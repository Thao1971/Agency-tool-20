"""Enrichment v2.0 — Multi-consumer endpoints with validation, whitelist, and HMAC callbacks."""

import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from models import new_id, now_iso
from auth_utils import get_current_user
from database import db
from services.enrichment_helpers import fire_enrichment_callback, build_callback_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/enrichment", tags=["enrichment"])


# ── Request Models (multi-consumer contract) ──

class CallbackConfig(BaseModel):
    url: str
    mode: str = "on_complete"

class EnrichmentRequest(BaseModel):
    consumer_id: Optional[str] = None
    environment: Optional[str] = "production"
    entity_id: str
    entity_type: str = "company"
    profile_id: str = "agency_enrichment_v1"
    website: str
    metadata: Optional[Dict[str, Any]] = None
    callback: Optional[CallbackConfig] = None
    priority: str = "normal"
    # Backward compat fields
    cis_company_id: Optional[str] = None
    cif: Optional[str] = None
    cif_normalized: Optional[str] = None
    company_name: Optional[str] = None
    requested_fields: Optional[List[str]] = None
    callback_url: Optional[str] = None


# ── Consumer Validation ──

async def resolve_consumer(user: dict, req: EnrichmentRequest) -> dict:
    """Resolve and validate consumer from API key and request."""
    # Find consumer by API key user
    consumer = await db.consumers.find_one(
        {"api_key_user_ids": user["id"]},
        {"_id": 0}
    )
    if not consumer:
        # Fallback: use consumer_id from request or default
        consumer_id = req.consumer_id or "default"
        consumer = await db.consumers.find_one({"consumer_id": consumer_id}, {"_id": 0})

    if not consumer:
        # Auto-create default consumer for backward compat
        consumer = {
            "consumer_id": req.consumer_id or "default",
            "name": req.consumer_id or "Default Consumer",
            "environments": {},
            "active": True
        }

    return consumer


async def validate_callback_url(consumer: dict, environment: str, callback_url: str) -> bool:
    """Validate callback URL against consumer's allowed domains."""
    if not callback_url:
        return True

    env_config = consumer.get("environments", {}).get(environment, {})
    allowed_domains = env_config.get("allowed_callback_domains", [])

    # If no whitelist configured, allow all (backward compat)
    if not allowed_domains:
        return True

    parsed = urlparse(callback_url)
    domain = parsed.netloc.lower()

    if domain in allowed_domains or any(domain.endswith(f".{d}") for d in allowed_domains):
        return True

    logger.warning(f"Callback domain {domain} not in whitelist {allowed_domains} for consumer {consumer.get('consumer_id')}/{environment}")
    return False



# ── Endpoints ──

@router.post("/request")
async def enrichment_request(req: EnrichmentRequest, user=Depends(get_current_user)):
    """Multi-consumer enrichment request."""
    from services.worker import _accepting_new_jobs, _backpressure_reason, get_worker_status

    # Backpressure check
    if not _accepting_new_jobs:
        status = await get_worker_status()
        raise HTTPException(status_code=503, detail={
            "error": "service_saturated",
            "reason": _backpressure_reason,
            "retry_after_seconds": 30,
            "capacity": {
                "accepting_new_jobs": False,
                "queue_depth": status["queue_depth"],
                "memory_usage_pct": status["memory_usage_pct"]
            }
        })

    # Resolve consumer
    consumer = await resolve_consumer(user, req)
    consumer_id = consumer.get("consumer_id", req.consumer_id or "default")
    environment = req.environment or "production"

    # Normalize URL
    url = req.website.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Resolve callback URL (new format or legacy)
    callback_url = None
    if req.callback:
        callback_url = req.callback.url
    elif req.callback_url:
        callback_url = req.callback_url

    # Validate callback domain
    if callback_url:
        valid = await validate_callback_url(consumer, environment, callback_url)
        if not valid:
            raise HTTPException(status_code=400, detail={
                "error": "callback_domain_not_allowed",
                "domain": urlparse(callback_url).netloc,
                "consumer": consumer_id,
                "environment": environment
            })

    # Backward compat: entity_id from cis_company_id
    entity_id = req.entity_id or req.cis_company_id
    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id is required")

    # Extract metadata
    metadata = req.metadata or {}
    cif = metadata.get("cif") or req.cif
    cif_normalized = metadata.get("cif_normalized") or req.cif_normalized
    company_name = metadata.get("company_name") or req.company_name
    requested_fields = metadata.get("requested_fields") or req.requested_fields or []

    job_id = new_id()
    now = now_iso()

    # Create job
    job = {
        "id": job_id,
        "url": url,
        "status": "pending",
        "consumer_id": consumer_id,
        "environment": environment,
        "entity_id": entity_id,
        "entity_type": req.entity_type,
        "profile_id": req.profile_id,
        "bulk_job_id": None,
        "result_id": None,
        "retries": 0,
        "max_retries": 3,
        "error_message": None,
        "phase": None,
        "user_id": user["id"],
        "cis_company_id": entity_id,
        "enrichment_source": consumer_id,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "heartbeat_at": None
    }
    await db.analysis_jobs.insert_one({**job})

    # Store enrichment metadata
    await db.enrichment_metadata.insert_one({
        "job_id": job_id,
        "consumer_id": consumer_id,
        "environment": environment,
        "entity_id": entity_id,
        "entity_type": req.entity_type,
        "profile_id": req.profile_id,
        "cis_company_id": entity_id,
        "cif": cif,
        "cif_normalized": cif_normalized,
        "company_name": company_name,
        "website": url,
        "requested_fields": requested_fields,
        "priority": req.priority,
        "callback_url": callback_url,
        "callback_mode": req.callback.mode if req.callback else "on_complete",
        "created_at": now
    })

    # Log admission
    logger.info(f"JOB_ADMIT | job={job_id[:12]} | consumer={consumer_id} | env={environment} | entity={entity_id} | url={url[:50]}")

    # Get queue position
    queue_depth = await db.analysis_jobs.count_documents({"status": "pending"})

    return {
        "job_id": job_id,
        "entity_id": entity_id,
        "consumer_id": consumer_id,
        "status": "pending",
        "queue_position": queue_depth,
        "estimated_wait_seconds": queue_depth * 22 // 3,
        "url": url,
        "created_at": now
    }


@router.get("/jobs/{job_id}")
async def get_enrichment_job(job_id: str, user=Depends(get_current_user)):
    job = await db.analysis_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    meta = await db.enrichment_metadata.find_one({"job_id": job_id}, {"_id": 0})
    response = {**job}
    if meta:
        for field in ["consumer_id", "environment", "entity_id", "profile_id", "cif", "company_name", "requested_fields"]:
            if meta.get(field):
                response[field] = meta[field]

    if job.get("result_id"):
        result = await db.agency_results.find_one(
            {"id": job["result_id"]},
            {"_id": 0, "callback_status": 1, "callback_sent_at": 1, "callback_error": 1}
        )
        if result:
            response["callback_status"] = result.get("callback_status")
            response["callback_sent_at"] = result.get("callback_sent_at")
            if result.get("callback_error"):
                response["callback_error"] = result["callback_error"]

    return response


@router.post("/retry-callbacks")
async def retry_failed_callbacks(user=Depends(get_current_user)):
    failed = await db.agency_results.find(
        {"callback_status": "failed", "callback_url": {"$ne": None}},
        {"_id": 0, "id": 1, "entity_id": 1, "cis_company_id": 1, "callback_url": 1}
    ).to_list(500)

    if not failed:
        return {"status": "no_failed_callbacks", "retried": 0}

    results = []
    for r in failed:
        await fire_enrichment_callback(r["id"])
        updated = await db.agency_results.find_one(
            {"id": r["id"]}, {"_id": 0, "id": 1, "entity_id": 1, "cis_company_id": 1, "callback_status": 1}
        )
        results.append({
            "result_id": r["id"],
            "entity_id": r.get("entity_id") or r.get("cis_company_id"),
            "new_status": updated.get("callback_status") if updated else "unknown"
        })

    succeeded = sum(1 for r in results if r["new_status"] == "sent")
    return {"status": "retried", "total": len(results), "succeeded": succeeded, "failed": len(results) - succeeded, "details": results}


@router.post("/retry-callback/{result_id}")
async def retry_single_callback(result_id: str, user=Depends(get_current_user)):
    result = await db.agency_results.find_one({"id": result_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    if not result.get("callback_url"):
        raise HTTPException(status_code=400, detail="No callback URL configured")

    await fire_enrichment_callback(result_id)
    updated = await db.agency_results.find_one(
        {"id": result_id}, {"_id": 0, "callback_status": 1, "callback_sent_at": 1, "callback_error": 1}
    )
    return updated


# ── Lookup endpoints ──
lookup_router = APIRouter(prefix="/api/v1/results", tags=["results-lookup"])

@lookup_router.get("/by-entity/{entity_id}")
async def get_result_by_entity(entity_id: str, user=Depends(get_current_user)):
    result = await db.agency_results.find_one(
        {"$or": [{"entity_id": entity_id}, {"cis_company_id": entity_id}]},
        {"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="No result found for this entity")
    evidence = await db.evidence_items.find({"result_id": result["id"]}, {"_id": 0}).to_list(200)
    result["evidence"] = evidence
    return result

@lookup_router.get("/by-cis-company/{cis_company_id}")
async def get_result_by_cis_company(cis_company_id: str, user=Depends(get_current_user)):
    result = await db.agency_results.find_one(
        {"$or": [{"cis_company_id": cis_company_id}, {"entity_id": cis_company_id}]},
        {"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="No result found for this CIS company")
    evidence = await db.evidence_items.find({"result_id": result["id"]}, {"_id": 0}).to_list(200)
    result["evidence"] = evidence
    return result

@lookup_router.get("/by-cif/{cif}")
async def get_result_by_cif(cif: str, user=Depends(get_current_user)):
    cif_clean = cif.strip().upper().replace("-", "").replace(" ", "")
    result = await db.agency_results.find_one(
        {"$or": [{"cif": cif}, {"cif_normalized": cif_clean}, {"cif": cif_clean}]},
        {"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="No result found for this CIF")
    evidence = await db.evidence_items.find({"result_id": result["id"]}, {"_id": 0}).to_list(200)
    result["evidence"] = evidence
    return result
