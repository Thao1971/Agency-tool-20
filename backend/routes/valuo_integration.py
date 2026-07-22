"""Valuo Integration — Receives update requests from Valuo, resolves entities, creates enrichment jobs."""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, Request
from typing import Optional, List
from pydantic import BaseModel
from database import db
from models import new_id, now_iso
from auth_utils import get_current_user
from services.entity_resolution import create_master_company, merge_into_master
from services.entity_resolution_provider import resolve_entity_provider as resolve_entity
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/valuo", tags=["valuo_integration"])


class ValuoUpdateRequest(BaseModel):
    valuo_company_id: str
    legal_name: Optional[str] = None
    commercial_names: Optional[List[str]] = None
    acronym: Optional[str] = None
    cif: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    requested_by: Optional[str] = None
    request_reason: Optional[str] = None


@router.post("/request-update-from-valuo")
async def request_update_from_valuo(req: ValuoUpdateRequest, background_tasks: BackgroundTasks):
    """Receive an update/enrichment request from Valuo. Public endpoint (Valuo authenticates via its own mechanism)."""
    now = now_iso()
    request_id = f"vreq_{new_id()[:12]}"

    # 1. Entity Resolution
    aliases = []
    if req.acronym:
        aliases.append(req.acronym)
    if req.commercial_names:
        aliases.extend(req.commercial_names)

    resolution = await resolve_entity(
        legal_name=req.legal_name,
        commercial_name=req.commercial_names[0] if req.commercial_names else None,
        cif=req.cif,
        domain=req.domain or req.website,
        aliases=aliases,
        source="valuo",
    )

    master_company_id = None
    resolution_status = resolution["status"]

    # 2. Act on resolution
    if resolution_status == "auto_merged" and resolution["match_id"]:
        master_company_id = resolution["match_id"]

        # Merge incoming Valuo data
        incoming = {}
        if req.legal_name:
            incoming["legal_name"] = req.legal_name
        if req.commercial_names:
            incoming["commercial_names"] = req.commercial_names
        if req.acronym:
            incoming["aliases"] = [req.acronym]
        if req.cif:
            incoming["cif"] = req.cif
        if req.website:
            incoming["website"] = req.website
        if req.domain:
            incoming["domain"] = req.domain
        if req.category_name:
            incoming["category_name"] = req.category_name
        incoming["_merge_score"] = resolution["score"]
        incoming["_merge_method"] = resolution["method"]

        await merge_into_master(
            master_company_id=master_company_id,
            incoming=incoming,
            source="valuo",
            source_id=req.valuo_company_id,
            user=req.requested_by,
        )

        # Link valuo_company_id
        await db.companies_master.update_one(
            {"master_company_id": master_company_id},
            {"$addToSet": {"linked_valuo_ids": req.valuo_company_id}, "$set": {"updated_at": now}}
        )

    elif resolution_status == "conflict":
        master_company_id = resolution.get("match_id")
        # Mark conflict on the best candidate
        if master_company_id:
            await db.companies_master.update_one(
                {"master_company_id": master_company_id},
                {"$set": {"merge_status": "conflict", "updated_at": now}}
            )

    else:  # discovered
        mc = await create_master_company(
            legal_name=req.legal_name or "Unknown",
            cif=req.cif,
            domain=req.domain or req.website,
            commercial_names=req.commercial_names,
            aliases=[req.acronym] if req.acronym else None,
            category_name=req.category_name,
            source="valuo",
            source_id=req.valuo_company_id,
            merge_status="discovered",
        )
        master_company_id = mc["master_company_id"]

        # Link valuo_company_id
        await db.companies_master.update_one(
            {"master_company_id": master_company_id},
            {"$addToSet": {"linked_valuo_ids": req.valuo_company_id}}
        )

    # 3. Create enrichment request record
    enrichment_request = {
        "request_id": request_id,
        "valuo_company_id": req.valuo_company_id,
        "master_company_id": master_company_id,
        "resolution_status": resolution_status,
        "resolution_score": resolution["score"],
        "resolution_method": resolution["method"],
        "resolution_candidates": resolution["candidates"][:3],
        "requested_by": req.requested_by,
        "request_reason": req.request_reason,
        "source": "valuo",
        "incoming_data": req.model_dump(),
        "enrichment_status": "pending",
        "merge_status": resolution_status,
        "updated_fields": [],
        "completed_at": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.valuo_update_requests.insert_one({**enrichment_request})

    # 4. Audit
    await db.er_audit_logs.insert_one({
        "log_id": new_id(),
        "master_company_id": master_company_id,
        "action": f"valuo_request_{resolution_status}",
        "source": "valuo",
        "source_id": req.valuo_company_id,
        "fields_updated": [],
        "merge_score": resolution["score"],
        "merge_method": resolution["method"],
        "performed_by": req.requested_by or "valuo_system",
        "timestamp": now,
    })

    # 5. Process enrichment — use BackgroundTasks (survives response completion)
    from services.valuo_enrichment import process_valuo_request

    async def _safe_enrich(rid):
        try:
            await process_valuo_request(rid)
        except Exception as e:
            logger.error(f"Background enrichment failed for {rid}: {e}")
            from services.valuo_enrichment import _mark_failed
            await _mark_failed(rid, str(e)[:200], now_iso())

    background_tasks.add_task(_safe_enrich, request_id)

    # 6. Response
    return {
        "agency_request_id": request_id,
        "master_company_id": master_company_id,
        "resolution_status": resolution_status,
        "confidence_score": resolution["score"],
        "candidates": [
            {"master_company_id": c["master_company_id"], "legal_name": c.get("legal_name"),
             "score": c["score"], "method": c["method"]}
            for c in resolution["candidates"][:3]
        ],
        "message": {
            "auto_merged": "Entity matched and merged. Enrichment job created.",
            "conflict": "Ambiguous match — needs human review in Agency Tool.",
            "discovered": "New entity created. Enrichment job pending.",
        }.get(resolution_status, "Processed."),
    }


@router.get("/request-update-status/{request_id}")
async def get_update_request_status(request_id: str):
    """Check status of a Valuo update request. Public endpoint."""
    req = await db.valuo_update_requests.find_one(
        {"request_id": request_id}, {"_id": 0}
    )
    if not req:
        raise HTTPException(404, "Request not found")

    return {
        "agency_request_id": req["request_id"],
        "status": req["enrichment_status"],
        "master_company_id": req["master_company_id"],
        "valuo_company_id": req["valuo_company_id"],
        "resolution_status": req["resolution_status"],
        "enrichment_status": req["enrichment_status"],
        "merge_status": req["merge_status"],
        "updated_fields": req.get("updated_fields", []),
        "completed_at": req.get("completed_at"),
        "error": req.get("error"),
        "created_at": req["created_at"],
    }


@router.get("/valuo-requests")
async def list_valuo_requests(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """List all Valuo update requests (admin)."""
    query = {}
    if status:
        query["enrichment_status"] = status
    total = await db.valuo_update_requests.count_documents(query)
    requests = await db.valuo_update_requests.find(
        query, {"_id": 0, "incoming_data": 0, "resolution_candidates": 0}
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)
    return {"requests": requests, "total": total}


@router.post("/process-pending")
async def process_pending(user=Depends(get_current_user)):
    """Process all pending Valuo enrichment requests."""
    from services.valuo_enrichment import process_all_pending
    result = await process_all_pending()
    return result


@router.post("/process-request/{request_id}")
async def force_process_request(request_id: str, user=Depends(get_current_user)):
    """Force-process a specific Valuo request."""
    await db.valuo_update_requests.update_one(
        {"request_id": request_id},
        {"$set": {"enrichment_status": "pending", "error": None}}
    )
    from services.valuo_enrichment import process_valuo_request
    result = await process_valuo_request(request_id)
    return result


@router.get("/request-status/{request_id}")
async def request_status(request_id: str, request: Request):
    """Per-request status endpoint for Valuo polling. Public (Valuo calls this)."""
    req = await db.valuo_update_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not req:
        from fastapi import HTTPException
        raise HTTPException(404, "Request not found")

    meta = req.get("enrichment_meta", {})
    mc_id = req.get("master_company_id")

    # Pointer to the canonical enriched company endpoint (Valuo can dereference)
    base = str(request.base_url).rstrip("/")
    enriched_company_url = (
        f"{base}/api/v1/company/{mc_id}/enriched" if mc_id else None
    )

    return {
        "request_id": req.get("request_id"),
        "status": req.get("status") or req.get("enrichment_status", "pending"),
        "enrichment_status": req.get("enrichment_status", "pending"),
        "merge_status": req.get("merge_status"),
        "master_company_id": mc_id,
        "updated_fields": req.get("updated_fields", []),
        "fields_count": len(req.get("updated_fields", [])),
        "enriched_data": req.get("enriched_data", {}),
        "enriched_company_url": enriched_company_url,
        "completed_at": req.get("completed_at"),
        "error": req.get("error"),
        "created_at": req.get("created_at"),
        "updated_at": req.get("updated_at"),
        "enrichment_meta": {
            "sources_consulted": meta.get("sources_consulted", []),
            "sources_count": meta.get("sources_count", 0),
            "fields_count": meta.get("fields_count", 0),
            "duration_ms": meta.get("duration_ms"),
            "processed_at": meta.get("processed_at"),
        },
    }


@router.get("/health")
async def valuo_health():
    """Realtime health check for the Valuo enrichment pipeline.

    Returns:
      - counts by status (pending, processing, completed, failed)
      - last hour timeline bucketed by 5-min intervals
      - oldest stuck request (if any pending > 5 min)
      - p50 / p95 duration_ms over last 100 completed
    """
    from datetime import datetime, timezone, timedelta

    now_dt = datetime.now(timezone.utc)
    one_hour_ago = now_dt - timedelta(hours=1)
    one_hour_ago_iso = one_hour_ago.isoformat().replace("+00:00", "Z")
    stuck_threshold = (now_dt - timedelta(minutes=5)).isoformat()

    # Counts by status
    by_status = {}
    for s in ("pending", "processing", "completed", "failed"):
        by_status[s] = await db.valuo_update_requests.count_documents({"enrichment_status": s})

    # Oldest stuck pending (>5 min)
    stuck = await db.valuo_update_requests.find_one(
        {"enrichment_status": {"$in": ["pending", "processing"]}, "created_at": {"$lt": stuck_threshold}},
        {"_id": 0, "request_id": 1, "valuo_company_id": 1, "created_at": 1, "enrichment_status": 1},
        sort=[("created_at", 1)],
    )

    # Timeline of last hour, bucketed by 5-min intervals (12 buckets)
    recent = await db.valuo_update_requests.find(
        {"created_at": {"$gte": one_hour_ago_iso}},
        {"_id": 0, "created_at": 1, "enrichment_status": 1, "enrichment_meta": 1},
    ).to_list(2000)

    buckets = []
    for i in range(12):
        bucket_start = one_hour_ago + timedelta(minutes=i * 5)
        bucket_end = bucket_start + timedelta(minutes=5)
        bucket = {
            "from": bucket_start.isoformat().replace("+00:00", "Z"),
            "to": bucket_end.isoformat().replace("+00:00", "Z"),
            "label": bucket_start.strftime("%H:%M"),
            "completed": 0,
            "failed": 0,
            "pending": 0,
            "processing": 0,
        }
        for r in recent:
            ca = r.get("created_at", "")
            if not ca:
                continue
            try:
                ca_dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
            except Exception:
                continue
            if bucket_start <= ca_dt < bucket_end:
                status = r.get("enrichment_status", "pending")
                if status in bucket:
                    bucket[status] += 1
        buckets.append(bucket)

    # Duration percentiles over last 100 completed
    last_completed = await db.valuo_update_requests.find(
        {"enrichment_status": "completed", "enrichment_meta.duration_ms": {"$ne": None}},
        {"_id": 0, "enrichment_meta.duration_ms": 1},
    ).sort("completed_at", -1).limit(100).to_list(100)

    durations = sorted(
        [r["enrichment_meta"]["duration_ms"] for r in last_completed if r.get("enrichment_meta", {}).get("duration_ms") is not None]
    )
    p50 = durations[len(durations) // 2] if durations else None
    p95 = durations[int(len(durations) * 0.95)] if len(durations) >= 20 else (max(durations) if durations else None)

    # Health verdict
    if by_status["failed"] > 0:
        verdict = "degraded"
    elif stuck:
        verdict = "stuck"
    elif by_status["pending"] > 10 or by_status["processing"] > 5:
        verdict = "busy"
    else:
        verdict = "healthy"

    return {
        "verdict": verdict,
        "by_status": by_status,
        "total": sum(by_status.values()),
        "oldest_stuck": stuck,
        "timeline_last_hour": buckets,
        "duration_ms": {"p50": p50, "p95": p95, "samples": len(durations)},
        "checked_at": now_dt.isoformat().replace("+00:00", "Z"),
    }
