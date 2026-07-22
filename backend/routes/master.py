"""Companies Master — Routes for the canonical entity dataset and entity resolution."""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from pydantic import BaseModel
from database import db
from models import new_id, now_iso
from auth_utils import get_current_user
from services.entity_resolution import (
    create_master_company, merge_into_master,
    _normalize_name, _normalize_cif, _extract_domain
)
from services.entity_resolution_provider import resolve_entity_provider as resolve_entity
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/master", tags=["companies_master"])


# ── Models ──
class MasterCompanyCreate(BaseModel):
    legal_name: str
    commercial_names: Optional[List[str]] = None
    aliases: Optional[List[str]] = None
    cif: Optional[str] = None
    website: Optional[str] = None
    category_name: Optional[str] = None


class MasterCompanyUpdate(BaseModel):
    legal_name: Optional[str] = None
    commercial_names: Optional[List[str]] = None
    aliases: Optional[List[str]] = None
    cif: Optional[str] = None
    website: Optional[str] = None
    category_name: Optional[str] = None
    merge_status: Optional[str] = None


class ResolveRequest(BaseModel):
    legal_name: Optional[str] = None
    commercial_name: Optional[str] = None
    cif: Optional[str] = None
    domain: Optional[str] = None
    aliases: Optional[List[str]] = None


class IngestFromScraperRequest(BaseModel):
    agency_result_ids: List[str]


# ══════════════════════════════════════════
# CRUD
# ══════════════════════════════════════════

@router.get("")
async def list_master_companies(
    search: Optional[str] = None,
    merge_status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    query = {}
    if search:
        query["$or"] = [
            {"legal_name": {"$regex": search, "$options": "i"}},
            {"normalized_name": {"$regex": search, "$options": "i"}},
            {"commercial_names": {"$regex": search, "$options": "i"}},
            {"aliases": {"$regex": search, "$options": "i"}},
            {"cif": {"$regex": search, "$options": "i"}},
        ]
    if merge_status:
        query["merge_status"] = merge_status

    total = await db.companies_master.count_documents(query)
    companies = await db.companies_master.find(query, {"_id": 0}).sort("updated_at", -1).skip(offset).limit(limit).to_list(limit)
    return {"companies": companies, "total": total}


@router.get("/stats")
async def master_stats(user=Depends(get_current_user)):
    total = await db.companies_master.count_documents({})
    discovered = await db.companies_master.count_documents({"merge_status": "discovered"})
    auto_merged = await db.companies_master.count_documents({"merge_status": "auto_merged"})
    verified = await db.companies_master.count_documents({"merge_status": "verified"})
    conflict = await db.companies_master.count_documents({"merge_status": "conflict"})
    with_cif = await db.companies_master.count_documents({"cif": {"$ne": None}})
    with_domain = await db.companies_master.count_documents({"domain": {"$ne": None}})
    published_to_valuo = await db.companies_master.count_documents({"published_to_valuo": True})
    pending_publication = await db.companies_master.count_documents({"merge_status": {"$in": ["verified", "auto_merged"]}, "published_to_valuo": {"$ne": True}})
    valuo_requests = await db.valuo_update_requests.count_documents({})
    valuo_pending = await db.valuo_update_requests.count_documents({"enrichment_status": "pending"})
    audit_entries = await db.er_audit_logs.count_documents({})

    return {
        "total": total,
        "discovered": discovered,
        "auto_merged": auto_merged,
        "verified": verified,
        "conflict": conflict,
        "with_cif": with_cif,
        "with_domain": with_domain,
        "published_to_valuo": published_to_valuo,
        "pending_publication": pending_publication,
        "valuo_requests": valuo_requests,
        "valuo_requests_pending": valuo_pending,
        "audit_entries": audit_entries,
    }


@router.get("/compare")
async def compare_datasets(user=Depends(get_current_user)):
    """Compare agency_results vs companies_master for debugging."""
    ar_total = await db.agency_results.count_documents({"status": "completed"})
    ar_with_cif = await db.agency_results.count_documents({"cif": {"$ne": None}, "status": "completed"})
    mc_total = await db.companies_master.count_documents({})
    mc_with_cif = await db.companies_master.count_documents({"cif": {"$ne": None}})

    linked_count = 0
    async for mc in db.companies_master.find({}, {"_id": 0, "linked_agency_result_ids": 1}):
        linked_count += len(mc.get("linked_agency_result_ids", []))

    return {
        "agency_results": {"total": ar_total, "with_cif": ar_with_cif},
        "companies_master": {"total": mc_total, "with_cif": mc_with_cif},
        "linked_results": linked_count,
        "unlinked_results": ar_total - linked_count,
        "coverage_pct": round(linked_count / max(ar_total, 1) * 100, 1),
    }


# ══════════════════════════════════════════
# CONFLICTS WORKSPACE
# ══════════════════════════════════════════

@router.get("/conflicts")
async def list_conflicts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """List entities with conflicts or low confidence."""
    query = {"$or": [
        {"merge_status": "conflict"},
        {"confidence_score": {"$lt": 0.7}},
    ]}
    total = await db.companies_master.count_documents(query)
    entities = await db.companies_master.find(query, {"_id": 0}).sort("confidence_score", 1).skip(offset).limit(limit).to_list(limit)

    # Detect conflict types
    for e in entities:
        conflicts = []
        if e.get("merge_status") == "conflict":
            conflicts.append("ambiguous_match")
        if e.get("confidence_score", 1) < 0.7:
            conflicts.append("low_confidence")
        # Check for duplicate CIF
        if e.get("cif_normalized"):
            dup_cif = await db.companies_master.count_documents({
                "cif_normalized": e["cif_normalized"],
                "master_company_id": {"$ne": e["master_company_id"]}
            })
            if dup_cif > 0:
                conflicts.append("duplicate_cif")
        # Check for duplicate domain
        if e.get("domain"):
            dup_dom = await db.companies_master.count_documents({
                "domain": e["domain"],
                "master_company_id": {"$ne": e["master_company_id"]}
            })
            if dup_dom > 0:
                conflicts.append("duplicate_domain")
        e["conflict_types"] = conflicts
        e["matching_signals"] = _extract_signals(e)

    return {"conflicts": entities, "total": total}


def _extract_signals(entity: dict) -> list:
    """Extract matching signals from an entity."""
    signals = []
    if entity.get("cif"):
        signals.append({"type": "cif", "value": entity["cif"], "weight": 1.0})
    if entity.get("domain"):
        signals.append({"type": "domain", "value": entity["domain"], "weight": 0.97})
    if entity.get("normalized_name"):
        signals.append({"type": "name", "value": entity["normalized_name"], "weight": 0.7})
    for alias in entity.get("aliases", []):
        signals.append({"type": "alias", "value": alias, "weight": 0.6})
    return signals


@router.post("/conflicts/{mc_id}/resolve")
async def resolve_conflict(mc_id: str, action: str = Query(..., regex="^(verify|reject|merge)$"), user=Depends(get_current_user)):
    """Resolve a conflict: verify (accept), reject (discard), or merge."""
    now = now_iso()
    email = user.get("email", user.get("id"))

    if action == "verify":
        await db.companies_master.update_one(
            {"master_company_id": mc_id},
            {"$set": {"merge_status": "verified", "updated_at": now}}
        )
    elif action == "reject":
        await db.companies_master.update_one(
            {"master_company_id": mc_id},
            {"$set": {"merge_status": "rejected", "updated_at": now}}
        )

    await db.er_audit_logs.insert_one({
        "log_id": new_id(), "master_company_id": mc_id,
        "action": f"conflict_resolved_{action}", "performed_by": email, "timestamp": now,
    })
    return {"status": action, "master_company_id": mc_id}


# ══════════════════════════════════════════
# GOVERNANCE PIPELINE (operational transitions)
# ══════════════════════════════════════════

VALID_TRANSITIONS = {
    "discovered": ["auto_merged", "verified", "conflict", "rejected"],
    "auto_merged": ["verified", "conflict", "rejected"],
    "conflict": ["verified", "rejected"],
    "verified": ["published", "rejected"],
    "rejected": ["discovered"],
    "published": ["excluded", "verified"],
    "excluded": ["verified"],
}


@router.post("/{mc_id}/transition")
async def pipeline_transition(
    mc_id: str,
    target_status: str = Query(...),
    user=Depends(get_current_user)
):
    """Formal pipeline transition with validation and audit."""
    mc = await db.companies_master.find_one({"master_company_id": mc_id}, {"_id": 0})
    if not mc:
        raise HTTPException(404, "Entity not found")

    current = mc.get("merge_status", "discovered")
    allowed = VALID_TRANSITIONS.get(current, [])
    if target_status not in allowed:
        raise HTTPException(400, f"Invalid transition: {current} → {target_status}. Allowed: {allowed}")

    now = now_iso()
    email = user.get("email", user.get("id"))

    update = {"merge_status": target_status, "updated_at": now}

    if target_status == "published":
        update["published_to_valuo"] = True
        update["published_to_valuo_at"] = now
        update["published_to_valuo_by"] = email
        update["publication_status"] = "published"
    elif target_status == "excluded":
        update["published_to_valuo"] = False
        update["publication_status"] = "excluded"
    elif target_status == "rejected":
        update["published_to_valuo"] = False
        update["publication_status"] = "rejected"

    await db.companies_master.update_one({"master_company_id": mc_id}, {"$set": update})

    await db.er_audit_logs.insert_one({
        "log_id": new_id(), "master_company_id": mc_id,
        "action": f"transition_{current}_to_{target_status}",
        "source": "governance_pipeline",
        "performed_by": email, "timestamp": now,
        "fields_updated": [f"{current} → {target_status}"],
    })

    return {"status": target_status, "previous": current, "entity_id": mc_id}


# ══════════════════════════════════════════
# PUBLICATION PIPELINE VISUAL
# ══════════════════════════════════════════

@router.get("/pipeline")
async def publication_pipeline(user=Depends(get_current_user)):
    """Visual pipeline: RAW → MATCHED → REVIEWED → VERIFIED → PUBLISHED → EXCLUDED."""
    raw = await db.agency_results.count_documents({"status": "completed"})
    matched = await db.companies_master.count_documents({})
    discovered = await db.companies_master.count_documents({"merge_status": "discovered"})
    auto_merged = await db.companies_master.count_documents({"merge_status": "auto_merged"})
    verified = await db.companies_master.count_documents({"merge_status": "verified"})
    conflict = await db.companies_master.count_documents({"merge_status": "conflict"})
    rejected = await db.companies_master.count_documents({"merge_status": "rejected"})
    published = await db.companies_master.count_documents({"published_to_valuo": True})
    excluded = await db.provider_exclusions.count_documents({"action": "exclude"})

    # Recent pipeline activity
    recent = await db.er_audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)

    return {
        "stages": [
            {"key": "raw", "label": "Raw (Scraper)", "count": raw, "color": "zinc"},
            {"key": "matched", "label": "Matched", "count": matched, "color": "blue"},
            {"key": "discovered", "label": "Discovered", "count": discovered, "color": "zinc"},
            {"key": "auto_merged", "label": "Auto-Merged", "count": auto_merged, "color": "blue"},
            {"key": "verified", "label": "Verified", "count": verified, "color": "emerald"},
            {"key": "conflict", "label": "Conflicts", "count": conflict, "color": "rose"},
            {"key": "rejected", "label": "Rejected", "count": rejected, "color": "zinc"},
            {"key": "published", "label": "Published to Valuo", "count": published, "color": "cyan"},
            {"key": "excluded", "label": "Excluded", "count": excluded, "color": "rose"},
        ],
        "recent_activity": [{
            "action": r.get("action"),
            "entity": r.get("master_company_id", "")[:16],
            "by": r.get("performed_by"),
            "at": r.get("timestamp"),
        } for r in recent],
    }


@router.get("/{mc_id}")
async def get_master_company(mc_id: str, user=Depends(get_current_user)):
    company = await db.companies_master.find_one({"master_company_id": mc_id}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Master company not found")

    # Get linked agency_results
    linked_results = []
    for ar_id in company.get("linked_agency_result_ids", []):
        ar = await db.agency_results.find_one({"id": ar_id}, {"_id": 0, "id": 1, "company_name": 1, "input_url": 1, "category": 1, "status": 1})
        if ar:
            linked_results.append(ar)
    company["linked_agency_results"] = linked_results

    # Get audit history
    audits = await db.er_audit_logs.find(
        {"master_company_id": mc_id}, {"_id": 0}
    ).sort("timestamp", -1).limit(20).to_list(20)
    company["audit_history"] = audits

    return company


@router.post("")
async def create_company(req: MasterCompanyCreate, user=Depends(get_current_user)):
    company = await create_master_company(
        legal_name=req.legal_name,
        cif=req.cif,
        domain=req.website,
        commercial_names=req.commercial_names,
        aliases=req.aliases,
        category_name=req.category_name,
        source="manual",
        merge_status="discovered",
    )
    return company


@router.put("/{mc_id}")
async def update_company(mc_id: str, req: MasterCompanyUpdate, user=Depends(get_current_user)):
    existing = await db.companies_master.find_one({"master_company_id": mc_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Not found")

    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if "legal_name" in update:
        update["normalized_name"] = _normalize_name(update["legal_name"])
    if "cif" in update:
        update["cif_normalized"] = _normalize_cif(update["cif"])
    if "website" in update:
        update["domain"] = _extract_domain(update["website"])

    update["updated_at"] = now_iso()
    await db.companies_master.update_one({"master_company_id": mc_id}, {"$set": update})

    await db.er_audit_logs.insert_one({
        "log_id": new_id(), "master_company_id": mc_id, "action": "manual_update",
        "source": "manual", "fields_updated": list(update.keys()),
        "performed_by": user.get("email", user.get("id")), "timestamp": now_iso(),
    })

    return await db.companies_master.find_one({"master_company_id": mc_id}, {"_id": 0})


@router.post("/{mc_id}/verify")
async def verify_company(mc_id: str, user=Depends(get_current_user)):
    """Mark a master company as verified (human-confirmed)."""
    await db.companies_master.update_one(
        {"master_company_id": mc_id},
        {"$set": {"merge_status": "verified", "updated_at": now_iso()}}
    )
    await db.er_audit_logs.insert_one({
        "log_id": new_id(), "master_company_id": mc_id, "action": "verified",
        "performed_by": user.get("email", user.get("id")), "timestamp": now_iso(),
    })
    return {"status": "verified"}


@router.post("/{mc_id}/publish-to-valuo")
async def publish_to_valuo(mc_id: str, user=Depends(get_current_user)):
    """Mark a master company as published to Valuo."""
    mc = await db.companies_master.find_one({"master_company_id": mc_id}, {"_id": 0})
    if not mc:
        raise HTTPException(404, "Not found")
    if mc.get("merge_status") not in ("verified", "auto_merged"):
        raise HTTPException(400, f"Cannot publish: merge_status is '{mc.get('merge_status')}'. Must be verified or auto_merged.")

    now = now_iso()
    email = user.get("email", user.get("id"))
    await db.companies_master.update_one(
        {"master_company_id": mc_id},
        {"$set": {"published_to_valuo": True, "published_to_valuo_at": now, "published_to_valuo_by": email, "updated_at": now}}
    )
    await db.er_audit_logs.insert_one({
        "log_id": new_id(), "master_company_id": mc_id, "action": "published_to_valuo",
        "performed_by": email, "timestamp": now,
    })
    return {"status": "published_to_valuo"}


@router.post("/{mc_id}/unpublish-from-valuo")
async def unpublish_from_valuo(mc_id: str, user=Depends(get_current_user)):
    """Remove a master company from Valuo publication."""
    now = now_iso()
    email = user.get("email", user.get("id"))
    await db.companies_master.update_one(
        {"master_company_id": mc_id},
        {"$set": {"published_to_valuo": False, "updated_at": now}}
    )
    await db.er_audit_logs.insert_one({
        "log_id": new_id(), "master_company_id": mc_id, "action": "unpublished_from_valuo",
        "performed_by": email, "timestamp": now,
    })
    return {"status": "unpublished"}


@router.get("/audit-log")
async def list_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """Global audit log for entity resolution and publication."""
    total = await db.er_audit_logs.count_documents({})
    logs = await db.er_audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).skip(offset).limit(limit).to_list(limit)
    return {"logs": logs, "total": total}


@router.post("/bulk-verify")
async def bulk_verify(user=Depends(get_current_user)):
    """Bulk-verify all auto_merged companies (convenience for initial review)."""
    now = now_iso()
    email = user.get("email", user.get("id"))
    result = await db.companies_master.update_many(
        {"merge_status": "auto_merged"},
        {"$set": {"merge_status": "verified", "updated_at": now}}
    )
    await db.er_audit_logs.insert_one({
        "log_id": new_id(), "master_company_id": "bulk",
        "action": "bulk_verified", "performed_by": email, "timestamp": now,
        "fields_updated": [f"{result.modified_count} companies"],
    })
    return {"status": "bulk_verified", "count": result.modified_count}


@router.post("/bulk-publish-to-valuo")
async def bulk_publish(user=Depends(get_current_user)):
    """Bulk-publish all verified companies to Valuo."""
    now = now_iso()
    email = user.get("email", user.get("id"))
    result = await db.companies_master.update_many(
        {"merge_status": "verified", "published_to_valuo": {"$ne": True}},
        {"$set": {"published_to_valuo": True, "published_to_valuo_at": now, "published_to_valuo_by": email, "updated_at": now}}
    )
    await db.er_audit_logs.insert_one({
        "log_id": new_id(), "master_company_id": "bulk",
        "action": "bulk_published_to_valuo", "performed_by": email, "timestamp": now,
        "fields_updated": [f"{result.modified_count} companies"],
    })
    return {"status": "bulk_published", "count": result.modified_count}


# ══════════════════════════════════════════
# ENTITY RESOLUTION
# ══════════════════════════════════════════

@router.post("/resolve")
async def resolve(req: ResolveRequest, user=Depends(get_current_user)):
    """Resolve an entity against companies_master. Does NOT create or merge — just resolves."""
    result = await resolve_entity(
        legal_name=req.legal_name,
        commercial_name=req.commercial_name,
        cif=req.cif,
        domain=req.domain,
        aliases=req.aliases,
    )
    return result


@router.post("/ingest-from-scraper")
async def ingest_from_scraper(req: IngestFromScraperRequest, user=Depends(get_current_user)):
    """Ingest agency_results into companies_master via entity resolution."""
    results = {"processed": 0, "created": 0, "merged": 0, "conflicts": 0, "skipped": 0, "items": []}

    for ar_id in req.agency_result_ids:
        ar = await db.agency_results.find_one({"id": ar_id}, {"_id": 0})
        if not ar:
            results["skipped"] += 1
            results["items"].append({"id": ar_id, "status": "not_found"})
            continue

        # Already linked?
        existing_link = await db.companies_master.find_one(
            {"linked_agency_result_ids": ar_id}, {"_id": 0, "master_company_id": 1}
        )
        if existing_link:
            results["skipped"] += 1
            results["items"].append({"id": ar_id, "status": "already_linked", "master_id": existing_link["master_company_id"]})
            continue

        resolution = await resolve_entity(
            legal_name=ar.get("company_name"),
            cif=ar.get("cif"),
            domain=ar.get("input_url"),
        )

        if resolution["status"] == "auto_merged" and resolution["match_id"]:
            merge_result = await merge_into_master(
                master_company_id=resolution["match_id"],
                incoming={
                    "commercial_names": [ar["company_name"]] if ar.get("company_name") else [],
                    "linked_agency_result_ids": ar_id,
                    "category_name": ar.get("category"),
                    "cif": ar.get("cif"),
                    "website": ar.get("input_url"),
                    "_merge_score": resolution["score"],
                    "_merge_method": resolution["method"],
                },
                source="scraper",
                source_id=ar_id,
            )
            results["merged"] += 1
            results["items"].append({"id": ar_id, "status": "merged", "master_id": resolution["match_id"], "score": resolution["score"]})

        elif resolution["status"] == "conflict":
            # Create link but mark as conflict
            if resolution["match_id"]:
                await db.companies_master.update_one(
                    {"master_company_id": resolution["match_id"]},
                    {"$set": {"merge_status": "conflict", "updated_at": now_iso()}}
                )
            results["conflicts"] += 1
            results["items"].append({"id": ar_id, "status": "conflict", "match_id": resolution.get("match_id"), "score": resolution["score"]})

        else:
            # Create new master company
            mc = await create_master_company(
                legal_name=ar.get("company_name", "Unknown"),
                cif=ar.get("cif"),
                domain=ar.get("input_url"),
                category_name=ar.get("category"),
                source="scraper",
                source_id=ar_id,
                merge_status="discovered",
            )
            results["created"] += 1
            results["items"].append({"id": ar_id, "status": "created", "master_id": mc["master_company_id"]})

        results["processed"] += 1

    return results


@router.post("/ingest-all-scraper")
async def ingest_all_from_scraper(user=Depends(get_current_user)):
    """Bulk ingest ALL unlinked agency_results into companies_master."""
    # Find agency_results not yet linked
    all_linked = set()
    async for mc in db.companies_master.find({}, {"_id": 0, "linked_agency_result_ids": 1}):
        all_linked.update(mc.get("linked_agency_result_ids", []))

    all_results = await db.agency_results.find(
        {"status": "completed"}, {"_id": 0, "id": 1}
    ).to_list(5000)

    unlinked_ids = [r["id"] for r in all_results if r["id"] not in all_linked]

    if not unlinked_ids:
        return {"status": "no_unlinked", "total_results": len(all_results), "already_linked": len(all_linked)}

    # Process in batches
    req = IngestFromScraperRequest(agency_result_ids=unlinked_ids[:500])
    return await ingest_from_scraper(req, user)


# ══════════════════════════════════════════
# ER CONFIG
# ══════════════════════════════════════════

@router.get("/er-config")
async def get_er_config(user=Depends(get_current_user)):
    """Get current entity resolution thresholds."""
    cfg = await db.er_config.find_one({"config_id": "default"}, {"_id": 0})
    from services.entity_resolution import DEFAULTS
    return {"config": {**DEFAULTS, **(cfg or {})}}


@router.put("/er-config")
async def update_er_config(body: dict, user=Depends(get_current_user)):
    """Update entity resolution thresholds."""
    allowed = {"auto_merge_threshold", "conflict_threshold", "cif_exact_score",
               "domain_exact_score", "legal_name_weight", "commercial_name_weight", "alias_weight"}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(400, "No valid fields")

    update["config_id"] = "default"
    update["updated_at"] = now_iso()
    update["updated_by"] = user.get("email", user.get("id"))

    await db.er_config.update_one(
        {"config_id": "default"}, {"$set": update}, upsert=True
    )
    return {"status": "updated", "config": update}
