"""Publication Layer v2 — Hardened contract for Valuo consumption.

Architecture: Agency Tool → Governance → Publication Layer → Valuo

Contract guarantees:
- Versioned (contract_version, schema_version)
- Deterministic (same input = same output)
- Incremental (updated_since filter)
- Change-detected (content_hash — no republish if unchanged)
- Stable payload (fixed fields, never dynamic)
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from database import db
from models import new_id, now_iso
from auth_utils import get_current_user
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/publication", tags=["publication"])

CONTRACT_VERSION = "2.0"
SCHEMA_VERSION = "2.0.0"


def _entity_to_payload(e: dict) -> dict:
    """Map internal entity to stable publication payload. NEVER return dynamic fields."""
    return {
        "canonical_entity_id": e["master_company_id"],
        "canonical_name": e.get("legal_name"),
        "normalized_name": e.get("normalized_name"),
        "aliases": e.get("aliases", []),
        "commercial_names": e.get("commercial_names", []),
        "cif": e.get("cif"),
        "category_name": e.get("category_name"),
        "domain": e.get("domain"),
        "website": e.get("website"),
        "publication_status": e.get("publication_status", "published"),
        "confidence_score": e.get("confidence_score"),
        "confidence_level": e.get("confidence_level"),
        "matching_signals": e.get("matching_signals", []),
        "source_provider": (e.get("source_trace", [{}])[0] or {}).get("source"),
        "content_hash": e.get("content_hash"),
        "published_at": e.get("published_to_valuo_at"),
        "updated_at": e.get("updated_at"),
    }


def _compute_content_hash(e: dict) -> str:
    """Deterministic hash of publishable content. If unchanged, no need to republish."""
    payload = {
        "legal_name": e.get("legal_name"),
        "normalized_name": e.get("normalized_name"),
        "aliases": sorted(e.get("aliases", [])),
        "commercial_names": sorted(e.get("commercial_names", [])),
        "cif": e.get("cif"),
        "category_name": e.get("category_name"),
        "domain": e.get("domain"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]


# ══════════════════════════════════════════
# PUBLIC (Valuo consumption — no auth)
# ══════════════════════════════════════════

@router.get("/entities")
async def get_published_entities(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None,
    updated_since: Optional[str] = None,
):
    """Public: Publication-ready entities. Stable contract for Valuo."""
    query = {"published_to_valuo": True}
    if category:
        query["category_name"] = {"$regex": category, "$options": "i"}
    if updated_since:
        query["updated_at"] = {"$gte": updated_since}

    total = await db.companies_master.count_documents(query)
    raw = await db.companies_master.find(query, {"_id": 0}).sort("updated_at", -1).skip(offset).limit(limit).to_list(limit)

    return {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "items": [_entity_to_payload(e) for e in raw],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/entities/{entity_id}")
async def get_published_entity(entity_id: str):
    """Public: Single published entity."""
    e = await db.companies_master.find_one(
        {"master_company_id": entity_id, "published_to_valuo": True}, {"_id": 0}
    )
    if not e:
        raise HTTPException(404, "Entity not published or not found")
    return {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        **_entity_to_payload(e),
    }


@router.get("/status")
async def publication_status():
    """Public: Publication summary."""
    total = await db.companies_master.count_documents({})
    published = await db.companies_master.count_documents({"published_to_valuo": True})
    excluded = await db.companies_master.count_documents({"publication_status": "excluded"})
    pending = await db.companies_master.count_documents({
        "merge_status": {"$in": ["verified", "auto_merged"]},
        "published_to_valuo": {"$ne": True}
    })
    last_pub = await db.companies_master.find_one(
        {"published_to_valuo": True}, {"_id": 0, "published_to_valuo_at": 1},
        sort=[("published_to_valuo_at", -1)]
    )
    last_event = await db.publication_events.find_one(
        {}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)]
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "total_master_entities": total,
        "published": published,
        "excluded": excluded,
        "pending_publication": pending,
        "last_published_at": last_pub.get("published_to_valuo_at") if last_pub else None,
        "last_event_at": last_event.get("timestamp") if last_event else None,
    }


@router.get("/health")
async def publication_health():
    """Public: Simple health check."""
    published = await db.companies_master.count_documents({"published_to_valuo": True})
    return {"status": "ok", "published": published, "contract_version": CONTRACT_VERSION}


@router.get("/version")
async def publication_version():
    """Public: API version info."""
    return {"contract_version": CONTRACT_VERSION, "schema_version": SCHEMA_VERSION}


@router.get("/stats")
async def publication_stats():
    """Public: Operational stats."""
    total_events = await db.publication_events.count_documents({})
    return {
        "contract_version": CONTRACT_VERSION,
        "total_events": total_events,
        "published": await db.companies_master.count_documents({"published_to_valuo": True}),
        "excluded": await db.companies_master.count_documents({"publication_status": "excluded"}),
        "generated_at": now_iso(),
    }


# ══════════════════════════════════════════
# ADMIN (Agency Tool — auth required)
# ══════════════════════════════════════════

@router.get("/pending")
async def list_pending(limit: int = Query(50, ge=1, le=200), user=Depends(get_current_user)):
    query = {"merge_status": {"$in": ["verified", "auto_merged"]}, "published_to_valuo": {"$ne": True}}
    total = await db.companies_master.count_documents(query)
    entities = await db.companies_master.find(query, {"_id": 0}).sort("updated_at", -1).limit(limit).to_list(limit)
    return {"entities": entities, "total": total}


@router.get("/published-admin")
async def list_published_admin(limit: int = Query(50, ge=1, le=200), user=Depends(get_current_user)):
    query = {"published_to_valuo": True}
    total = await db.companies_master.count_documents(query)
    entities = await db.companies_master.find(query, {"_id": 0}).sort("published_to_valuo_at", -1).limit(limit).to_list(limit)
    return {"entities": entities, "total": total}


@router.get("/excluded-admin")
async def list_excluded_admin(limit: int = Query(50, ge=1, le=200), user=Depends(get_current_user)):
    exclusions = await db.provider_exclusions.find(
        {"action": "exclude"}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"exclusions": exclusions, "total": await db.provider_exclusions.count_documents({"action": "exclude"})}


@router.get("/events")
async def list_events(limit: int = Query(50, ge=1, le=200), user=Depends(get_current_user)):
    """Admin: Publication event log."""
    events = await db.publication_events.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    total = await db.publication_events.count_documents({})
    return {"events": events, "total": total}


async def _publish_entity(mc_id: str, email: str) -> dict:
    """Internal: publish with change detection and event logging."""
    mc = await db.companies_master.find_one({"master_company_id": mc_id}, {"_id": 0})
    if not mc:
        return {"error": "not_found"}
    if mc.get("merge_status") not in ("verified", "auto_merged", "published"):
        return {"error": f"invalid_status:{mc.get('merge_status')}"}

    now = now_iso()
    new_hash = _compute_content_hash(mc)
    old_hash = mc.get("content_hash")

    # Change detection: skip if unchanged
    if mc.get("published_to_valuo") and old_hash == new_hash:
        return {"status": "unchanged", "entity_id": mc_id, "content_hash": new_hash}

    changed_fields = []
    if old_hash and old_hash != new_hash:
        changed_fields.append("content_changed")

    await db.companies_master.update_one(
        {"master_company_id": mc_id},
        {"$set": {
            "published_to_valuo": True,
            "published_to_valuo_at": now,
            "published_to_valuo_by": email,
            "publication_status": "published",
            "content_hash": new_hash,
            "updated_at": now,
        }}
    )

    # Publication event
    await db.publication_events.insert_one({
        "event_id": new_id(),
        "entity_id": mc_id,
        "action": "published",
        "published_at": now,
        "content_hash": new_hash,
        "changed_fields": changed_fields,
        "triggered_by": email,
        "timestamp": now,
    })

    return {"status": "published", "entity_id": mc_id, "content_hash": new_hash, "changed": len(changed_fields) > 0}


@router.post("/{mc_id}/publish")
async def publish_entity(mc_id: str, user=Depends(get_current_user)):
    email = user.get("email", user.get("id"))
    result = await _publish_entity(mc_id, email)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/{mc_id}/exclude")
async def exclude_entity(mc_id: str, reason: str = Query("manual_quality_control"), user=Depends(get_current_user)):
    now = now_iso()
    email = user.get("email", user.get("id"))
    await db.companies_master.update_one(
        {"master_company_id": mc_id},
        {"$set": {"published_to_valuo": False, "publication_status": "excluded", "updated_at": now}}
    )
    await db.provider_exclusions.insert_one({
        "exclusion_id": new_id(), "provider": "master", "source_record_id": mc_id,
        "action": "exclude", "reason_code": reason, "excluded_from_valuo": True,
        "created_by": email, "created_at": now, "updated_at": now,
    })
    await db.publication_events.insert_one({
        "event_id": new_id(), "entity_id": mc_id, "action": "excluded",
        "excluded_at": now, "triggered_by": email, "timestamp": now,
    })
    return {"status": "excluded", "entity_id": mc_id}


@router.post("/{mc_id}/restore")
async def restore_entity(mc_id: str, user=Depends(get_current_user)):
    now = now_iso()
    email = user.get("email", user.get("id"))
    await db.provider_exclusions.delete_many({"provider": "master", "source_record_id": mc_id, "action": "exclude"})
    await db.companies_master.update_one(
        {"master_company_id": mc_id},
        {"$set": {"publication_status": "pending", "updated_at": now}}
    )
    await db.publication_events.insert_one({
        "event_id": new_id(), "entity_id": mc_id, "action": "restored",
        "restored_at": now, "triggered_by": email, "timestamp": now,
    })
    return {"status": "restored", "entity_id": mc_id}
