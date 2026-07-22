"""Transaction Intelligence — API routes."""

import io
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Response
from typing import Optional
from database import db
from auth_utils import get_current_user
from models import new_id, now_iso
from transactions import (
    TransactionCreate, TransactionUpdate, SourceCreate, SourceUpdate,
    normalize_transaction, normalize_name, make_transaction_key,
    calculate_similarity, parse_float, parse_date,
    compute_visible_status, compute_cis_payload_hash, compute_incidences,
    CIS_CRITICAL_FIELDS, WITHDRAWAL_REASONS, CIS_SYNC_STATUSES,
    translate_country,
)

from transactions.matching import find_entity_matches, run_matching_for_transaction
from transactions.classification import suggest_classification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


# ══════════════════════════════════════════
# TRANSACTIONS CRUD
# ══════════════════════════════════════════

@router.get("")
async def list_transactions(
    search: Optional[str] = None, year: Optional[int] = None,
    status: Optional[str] = None, transaction_type: Optional[str] = None,
    geography: Optional[str] = None, dedupe_status: Optional[str] = None,
    publish_status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    query = {"deleted": {"$ne": True}}
    if search: query["$or"] = [
        {"target_name": {"$regex": search, "$options": "i"}},
        {"buyer_name": {"$regex": search, "$options": "i"}},
        {"seller_name": {"$regex": search, "$options": "i"}}
    ]
    if year: query["year"] = year
    if status: query["status"] = status
    if transaction_type: query["transaction_type"] = transaction_type
    if geography: query["geography_primary"] = {"$regex": geography, "$options": "i"}
    if dedupe_status: query["dedupe_status"] = dedupe_status
    if publish_status: query["publish_status"] = publish_status

    total = await db.transactions_normalized.count_documents(query)
    txs = await db.transactions_normalized.find(query, {"_id": 0}).sort("announcement_date", -1).skip(offset).limit(limit).to_list(limit)

    # Batch-enrich: 3 aggregate queries instead of 3*N individual queries
    tx_ids = [tx["transaction_id"] for tx in txs]

    src_pipeline = [
        {"$match": {"transaction_id": {"$in": tx_ids}}},
        {"$group": {"_id": "$transaction_id", "count": {"$sum": 1},
                     "primary_pub": {"$max": {"$cond": [{"$eq": ["$is_primary", True]}, "$publisher", None]}}}}
    ]
    src_data = {r["_id"]: r for r in await db.transaction_sources.aggregate(src_pipeline).to_list(len(tx_ids) + 1)}

    link_pipeline = [
        {"$match": {"transaction_id": {"$in": tx_ids}, "entity_role": "target",
                     "match_status": {"$in": ["manual_confirmed", "auto_strong_candidate", "needs_new_company", "external_entity"]}}},
        {"$group": {"_id": "$transaction_id"}}
    ]
    link_data = {r["_id"] for r in await db.transaction_company_links.aggregate(link_pipeline).to_list(len(tx_ids) + 1)}

    for tx in txs:
        tid = tx["transaction_id"]
        ps = tx.get("publish_status", "not_published")
        sync = tx.get("cis_sync_status")
        if tx.get("deleted"): vs = "archived"
        elif ps == "approved_for_cis" or tx.get("visible_in_cis"): vs = "pending_sync" if sync == "pending_update" else "published_in_cis"
        elif ps == "removed_from_cis": vs = "withdrawn_from_cis"
        elif ps == "ready_to_publish": vs = "ready_for_cis"
        elif tx.get("review_status") in ("reviewed", "approved"): vs = "needs_review"
        elif not tx.get("target_name") or not (tx.get("announcement_date") or tx.get("year")): vs = "incomplete"
        else: vs = "draft"
        tx["visible_status"] = vs

        src = src_data.get(tid, {})
        sc = src.get("count", 0)
        tx["sources_count"] = sc
        tx["primary_source_publisher"] = src.get("primary_pub") or tx.get("source")
        hs = sc > 0 or bool(tx.get("source") or tx.get("source_url"))
        hp = src.get("primary_pub") is not None or bool(tx.get("source") or tx.get("source_url"))
        tx["incidences"] = compute_incidences(tx, hs, hp, tid in link_data)

    return {"transactions": txs, "total": total}


@router.get("/stats")
async def transaction_stats(user=Depends(get_current_user)):
    f = {"deleted": {"$ne": True}}
    total = await db.transactions_normalized.count_documents(f)
    imported = await db.transactions_normalized.count_documents({**f, "source_type": "file_import"})
    manual = await db.transactions_normalized.count_documents({**f, "source_type": "manual"})
    pending_review = await db.transactions_normalized.count_documents({**f, "review_status": "pending"})
    possible_dupes = await db.transaction_dedupe_candidates.count_documents({"review_status": "pending"})
    dupes_merged = await db.transaction_dedupe_candidates.count_documents({"review_status": "merged"})
    matched = await db.transaction_company_links.count_documents({"match_status": "manual_confirmed"})
    ambiguous = await db.transaction_company_links.count_documents({"match_status": {"$in": ["auto_ambiguous_candidate", "auto_strong_candidate"]}})
    sectors_pending = await db.transactions_normalized.count_documents({**f, "sector_mapping_status": {"$in": [None, "pending"]}})
    ready = await db.transactions_normalized.count_documents({**f, "publish_status": "ready_to_publish"})
    published = await db.transactions_normalized.count_documents({**f, "publish_status": "published"})
    approved_cis = await db.transactions_normalized.count_documents({**f, "publish_status": "approved_for_cis"})
    visible_in_cis = await db.transactions_normalized.count_documents({**f, "visible_in_cis": True})

    return {
        "total": total, "imported": imported, "manual": manual,
        "pending_review": pending_review, "possible_duplicates": possible_dupes,
        "duplicates_merged": dupes_merged, "entities_matched": matched,
        "entities_ambiguous": ambiguous, "sectors_pending": sectors_pending,
        "ready_to_publish": ready, "published": published,
        "approved_for_cis": approved_cis, "visible_in_cis": visible_in_cis,
    }


# Fixed-path GET routes MUST come before /{tx_id} to avoid route conflicts
@router.get("/export")
async def export_transactions(
    format: str = Query("json", regex="^(json|excel)$"),
    publish_status: Optional[str] = None,
    user=Depends(get_current_user)
):
    query = {"deleted": {"$ne": True}}
    if publish_status: query["publish_status"] = publish_status

    txs = await db.transactions_normalized.find(query, {"_id": 0}).to_list(10000)

    if format == "json":
        import json
        return Response(content=json.dumps(txs, indent=2, default=str),
                       media_type="application/json",
                       headers={"Content-Disposition": "attachment; filename=transactions.json"})
    else:
        import pandas as pd
        df = pd.json_normalize(txs)
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="xlsxwriter")
        buf.seek(0)
        return Response(content=buf.getvalue(),
                       media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       headers={"Content-Disposition": "attachment; filename=transactions.xlsx"})


# ══════════════════════════════════════════
# TAXONOMY FOR SELECTORS
# ══════════════════════════════════════════

@router.get("/taxonomy-options")
async def taxonomy_options():
    """Get CIS taxonomy for category/subcategory selectors."""
    categories = await db.taxonomy_categories.find(
        {"active": True}, {"_id": 0, "id": 1, "name": 1}
    ).sort("order", 1).to_list(100)

    result = []
    for cat in categories:
        subs = await db.taxonomy_subcategories.find(
            {"category_id": cat["id"], "active": True}, {"_id": 0, "name": 1}
        ).sort("order", 1).to_list(100)
        result.append({"name": cat["name"], "subcategories": [s["name"] for s in subs]})

    return {"categories": result}


# ══════════════════════════════════════════
# ANALYTICS (aggregated M&A Radar data)
# ══════════════════════════════════════════

@router.get("/analytics")
async def get_analytics(user=Depends(get_current_user)):
    """Aggregated analytics for the M&A Radar. Only counts reviewed/ready transactions."""
    f = {"deleted": {"$ne": True}, "review_status": {"$in": ["reviewed", "approved"]}}

    # ── By category ──
    cat_pipeline = [
        {"$match": {**f, "cis_category_suggested": {"$ne": None}}},
        {"$group": {
            "_id": "$cis_category_suggested",
            "count": {"$sum": 1},
            "with_amount": {"$sum": {"$cond": [{"$ne": ["$value_eurm", None]}, 1, 0]}},
            "total_eurm": {"$sum": {"$ifNull": ["$value_eurm", 0]}},
            "published": {"$sum": {"$cond": [{"$eq": ["$publish_status", "approved_for_cis"]}, 1, 0]}},
        }},
        {"$sort": {"count": -1}},
    ]
    by_category = await db.transactions_normalized.aggregate(cat_pipeline).to_list(50)

    # ── By type ──
    type_pipeline = [
        {"$match": f},
        {"$group": {"_id": "$transaction_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_type = await db.transactions_normalized.aggregate(type_pipeline).to_list(20)

    # ── By year ──
    year_pipeline = [
        {"$match": {**f, "year": {"$ne": None}}},
        {"$group": {
            "_id": "$year",
            "count": {"$sum": 1},
            "with_amount": {"$sum": {"$cond": [{"$ne": ["$value_eurm", None]}, 1, 0]}},
            "total_eurm": {"$sum": {"$ifNull": ["$value_eurm", 0]}},
        }},
        {"$sort": {"_id": -1}},
    ]
    by_year = await db.transactions_normalized.aggregate(year_pipeline).to_list(20)

    # ── By country ──
    country_pipeline = [
        {"$match": {**f, "geography_primary": {"$ne": None}}},
        {"$group": {"_id": "$geography_primary", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
    ]
    by_country = await db.transactions_normalized.aggregate(country_pipeline).to_list(15)

    # ── Top buyers ──
    buyer_pipeline = [
        {"$match": {**f, "buyer_name": {"$ne": None}, "buyer_name": {"$ne": ""}}},
        {"$group": {
            "_id": "$buyer_name",
            "count": {"$sum": 1},
            "total_eurm": {"$sum": {"$ifNull": ["$value_eurm", 0]}},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 15},
    ]
    top_buyers = await db.transactions_normalized.aggregate(buyer_pipeline).to_list(15)

    # ── Top targets (most acquired) ──
    target_pipeline = [
        {"$match": {**f, "target_name": {"$ne": None}}},
        {"$group": {"_id": "$target_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_targets = await db.transactions_normalized.aggregate(target_pipeline).to_list(10)

    # ── Amount distribution ──
    amount_pipeline = [
        {"$match": f},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "with_amount": {"$sum": {"$cond": [{"$ne": ["$value_eurm", None]}, 1, 0]}},
            "undisclosed": {"$sum": {"$cond": [{"$eq": ["$value_eurm", None]}, 1, 0]}},
            "total_eurm": {"$sum": {"$ifNull": ["$value_eurm", 0]}},
            "avg_eurm": {"$avg": "$value_eurm"},
        }},
    ]
    amount_stats_raw = await db.transactions_normalized.aggregate(amount_pipeline).to_list(1)
    amount_stats = amount_stats_raw[0] if amount_stats_raw else {"total": 0, "with_amount": 0, "undisclosed": 0, "total_eurm": 0, "avg_eurm": 0}
    amount_stats.pop("_id", None)
    if amount_stats.get("avg_eurm"):
        amount_stats["avg_eurm"] = round(amount_stats["avg_eurm"], 2)

    # ── Publication funnel ──
    funnel_pipeline = [
        {"$match": f},
        {"$group": {"_id": "$publish_status", "count": {"$sum": 1}}},
    ]
    funnel_raw = await db.transactions_normalized.aggregate(funnel_pipeline).to_list(10)
    funnel = {item["_id"]: item["count"] for item in funnel_raw}

    return {
        "by_category": [{"category": r["_id"], "count": r["count"], "with_amount": r["with_amount"], "total_eurm": round(r["total_eurm"], 2), "published": r["published"]} for r in by_category],
        "by_type": [{"type": r["_id"], "count": r["count"]} for r in by_type],
        "by_year": [{"year": r["_id"], "count": r["count"], "with_amount": r["with_amount"], "total_eurm": round(r["total_eurm"], 2)} for r in by_year],
        "by_country": [{"country": r["_id"], "count": r["count"]} for r in by_country],
        "top_buyers": [{"buyer": r["_id"], "count": r["count"], "total_eurm": round(r["total_eurm"], 2)} for r in top_buyers],
        "top_targets": [{"target": r["_id"], "count": r["count"]} for r in top_targets],
        "amount_stats": amount_stats,
        "funnel": funnel,
    }


# ══════════════════════════════════════════
# VIEW ENDPOINTS (for 4-view navigation)
# ══════════════════════════════════════════

async def _batch_enrich(txs: list) -> list:
    """Batch-enrich transactions with visible_status, sources, incidences. 3 queries total."""
    if not txs:
        return txs
    tx_ids = [tx["transaction_id"] for tx in txs]

    src_pipeline = [
        {"$match": {"transaction_id": {"$in": tx_ids}}},
        {"$group": {"_id": "$transaction_id", "count": {"$sum": 1},
                     "primary_pub": {"$max": {"$cond": [{"$eq": ["$is_primary", True]}, "$publisher", None]}}}}
    ]
    src_data = {r["_id"]: r for r in await db.transaction_sources.aggregate(src_pipeline).to_list(len(tx_ids) + 1)}

    link_pipeline = [
        {"$match": {"transaction_id": {"$in": tx_ids}, "entity_role": "target",
                     "match_status": {"$in": ["manual_confirmed", "auto_strong_candidate", "needs_new_company", "external_entity"]}}},
        {"$group": {"_id": "$transaction_id"}}
    ]
    link_data = {r["_id"] for r in await db.transaction_company_links.aggregate(link_pipeline).to_list(len(tx_ids) + 1)}

    for tx in txs:
        tid = tx["transaction_id"]
        ps = tx.get("publish_status", "not_published")
        sync = tx.get("cis_sync_status")
        if tx.get("deleted"): vs = "archived"
        elif ps == "approved_for_cis" or tx.get("visible_in_cis"): vs = "pending_sync" if sync == "pending_update" else "published_in_cis"
        elif ps == "removed_from_cis": vs = "withdrawn_from_cis"
        elif ps == "ready_to_publish": vs = "ready_for_cis"
        elif tx.get("review_status") in ("reviewed", "approved"): vs = "needs_review"
        elif not tx.get("target_name") or not (tx.get("announcement_date") or tx.get("year")): vs = "incomplete"
        else: vs = "draft"
        tx["visible_status"] = vs

        src = src_data.get(tid, {})
        sc = src.get("count", 0)
        tx["sources_count"] = sc
        tx["primary_source_publisher"] = src.get("primary_pub") or tx.get("source")
        hs = sc > 0 or bool(tx.get("source") or tx.get("source_url"))
        hp = src.get("primary_pub") is not None or bool(tx.get("source") or tx.get("source_url"))
        tx["incidences"] = compute_incidences(tx, hs, hp, tid in link_data)

    return txs


@router.get("/views/needs-review")
async def view_needs_review(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """Transactions that need editorial review (review_status=pending)."""
    query = {"deleted": {"$ne": True}, "review_status": {"$in": ["pending", "needs_review"]}}
    total = await db.transactions_normalized.count_documents(query)
    txs = await db.transactions_normalized.find(query, {"_id": 0}).sort("updated_at", -1).skip(offset).limit(limit).to_list(limit)
    await _batch_enrich(txs)
    return {"transactions": txs, "total": total}


@router.get("/views/ready-for-cis")
async def view_ready_for_cis(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """Transactions marked as ready for CIS publishing."""
    query = {"deleted": {"$ne": True}, "publish_status": "ready_to_publish"}
    total = await db.transactions_normalized.count_documents(query)
    txs = await db.transactions_normalized.find(query, {"_id": 0}).sort("updated_at", -1).skip(offset).limit(limit).to_list(limit)
    await _batch_enrich(txs)
    return {"transactions": txs, "total": total}


@router.get("/views/published")
async def view_published(
    limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """Transactions published in CIS (approved_for_cis OR visible_in_cis)."""
    pub_query = {
        "deleted": {"$ne": True},
        "$or": [{"publish_status": "approved_for_cis"}, {"visible_in_cis": True}]
    }
    txs = await db.transactions_normalized.find(
        pub_query, {"_id": 0}
    ).sort("updated_at", -1).skip(offset).limit(limit).to_list(limit)
    total = await db.transactions_normalized.count_documents(pub_query)
    await _batch_enrich(txs)
    return {"transactions": txs, "total": total}


# ══════════════════════════════════════════
# SOURCES CRUD
# ══════════════════════════════════════════

@router.get("/sources/{tx_id}")
async def list_sources(tx_id: str, user=Depends(get_current_user)):
    """List all sources for a transaction."""
    sources = await db.transaction_sources.find(
        {"transaction_id": tx_id}, {"_id": 0}
    ).sort([("is_primary", -1), ("created_at", -1)]).to_list(50)
    return {"sources": sources}


@router.post("/sources/{tx_id}")
async def create_source(tx_id: str, req: SourceCreate, user=Depends(get_current_user)):
    """Add a source to a transaction."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    now = now_iso()
    source_id = f"src_{new_id()[:12]}"

    # If marking as primary, unset other primaries
    if req.is_primary:
        await db.transaction_sources.update_many(
            {"transaction_id": tx_id, "is_primary": True},
            {"$set": {"is_primary": False, "updated_at": now}}
        )

    source = {
        "source_id": source_id,
        "transaction_id": tx_id,
        "title": req.title,
        "publisher": req.publisher,
        "url": req.url,
        "published_at": req.published_at,
        "source_type": req.source_type,
        "is_primary": req.is_primary,
        "summary": req.summary,
        "notes": req.notes,
        "created_at": now,
        "updated_at": now,
    }
    await db.transaction_sources.insert_one({**source})

    # Mark pending_update if published
    await _mark_pending_update_if_published(tx_id, "sources_changed", user)

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "source_added",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {"source_id": source_id, "publisher": req.publisher, "url": req.url},
    })

    return source


@router.put("/sources/{tx_id}/{source_id}")
async def update_source(tx_id: str, source_id: str, req: SourceUpdate, user=Depends(get_current_user)):
    """Update a source."""
    existing = await db.transaction_sources.find_one({"source_id": source_id, "transaction_id": tx_id})
    if not existing:
        raise HTTPException(404, "Source not found")

    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")

    now = now_iso()

    if update.get("is_primary"):
        await db.transaction_sources.update_many(
            {"transaction_id": tx_id, "is_primary": True, "source_id": {"$ne": source_id}},
            {"$set": {"is_primary": False, "updated_at": now}}
        )

    update["updated_at"] = now
    await db.transaction_sources.update_one({"source_id": source_id}, {"$set": update})

    await _mark_pending_update_if_published(tx_id, "sources_changed", user)
    return await db.transaction_sources.find_one({"source_id": source_id}, {"_id": 0})


@router.delete("/sources/{tx_id}/{source_id}")
async def delete_source(tx_id: str, source_id: str, user=Depends(get_current_user)):
    """Delete a source."""
    existing = await db.transaction_sources.find_one({"source_id": source_id, "transaction_id": tx_id})
    if not existing:
        raise HTTPException(404, "Source not found")

    await db.transaction_sources.delete_one({"source_id": source_id})

    await _mark_pending_update_if_published(tx_id, "sources_changed", user)

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "source_removed",
        "changed_by": user.get("email", user["id"]), "changed_at": now_iso(),
        "new_values": {"source_id": source_id, "publisher": existing.get("publisher")},
    })
    return {"status": "deleted"}


async def _mark_pending_update_if_published(tx_id: str, reason: str, user: dict):
    """If the transaction is published, mark as pending_update."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0, "publish_status": 1})
    if tx and tx.get("publish_status") == "approved_for_cis":
        await db.transactions_normalized.update_one(
            {"transaction_id": tx_id},
            {"$set": {"cis_sync_status": "pending_update", "updated_at": now_iso()}}
        )


# ══════════════════════════════════════════
# CIS PUBLICATION
# ══════════════════════════════════════════

async def _validate_for_cis(tx: dict) -> dict:
    """Validate a transaction meets all CIS publication requirements."""
    missing = []
    warnings = []
    score = 0.0
    max_score = 0.0
    tx_id = tx["transaction_id"]

    # Required: target_name
    max_score += 15
    if tx.get("target_name"):
        score += 15
    else:
        missing.append("Falta nombre del target")

    # Required: date or year
    max_score += 10
    if tx.get("announcement_date") or tx.get("year"):
        score += 10
    else:
        missing.append("Falta fecha de anuncio o año")

    # Required: transaction_type
    max_score += 10
    if tx.get("transaction_type") and tx["transaction_type"] != "other":
        score += 10
    elif tx.get("transaction_type") == "other":
        score += 5
        warnings.append("Tipo de operacion es 'other' — considerar especificar")
    else:
        missing.append("Falta tipo de operacion")

    # Required: CIS category or outside_cis_taxonomy
    max_score += 15
    if tx.get("cis_category_suggested"):
        score += 15
    elif tx.get("outside_cis_taxonomy"):
        score += 12
        warnings.append("Marcada como fuera de taxonomia CIS — no alimentara analisis por categoria")
    else:
        missing.append("Falta categoria CIS")

    # Required: source (check transaction_sources first, fallback to legacy fields)
    max_score += 10
    src_count = await db.transaction_sources.count_documents({"transaction_id": tx_id})
    primary_src = await db.transaction_sources.find_one(
        {"transaction_id": tx_id, "is_primary": True}, {"_id": 0}
    )
    has_source = src_count > 0 or bool(tx.get("source") or tx.get("source_url"))
    has_primary = primary_src is not None or bool(tx.get("source") or tx.get("source_url"))

    if has_source and has_primary:
        score += 10
    elif has_source and not has_primary:
        score += 5
        missing.append("Falta fuente principal — selecciona una fuente como principal")
    else:
        missing.append("Falta al menos una fuente asociada")

    # Required: summary
    max_score += 10
    if tx.get("summary"):
        score += 10
    else:
        missing.append("Falta descripcion (summary)")

    # Required: deduplication resolved
    max_score += 10
    if tx.get("dedupe_status") in ("unique", "confirmed_duplicate"):
        score += 10
    elif tx.get("dedupe_status") == "possible_duplicate":
        missing.append("Tiene duplicados pendientes de resolver")
    else:
        score += 5
        warnings.append("Estado de deduplicacion no verificado explicitamente")

    # Required: review status
    max_score += 10
    if tx.get("review_status") in ("reviewed", "approved"):
        score += 10
    else:
        missing.append(f"Review editorial pendiente — estado actual: '{tx.get('review_status', 'pending')}'")

    # Required: target entity reviewed
    max_score += 10
    target_link = await db.transaction_company_links.find_one(
        {"transaction_id": tx_id, "entity_role": "target",
         "match_status": {"$in": ["manual_confirmed", "auto_strong_candidate", "needs_new_company", "external_entity"]}},
        {"_id": 0}
    )
    if target_link:
        score += 10
    else:
        has_any_link = await db.transaction_company_links.find_one(
            {"transaction_id": tx_id, "entity_role": "target"}, {"_id": 0}
        )
        if has_any_link:
            missing.append("Target vinculado pero no confirmado — revisar vinculacion")
        else:
            missing.append("Target no vinculado — vincular, crear nueva empresa o marcar como entidad externa")

    quality_score = round(score / max_score, 3) if max_score > 0 else 0.0

    # Warnings for optional fields
    if not tx.get("buyer_name"):
        warnings.append("Buyer ausente — recomendable para M&A Radar")
    if not tx.get("geography_primary"):
        warnings.append("Pais ausente — recomendable para filtros CIS")
    if not tx.get("value_eurm"):
        warnings.append("Importe no disponible — normal en muchas operaciones")
    if not tx.get("strategic_rationale"):
        warnings.append("Sin lectura estrategica — recomendable para ficha CIS")

    return {
        "transaction_id": tx_id,
        "can_approve": len(missing) == 0,
        "missing_requirements": missing,
        "warnings": warnings,
        "quality_score": quality_score,
    }


@router.post("/publish-all-cis")
async def publish_all_to_cis(user=Depends(get_current_user)):
    """Mass pre-publish: set visible_in_cis=true for all non-deleted transactions."""
    now = now_iso()
    email = user.get("email", user["id"])
    result = await db.transactions_normalized.update_many(
        {"deleted": {"$ne": True}, "visible_in_cis": {"$ne": True}},
        {"$set": {"visible_in_cis": True, "updated_at": now}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": "bulk:publish_all",
        "action": "mass_publish_cis", "changed_by": email, "changed_at": now,
        "new_values": {"count": result.modified_count},
    })
    return {"status": "published", "count": result.modified_count}


@router.get("/approved-for-cis")
async def get_approved_for_cis(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    year: Optional[int] = None,
    category: Optional[str] = None,
    transaction_type: Optional[str] = None,
    country: Optional[str] = None,
    buyer: Optional[str] = None,
    seller: Optional[str] = None,
    target: Optional[str] = None,
    amount_known: Optional[bool] = None,
    source: Optional[str] = None,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """Public CIS endpoint — returns approved OR visible_in_cis transactions."""
    query = {
        "$or": [
            {"publish_status": "approved_for_cis"},
            {"visible_in_cis": True},
        ],
        "deleted": {"$ne": True},
    }

    if date_from:
        query.setdefault("announcement_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("announcement_date", {})["$lte"] = date_to
    if year:
        query["year"] = year
    if category:
        query["cis_category_suggested"] = {"$regex": category, "$options": "i"}
    if transaction_type:
        query["transaction_type"] = transaction_type
    if country:
        query["geography_primary"] = {"$regex": country, "$options": "i"}
    if buyer:
        query["buyer_name"] = {"$regex": buyer, "$options": "i"}
    if seller:
        query["seller_name"] = {"$regex": seller, "$options": "i"}
    if target:
        query["target_name"] = {"$regex": target, "$options": "i"}
    if amount_known is True:
        query["value_eurm"] = {"$ne": None}
    elif amount_known is False:
        query["$or"] = [{"value_eurm": None}, {"value_eurm": {"$exists": False}}]
    if source:
        query["$or"] = [
            {"source": {"$regex": source, "$options": "i"}},
            {"source_url": {"$regex": source, "$options": "i"}},
        ]

    total = await db.transactions_normalized.count_documents(query)
    txs = await db.transactions_normalized.find(query, {"_id": 0}).sort("announcement_date", -1).skip(offset).limit(limit).to_list(limit)

    items = []
    for tx in txs:
        # Determine amount_status
        amt_status = tx.get("amount_status", "undisclosed")
        if tx.get("value_eurm"):
            if amt_status == "undisclosed":
                amt_status = "confirmed" if tx.get("value_disclosed") else "estimated"
            amount_label = f"{tx['value_eurm']}M EUR"
        else:
            amt_status = "undisclosed"
            amount_label = "ND"

        # Get linked entities
        links = await db.transaction_company_links.find(
            {"transaction_id": tx["transaction_id"],
             "match_status": {"$in": ["manual_confirmed", "auto_strong_candidate", "needs_new_company", "external_entity"]}},
            {"_id": 0, "entity_role": 1, "raw_entity_name": 1, "matched_company_name": 1,
             "matched_company_id": 1, "matched_cis_company_id": 1, "match_status": 1}
        ).to_list(10)

        linked_entities = [
            {"role": lnk["entity_role"],
             "name": lnk.get("raw_entity_name"),
             "matched_company_name": lnk.get("matched_company_name"),
             "company_id": lnk.get("matched_company_id"),
             "cis_company_id": lnk.get("matched_cis_company_id"),
             "is_external": lnk.get("match_status") == "external_entity"}
            for lnk in links
        ]

        # Get sources
        tx_sources = await db.transaction_sources.find(
            {"transaction_id": tx["transaction_id"]},
            {"_id": 0, "source_id": 0, "transaction_id": 0, "notes": 0}
        ).sort([("is_primary", -1), ("created_at", 1)]).to_list(20)

        primary_source_obj = next((s for s in tx_sources if s.get("is_primary")), None)

        # Retrocompatible source_name/source_url: primary_source > legacy fields
        retro_source_name = None
        retro_source_url = None
        if primary_source_obj:
            retro_source_name = primary_source_obj.get("publisher")
            retro_source_url = primary_source_obj.get("url")
        elif tx.get("source") or tx.get("source_url"):
            retro_source_name = tx.get("source")
            retro_source_url = tx.get("source_url")

        # Determine classification_origin
        sug = await db.transaction_classification_suggestions.find_one(
            {"transaction_id": tx["transaction_id"], "status": "accepted"}, {"_id": 0, "confidence": 1}
        )
        if sug:
            classification_origin = "ai_accepted"
            classification_confidence = sug.get("confidence", 0)
        elif tx.get("source_type") == "file_import":
            classification_origin = "imported"
            classification_confidence = None
        else:
            classification_origin = "manual"
            classification_confidence = None

        items.append({
            "id": tx["transaction_id"],
            "title": f"{tx.get('buyer_name', '?')} adquiere {tx.get('target_name', '?')}" if tx.get("buyer_name") else tx.get("target_name", "?"),
            "transaction_date": tx.get("announcement_date"),
            "year": tx.get("year"),
            "target_name": tx.get("target_name"),
            "buyer_name": tx.get("buyer_name"),
            "seller_name": tx.get("seller_name"),
            "transaction_type": tx.get("transaction_type"),
            "cis_category": tx.get("cis_category_suggested"),
            "cis_subcategory": tx.get("cis_subcategory_suggested"),
            "outside_cis_taxonomy": tx.get("outside_cis_taxonomy", False),
            # Economic data
            "amount": tx.get("value_eurm"),
            "amount_label": amount_label,
            "amount_status": amt_status,
            "currency": "EUR",
            "valuation_basis": tx.get("valuation_basis"),
            "stake_acquired_percent": tx.get("stake_acquired_percent"),
            "includes_debt": tx.get("includes_debt"),
            "includes_earnout": tx.get("includes_earnout"),
            "revenue_eurm": tx.get("revenue_eurm"),
            "ebitda_eurm": tx.get("ebitda_eurm"),
            "ev_eurm": tx.get("ev_eurm"),
            "ev_sales_multiple": tx.get("ve_sales"),
            "ev_ebitda_multiple": tx.get("ve_ebitda"),
            "multiple_quality": tx.get("multiple_quality"),
            "multiple_notes": tx.get("multiple_notes"),
            "financial_year_used": tx.get("financial_year_used"),
            # Geography
            "country": tx.get("geography_primary"),
            # Retrocompatible sources
            "source_name": retro_source_name,
            "source_url": retro_source_url,
            # Structured sources
            "primary_source": primary_source_obj,
            "sources": tx_sources,
            # Editorial
            "summary": tx.get("summary"),
            "strategic_rationale": tx.get("strategic_rationale"),
            # Quality & linking
            "quality_status": "approved_for_cis",
            "linked_entities": linked_entities,
            "classification_origin": classification_origin,
            "classification_confidence": classification_confidence,
            "last_updated": tx.get("updated_at"),
        })

    return {
        "items": items,
        "total": total,
        "last_updated": now_iso(),
    }


@router.get("/audit-global")
async def get_global_audit(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Global audit log for the Logs tab."""
    query = {}
    if action:
        query["action"] = action
    total = await db.transaction_audit_logs.count_documents(query)
    logs = await db.transaction_audit_logs.find(query, {"_id": 0}).sort("changed_at", -1).skip(offset).limit(limit).to_list(limit)
    return {"logs": logs, "total": total}


# ══════════════════════════════════════════
# BATCH CLASSIFICATION
# ══════════════════════════════════════════

BATCH_MAX_LIMIT = 50

from pydantic import BaseModel as _BM
from typing import List as _TL

class BatchClassificationRequest(_BM):
    limit: int = 20
    only_without_category: bool = True
    only_without_existing_suggestion: bool = True
    dry_run: bool = False


@router.post("/classification-suggestions/batch")
async def batch_classification(req: BatchClassificationRequest, user=Depends(get_current_user)):
    """Generate AI classification suggestions for multiple pending transactions."""
    effective_limit = min(req.limit, BATCH_MAX_LIMIT)
    now = now_iso()
    email = user.get("email", user["id"])

    # Build query for candidate transactions
    query = {"deleted": {"$ne": True}}
    if req.only_without_category:
        query["$or"] = [
            {"cis_category_suggested": None},
            {"cis_category_suggested": ""},
            {"cis_category_suggested": {"$exists": False}},
        ]

    candidates = await db.transactions_normalized.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(effective_limit * 2).to_list(effective_limit * 2)

    # Filter by existing suggestion if needed
    items = []
    selected = []
    for tx in candidates:
        if len(selected) >= effective_limit:
            break
        tx_id = tx["transaction_id"]

        if req.only_without_existing_suggestion:
            existing = await db.transaction_classification_suggestions.find_one(
                {"transaction_id": tx_id, "status": "suggested", "validation_status": "valid"}
            )
            if existing:
                items.append({"transaction_id": tx_id, "status": "skipped", "suggestion_id": None,
                              "reason": "Ya tiene sugerencia activa valida",
                              "target_name": tx.get("target_name")})
                continue

        selected.append(tx)
        items.append({"transaction_id": tx_id, "status": "pending", "suggestion_id": None,
                       "reason": None, "target_name": tx.get("target_name")})

    # Dry run: return candidates without calling LLM
    if req.dry_run:
        for item in items:
            if item["status"] == "pending":
                item["status"] = "candidate"
        return {
            "processed": 0, "suggestions_created": 0,
            "skipped": sum(1 for i in items if i["status"] == "skipped"),
            "errors": 0, "dry_run": True,
            "candidates": sum(1 for i in items if i["status"] == "candidate"),
            "max_limit": BATCH_MAX_LIMIT,
            "items": items,
        }

    # Real run: call LLM for each candidate
    created = 0
    errors = 0

    for idx, tx in enumerate(selected):
        tx_id = tx["transaction_id"]
        item = next(i for i in items if i["transaction_id"] == tx_id and i["status"] == "pending")

        try:
            result = await suggest_classification(tx)
            suggestion_id = f"sug_{new_id()[:12]}"

            suggestion = {
                "suggestion_id": suggestion_id,
                "transaction_id": tx_id,
                "suggested_category": result["suggested_category"],
                "suggested_subcategory": result["suggested_subcategory"],
                "confidence": result["confidence"],
                "confidence_label": result["confidence_label"],
                "reasoning": result["reasoning"],
                "signals_used": result["signals_used"],
                "alternative_suggestions": result["alternative_suggestions"],
                "model_used": result["model_used"],
                "prompt_version": result["prompt_version"],
                "raw_model_response": result["raw_model_response"],
                "validation_status": result["validation_status"],
                "validation_errors": result.get("validation_errors", []),
                "status": "suggested",
                "requires_human_review": True,
                "batch_id": None,
                "accepted_by": None, "accepted_at": None,
                "rejected_by": None, "rejected_at": None,
                "created_by": email,
                "created_at": now_iso(), "updated_at": now_iso(),
            }
            await db.transaction_classification_suggestions.insert_one({**suggestion})

            await db.transaction_audit_logs.insert_one({
                "log_id": new_id(), "transaction_id": tx_id,
                "action": "classification_suggested",
                "changed_by": email, "changed_at": now_iso(),
                "new_values": {
                    "suggestion_id": suggestion_id,
                    "category": result["suggested_category"],
                    "subcategory": result["suggested_subcategory"],
                    "confidence": result["confidence_label"],
                    "validation": result["validation_status"],
                    "source": "batch",
                },
            })

            item["status"] = "suggested"
            item["suggestion_id"] = suggestion_id
            item["suggested_category"] = result["suggested_category"]
            item["suggested_subcategory"] = result["suggested_subcategory"]
            item["confidence_label"] = result["confidence_label"]
            item["validation_status"] = result["validation_status"]
            created += 1

        except Exception as e:
            logger.error(f"Batch classification error for {tx_id}: {e}")
            item["status"] = "error"
            item["reason"] = str(e)[:200]
            errors += 1

    skipped = sum(1 for i in items if i["status"] == "skipped")

    # Global audit log for the batch
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": f"batch:{now}",
        "action": "batch_classification_run",
        "changed_by": email, "changed_at": now_iso(),
        "new_values": {
            "processed": len(selected), "suggestions_created": created,
            "skipped": skipped, "errors": errors,
            "params": req.model_dump(),
        },
    })

    return {
        "processed": len(selected), "suggestions_created": created,
        "skipped": skipped, "errors": errors, "dry_run": False,
        "max_limit": BATCH_MAX_LIMIT,
        "items": items,
    }


@router.get("/classification-suggestions/review")
async def classification_review_queue(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """Get pending classification suggestions for review."""
    query = {"status": "suggested", "validation_status": "valid"}
    total = await db.transaction_classification_suggestions.count_documents(query)
    suggestions = await db.transaction_classification_suggestions.find(
        query, {"_id": 0, "raw_model_response": 0}
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)

    # Enrich with transaction data
    for s in suggestions:
        tx = await db.transactions_normalized.find_one(
            {"transaction_id": s["transaction_id"]},
            {"_id": 0, "target_name": 1, "buyer_name": 1, "announcement_date": 1,
             "geography_primary": 1, "sector_original": 1, "transaction_type": 1}
        )
        s["transaction"] = tx

    return {"suggestions": suggestions, "total": total}


# ══════════════════════════════════════════
# ENTITY MATCHING
# ══════════════════════════════════════════

@router.get("/matching/stats")
async def matching_stats(user=Depends(get_current_user)):
    """Statistics for the entity matching pipeline."""
    total_links = await db.transaction_company_links.count_documents({})
    strong = await db.transaction_company_links.count_documents({"match_status": "auto_strong_candidate"})
    ambiguous = await db.transaction_company_links.count_documents({"match_status": "auto_ambiguous_candidate"})
    unmatched = await db.transaction_company_links.count_documents({"match_status": "unmatched"})
    confirmed = await db.transaction_company_links.count_documents({"match_status": "manual_confirmed"})
    rejected = await db.transaction_company_links.count_documents({"match_status": "manual_rejected"})
    needs_new = await db.transaction_company_links.count_documents({"match_status": "needs_new_company"})

    txs_needing_review = await db.transactions_normalized.count_documents(
        {"matching_status": "needs_review", "deleted": {"$ne": True}}
    )

    return {
        "total_links": total_links,
        "auto_strong_candidate": strong,
        "auto_ambiguous_candidate": ambiguous,
        "unmatched": unmatched,
        "manual_confirmed": confirmed,
        "manual_rejected": rejected,
        "needs_new_company": needs_new,
        "transactions_needing_review": txs_needing_review,
    }


@router.get("/matching/pending")
async def matching_pending(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = None,
    user=Depends(get_current_user)
):
    """List entity links that need human review."""
    query = {}
    if status_filter:
        query["match_status"] = status_filter
    else:
        query["match_status"] = {"$in": ["auto_strong_candidate", "auto_ambiguous_candidate", "unmatched"]}

    total = await db.transaction_company_links.count_documents(query)
    links = await db.transaction_company_links.find(
        query, {"_id": 0}
    ).sort([("match_status", 1), ("match_confidence", -1)]).skip(offset).limit(limit).to_list(limit)

    # Enrich with transaction data
    for link in links:
        tx = await db.transactions_normalized.find_one(
            {"transaction_id": link["transaction_id"]},
            {"_id": 0, "target_name": 1, "buyer_name": 1, "seller_name": 1,
             "announcement_date": 1, "geography_primary": 1, "sector_original": 1,
             "transaction_type": 1}
        )
        link["transaction"] = tx

    return {"links": links, "total": total}


@router.get("/matching/search")
async def matching_search(q: str = Query(..., min_length=2), user=Depends(get_current_user)):
    """Search CIS companies for manual entity linking."""
    results = await db.agency_results.find(
        {"$or": [
            {"company_name": {"$regex": q, "$options": "i"}},
            {"cif": {"$regex": q, "$options": "i"}},
            {"input_url": {"$regex": q, "$options": "i"}},
        ], "status": "completed"},
        {"_id": 0, "id": 1, "company_name": 1, "input_url": 1, "cif": 1,
         "cis_company_id": 1, "category": 1, "subcategory": 1, "country": 1}
    ).limit(20).to_list(20)
    return {"results": results}


@router.post("/matching/run-all")
async def run_matching_all(user=Depends(get_current_user)):
    """Run entity matching for all transactions missing links."""
    txs = await db.transactions_normalized.find(
        {"deleted": {"$ne": True}, "matching_status": {"$in": ["pending", "needs_review", None]}},
        {"_id": 0}
    ).to_list(500)

    processed = 0
    for tx in txs:
        await run_matching_for_transaction(db, tx)
        processed += 1

    return {"processed": processed}


@router.post("/matching/{link_id}/confirm")
async def confirm_match(link_id: str, user=Depends(get_current_user)):
    """Confirm a proposed entity match."""
    link = await db.transaction_company_links.find_one({"link_id": link_id})
    if not link:
        raise HTTPException(404, "Link not found")

    now = now_iso()
    await db.transaction_company_links.update_one(
        {"link_id": link_id},
        {"$set": {
            "match_status": "manual_confirmed",
            "confirmed_by": user.get("email", user["id"]),
            "confirmed_at": now,
            "updated_at": now,
        }}
    )

    # Audit
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": link["transaction_id"],
        "action": "entity_match_confirmed",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {
            "entity_role": link["entity_role"],
            "matched_company": link.get("matched_company_name"),
            "method": link.get("match_method"),
        },
    })

    # Recompute matching_status for the transaction
    await _recompute_matching_status(link["transaction_id"])
    return {"status": "manual_confirmed"}


@router.post("/matching/{link_id}/reject")
async def reject_match(link_id: str, user=Depends(get_current_user)):
    """Reject a proposed entity match."""
    link = await db.transaction_company_links.find_one({"link_id": link_id})
    if not link:
        raise HTTPException(404, "Link not found")

    now = now_iso()
    await db.transaction_company_links.update_one(
        {"link_id": link_id},
        {"$set": {
            "match_status": "manual_rejected",
            "matched_company_id": None,
            "matched_company_name": None,
            "confirmed_by": user.get("email", user["id"]),
            "confirmed_at": now,
            "updated_at": now,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": link["transaction_id"],
        "action": "entity_match_rejected",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {"entity_role": link["entity_role"]},
    })

    await _recompute_matching_status(link["transaction_id"])
    return {"status": "manual_rejected"}


@router.post("/matching/{link_id}/manual-link")
async def manual_link(link_id: str, company_id: str = Query(...), user=Depends(get_current_user)):
    """Manually link an entity to a specific CIS company."""
    link = await db.transaction_company_links.find_one({"link_id": link_id})
    if not link:
        raise HTTPException(404, "Link not found")

    company = await db.agency_results.find_one(
        {"id": company_id},
        {"_id": 0, "id": 1, "company_name": 1, "input_url": 1, "cis_company_id": 1}
    )
    if not company:
        raise HTTPException(404, "Company not found")

    now = now_iso()
    await db.transaction_company_links.update_one(
        {"link_id": link_id},
        {"$set": {
            "matched_company_id": company["id"],
            "matched_company_name": company.get("company_name"),
            "matched_company_url": company.get("input_url"),
            "matched_cis_company_id": company.get("cis_company_id"),
            "match_status": "manual_confirmed",
            "match_method": "manual",
            "match_confidence": 1.0,
            "match_reasons": ["manual_selection"],
            "confirmed_by": user.get("email", user["id"]),
            "confirmed_at": now,
            "updated_at": now,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": link["transaction_id"],
        "action": "entity_manual_linked",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {
            "entity_role": link["entity_role"],
            "company_id": company["id"],
            "company_name": company.get("company_name"),
        },
    })

    await _recompute_matching_status(link["transaction_id"])
    return {"status": "manual_confirmed", "company_name": company.get("company_name")}


@router.post("/matching/{link_id}/needs-new")
async def mark_needs_new(link_id: str, user=Depends(get_current_user)):
    """Mark an entity as needing a new CIS company to be created."""
    link = await db.transaction_company_links.find_one({"link_id": link_id})
    if not link:
        raise HTTPException(404, "Link not found")

    now = now_iso()
    await db.transaction_company_links.update_one(
        {"link_id": link_id},
        {"$set": {
            "match_status": "needs_new_company",
            "confirmed_by": user.get("email", user["id"]),
            "confirmed_at": now,
            "updated_at": now,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": link["transaction_id"],
        "action": "entity_needs_new_company",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {"entity_role": link["entity_role"], "raw_name": link.get("raw_entity_name")},
    })

    await _recompute_matching_status(link["transaction_id"])
    return {"status": "needs_new_company"}


@router.post("/matching/{link_id}/external-entity")
async def mark_external_entity(link_id: str, user=Depends(get_current_user)):
    """Mark an entity as external (not in CIS universe, but reviewed)."""
    link = await db.transaction_company_links.find_one({"link_id": link_id})
    if not link:
        raise HTTPException(404, "Link not found")

    now = now_iso()
    await db.transaction_company_links.update_one(
        {"link_id": link_id},
        {"$set": {
            "match_status": "external_entity",
            "confirmed_by": user.get("email", user["id"]),
            "confirmed_at": now,
            "updated_at": now,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": link["transaction_id"],
        "action": "entity_marked_external",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {"entity_role": link["entity_role"], "raw_name": link.get("raw_entity_name")},
    })

    await _recompute_matching_status(link["transaction_id"])
    return {"status": "external_entity"}


async def _recompute_matching_status(tx_id: str):
    """Recompute the matching_status for a transaction based on its links."""
    links = await db.transaction_company_links.find(
        {"transaction_id": tx_id}, {"_id": 0, "match_status": 1}
    ).to_list(10)

    resolved_statuses = ("manual_confirmed", "needs_new_company", "external_entity")

    if not links:
        status = "no_entities"
    elif all(lnk["match_status"] in resolved_statuses for lnk in links):
        status = "completed"
    elif any(lnk["match_status"] in ("auto_ambiguous_candidate", "unmatched") for lnk in links):
        status = "needs_review"
    elif all(lnk["match_status"] in (*resolved_statuses, "manual_rejected", "auto_strong_candidate") for lnk in links):
        status = "partial"
    else:
        status = "needs_review"

    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {"matching_status": status, "updated_at": now_iso()}}
    )


@router.get("/{tx_id}")
async def get_transaction(tx_id: str, user=Depends(get_current_user)):
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx: raise HTTPException(404, "Transaction not found")
    # Get links
    links = await db.transaction_company_links.find({"transaction_id": tx_id}, {"_id": 0}).to_list(10)
    tx["company_links"] = links
    # Get dedupe candidates
    dupes = await db.transaction_dedupe_candidates.find(
        {"$or": [{"transaction_id_a": tx_id}, {"transaction_id_b": tx_id}]}, {"_id": 0}
    ).to_list(20)
    tx["dedupe_candidates"] = dupes
    # Get sources
    sources = await db.transaction_sources.find({"transaction_id": tx_id}, {"_id": 0}).sort([("is_primary", -1), ("created_at", -1)]).to_list(20)
    tx["sources"] = sources
    # Visible status (computed)
    tx["visible_status"] = await compute_visible_status(tx, db)
    # Incidences
    src_count = len(sources)
    has_source = src_count > 0 or bool(tx.get("source") or tx.get("source_url"))
    has_primary = any(s.get("is_primary") for s in sources) or bool(tx.get("source") or tx.get("source_url"))
    target_link = next((l for l in links if l.get("entity_role") == "target" and l.get("match_status") in ("manual_confirmed", "auto_strong_candidate", "needs_new_company", "external_entity")), None)
    tx["incidences"] = compute_incidences(tx, has_source, has_primary, target_link is not None)
    return tx


@router.post("")
async def create_transaction(req: TransactionCreate, user=Depends(get_current_user)):
    """Create a manual transaction."""
    raw = req.model_dump()
    normalized = normalize_transaction(raw)
    tx_id = f"tx_{new_id()[:12]}"
    now = now_iso()

    tx = {
        "transaction_id": tx_id, "source_type": "manual",
        **normalized,
        "source": req.source,
        "source_url": req.source_url,
        "dedupe_status": "pending_check", "matching_status": "pending",
        "review_status": "pending", "publish_status": "not_published",
        "sector_mapping_status": "pending" if normalized.get("sector_original") else "not_applicable",
        "deleted": False, "created_by": user.get("email", user["id"]),
        "updated_by": None, "created_at": now, "updated_at": now,
    }
    await db.transactions_normalized.insert_one({**tx})

    # Audit
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "created_manual",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {"target": tx.get("target_name"), "buyer": tx.get("buyer_name")},
    })

    # Run dedupe check in background
    await _check_duplicates(tx_id)

    # Run entity matching
    await run_matching_for_transaction(db, tx)

    return tx


@router.put("/{tx_id}")
async def update_transaction(tx_id: str, req: TransactionUpdate, user=Depends(get_current_user)):
    existing = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not existing: raise HTTPException(404, "Transaction not found")

    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update: raise HTTPException(400, "No fields to update")

    # Re-normalize if key fields changed
    if any(k in update for k in ["target_name", "buyer_name", "seller_name"]):
        if "target_name" in update: update["target_name_normalized"] = normalize_name(update["target_name"])
        if "buyer_name" in update: update["buyer_name_normalized"] = normalize_name(update["buyer_name"])
        if "seller_name" in update: update["seller_name_normalized"] = normalize_name(update["seller_name"])
        update["transaction_key"] = make_transaction_key(
            update.get("target_name", existing.get("target_name")),
            update.get("buyer_name", existing.get("buyer_name")),
            update.get("announcement_date", existing.get("announcement_date")),
            update.get("transaction_type", existing.get("transaction_type"))
        )

    now = now_iso()
    update["updated_at"] = now
    update["updated_by"] = user.get("email", user["id"])

    # If was published in CIS, check if critical fields changed → mark pending_update
    if existing.get("publish_status") == "approved_for_cis":
        changed_critical = any(k in CIS_CRITICAL_FIELDS for k in update if update[k] != existing.get(k))
        if changed_critical:
            update["cis_sync_status"] = "pending_update"
    elif existing.get("publish_status") == "published":
        update["publish_status"] = "needs_republish"

    await db.transactions_normalized.update_one({"transaction_id": tx_id}, {"$set": update})

    # Audit
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "edited",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "previous_values": {k: existing.get(k) for k in update if k not in ("updated_at", "updated_by")},
        "new_values": {k: v for k, v in update.items() if k not in ("updated_at", "updated_by")},
    })

    return await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})


@router.delete("/{tx_id}")
async def delete_transaction(tx_id: str, user=Depends(get_current_user)):
    now = now_iso()
    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {"deleted": True, "deleted_at": now, "deleted_by": user.get("email", user["id"])}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "deleted",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
    })
    return {"status": "deleted"}


@router.post("/{tx_id}/approve")
async def approve_transaction(tx_id: str, user=Depends(get_current_user)):
    await db.transactions_normalized.update_one({"transaction_id": tx_id}, {"$set": {"review_status": "approved", "updated_at": now_iso()}})
    return {"status": "approved"}

@router.post("/{tx_id}/ready-to-publish")
async def mark_ready(tx_id: str, user=Depends(get_current_user)):
    await db.transactions_normalized.update_one({"transaction_id": tx_id}, {"$set": {"publish_status": "ready_to_publish", "updated_at": now_iso()}})
    return {"status": "ready_to_publish"}


# ══════════════════════════════════════════
# IMPORT
# ══════════════════════════════════════════

@router.post("/import")
async def import_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Import Excel/CSV file with transactions."""
    import pandas as pd

    content = await file.read()
    filename = file.filename or "upload"
    import_id = f"imp_{new_id()[:12]}"
    now = now_iso()

    # Parse file
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content), sheet_name=None)
            # Find the data sheet
            for name, sheet_df in df.items():
                if len(sheet_df) > 10 and any(col in str(sheet_df.columns).lower() for col in ["target", "buyer", "announcement"]):
                    df = sheet_df
                    break
            else:
                df = list(df.values())[0] if isinstance(df, dict) else df
    except Exception as e:
        raise HTTPException(400, f"Parse error: {str(e)}")

    # Column alias mapping
    ALIASES = {
        "announcement_date": ["announcement_date", "fecha_anuncio", "date", "announcement date"],
        "conclusion_date": ["conclusion_date", "fecha_cierre", "close date"],
        "status": ["status", "estado"],
        "target": ["target", "target company", "compañía objetivo", "target_name"],
        "buyer": ["buyer", "comprador", "acquiror", "buyer_name"],
        "seller": ["seller", "vendedor", "seller_name"],
        "transaction_type": ["transaction_type", "tipo operación", "deal type", "type"],
        "geography_primary": ["geography_primary", "geography", "país", "country"],
        "geography_detail_raw": ["geography_detail_raw", "geography detail"],
        "value_raw": ["value_raw", "valor", "value"],
        "value_eurm": ["value_eurm", "valor eurm", "deal value"],
        "value_disclosed": ["value_disclosed"],
        "approximate_value": ["approximate_value"],
        "revenue_eurm": ["revenue_eurm", "revenue", "sales", "ventas", "facturación"],
        "ebitda_eurm": ["ebitda_eurm", "ebitda"],
        "ev_eurm": ["ev_eurm", "ev", "enterprise value"],
        "ve_sales": ["ve_sales", "ve/ventas"],
        "ve_ebitda": ["ve_ebitda", "ve/ebitda"],
        "sector_target": ["sector_target", "sector", "subsector"],
        "subsector_objective": ["subsector_objective", "subsector"],
        "cis_category_suggested": ["cis_category_suggested", "categoría sugerida"],
        "observations": ["observations", "observaciones", "notes"],
        "review_notes": ["review_notes"],
    }

    # Normalize column names
    col_map = {}
    for target_col, aliases in ALIASES.items():
        for col in df.columns:
            if str(col).strip().lower() in [a.lower() for a in aliases]:
                col_map[col] = target_col
                break

    df = df.rename(columns=col_map)

    # Save import record
    await db.transaction_imports.insert_one({
        "import_id": import_id, "source_file_name": filename, "source_type": "file_import",
        "file_type": filename.split(".")[-1], "imported_by": user.get("email", user["id"]),
        "imported_at": now, "status": "processing",
        "raw_rows_count": len(df), "normalized_rows_count": 0,
        "duplicates_detected_count": 0, "errors_count": 0,
        "created_at": now, "updated_at": now,
    })

    # Process rows
    stats = {"imported": 0, "errors": 0, "dupes_detected": 0}

    for idx, row in df.iterrows():
        raw = row.to_dict()
        # Clean NaN
        raw = {k: (None if str(v) in ("nan", "NaN", "None", "") else v) for k, v in raw.items()}

        try:
            # Save raw
            await db.transactions_raw.insert_one({
                "raw_id": new_id(), "import_id": import_id,
                "source_file_name": filename, "source_row_number": idx + 2,
                "raw_payload": {k: str(v)[:500] if v else None for k, v in raw.items()},
                "parse_status": "ok", "created_at": now,
            })

            # Normalize
            normalized = normalize_transaction(raw)
            tx_id = f"tx_{new_id()[:12]}"

            tx = {
                "transaction_id": tx_id, "source_type": "file_import",
                "source_import_id": import_id, "source_file_name": filename,
                "source_row_number": idx + 2,
                **normalized,
                "dedupe_status": "pending_check",
                "matching_status": "pending", "review_status": "pending",
                "publish_status": "not_published",
                "sector_mapping_status": "pending" if normalized.get("sector_original") else "not_applicable",
                "deleted": False,
                "created_by": user.get("email", user["id"]),
                "created_at": now, "updated_at": now,
            }
            await db.transactions_normalized.insert_one({**tx})
            stats["imported"] += 1

        except Exception as e:
            stats["errors"] += 1
            logger.warning(f"Import row {idx} error: {e}")

    # Update import record
    await db.transaction_imports.update_one(
        {"import_id": import_id},
        {"$set": {
            "status": "completed", "normalized_rows_count": stats["imported"],
            "errors_count": stats["errors"], "updated_at": now_iso()
        }}
    )

    # Audit log for the import
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": f"import:{import_id}",
        "action": "file_imported",
        "changed_by": user.get("email", user["id"]), "changed_at": now_iso(),
        "new_values": {"filename": filename, "rows_imported": stats["imported"], "errors": stats["errors"]},
    })

    # Run dedupe check on all imported transactions
    imported_txs = await db.transactions_normalized.find(
        {"source_import_id": import_id, "deleted": {"$ne": True}},
        {"_id": 0}
    ).to_list(10000)
    for itx in imported_txs:
        await _check_duplicates(itx["transaction_id"])
        stats["dupes_detected"] += await db.transaction_dedupe_candidates.count_documents(
            {"$or": [{"transaction_id_a": itx["transaction_id"]}, {"transaction_id_b": itx["transaction_id"]}], "review_status": "pending"}
        )
        # Run entity matching
        await run_matching_for_transaction(db, itx)

    # Update dedupe count in import record
    await db.transaction_imports.update_one(
        {"import_id": import_id},
        {"$set": {"duplicates_detected_count": stats["dupes_detected"], "updated_at": now_iso()}}
    )

    return {"import_id": import_id, **stats, "total_rows": len(df)}


@router.get("/imports/list")
async def list_imports(user=Depends(get_current_user)):
    imports = await db.transaction_imports.find({}, {"_id": 0}).sort("imported_at", -1).to_list(50)
    return {"imports": imports}


# ══════════════════════════════════════════
# DEDUPLICATION
# ══════════════════════════════════════════

async def _check_duplicates(tx_id: str):
    """Check a transaction against existing ones for duplicates."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx: return

    target_norm = tx.get("target_name_normalized", "")
    if not target_norm:
        await db.transactions_normalized.update_one(
            {"transaction_id": tx_id}, {"$set": {"dedupe_status": "unique"}}
        )
        return

    candidates = await db.transactions_normalized.find(
        {"transaction_id": {"$ne": tx_id}, "deleted": {"$ne": True},
         "target_name_normalized": {"$regex": target_norm[:10], "$options": "i"}},
        {"_id": 0}
    ).limit(50).to_list(50)

    found_dupe = False
    for cand in candidates:
        sim = calculate_similarity(tx, cand)
        if sim["recommendation"] in ("merge", "review"):
            # Avoid duplicate candidate pairs
            existing = await db.transaction_dedupe_candidates.find_one({
                "$or": [
                    {"transaction_id_a": tx_id, "transaction_id_b": cand["transaction_id"]},
                    {"transaction_id_a": cand["transaction_id"], "transaction_id_b": tx_id},
                ]
            })
            if existing:
                continue
            await db.transaction_dedupe_candidates.insert_one({
                "candidate_id": new_id(), "transaction_id_a": tx_id,
                "transaction_id_b": cand["transaction_id"],
                **sim, "review_status": "pending", "created_at": now_iso(),
            })
            found_dupe = True

    # Update dedupe_status
    if found_dupe:
        await db.transactions_normalized.update_one(
            {"transaction_id": tx_id}, {"$set": {"dedupe_status": "possible_duplicate"}}
        )
    else:
        await db.transactions_normalized.update_one(
            {"transaction_id": tx_id}, {"$set": {"dedupe_status": "unique"}}
        )


@router.get("/dedupe/candidates")
async def list_dedupe_candidates(status: Optional[str] = "pending", user=Depends(get_current_user)):
    query = {}
    if status: query["review_status"] = status
    candidates = await db.transaction_dedupe_candidates.find(query, {"_id": 0}).sort("similarity_score", -1).to_list(100)

    # Enrich with transaction data
    for c in candidates:
        c["tx_a"] = await db.transactions_normalized.find_one({"transaction_id": c["transaction_id_a"]}, {"_id": 0, "target_name": 1, "buyer_name": 1, "announcement_date": 1, "transaction_type": 1, "geography_primary": 1, "value_eurm": 1})
        c["tx_b"] = await db.transactions_normalized.find_one({"transaction_id": c["transaction_id_b"]}, {"_id": 0, "target_name": 1, "buyer_name": 1, "announcement_date": 1, "transaction_type": 1, "geography_primary": 1, "value_eurm": 1})

    return {"candidates": candidates, "total": len(candidates)}


@router.post("/dedupe/{candidate_id}/merge")
async def merge_duplicate(candidate_id: str, user=Depends(get_current_user)):
    """Merge: keep A, soft-delete B."""
    cand = await db.transaction_dedupe_candidates.find_one({"candidate_id": candidate_id}, {"_id": 0})
    if not cand: raise HTTPException(404, "Candidate not found")

    now = now_iso()
    email = user.get("email", user.get("id"))

    # Soft delete B
    await db.transactions_normalized.update_one(
        {"transaction_id": cand["transaction_id_b"]},
        {"$set": {"deleted": True, "dedupe_status": "confirmed_duplicate", "deleted_at": now, "deleted_by": email, "delete_reason": "duplicate_merged", "visible_in_cis": False}}
    )
    await db.transactions_normalized.update_one(
        {"transaction_id": cand["transaction_id_a"]},
        {"$set": {"dedupe_status": "unique"}}
    )
    await db.transaction_dedupe_candidates.update_one(
        {"candidate_id": candidate_id},
        {"$set": {"review_status": "merged", "reviewed_by": email, "reviewed_at": now}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": cand["transaction_id_a"],
        "action": "duplicate_merged", "changed_by": email, "changed_at": now,
        "new_values": {"kept": cand["transaction_id_a"], "discarded": cand["transaction_id_b"]},
    })
    return {"status": "merged", "kept": cand["transaction_id_a"], "discarded": cand["transaction_id_b"]}


@router.post("/dedupe/{candidate_id}/merge-reverse")
async def merge_duplicate_reverse(candidate_id: str, user=Depends(get_current_user)):
    """Merge reverse: keep B, soft-delete A."""
    cand = await db.transaction_dedupe_candidates.find_one({"candidate_id": candidate_id}, {"_id": 0})
    if not cand: raise HTTPException(404, "Candidate not found")

    now = now_iso()
    email = user.get("email", user.get("id"))

    await db.transactions_normalized.update_one(
        {"transaction_id": cand["transaction_id_a"]},
        {"$set": {"deleted": True, "dedupe_status": "confirmed_duplicate", "deleted_at": now, "deleted_by": email, "delete_reason": "duplicate_merged", "visible_in_cis": False}}
    )
    await db.transactions_normalized.update_one(
        {"transaction_id": cand["transaction_id_b"]},
        {"$set": {"dedupe_status": "unique"}}
    )
    await db.transaction_dedupe_candidates.update_one(
        {"candidate_id": candidate_id},
        {"$set": {"review_status": "merged_reverse", "reviewed_by": email, "reviewed_at": now}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": cand["transaction_id_b"],
        "action": "duplicate_merged", "changed_by": email, "changed_at": now,
        "new_values": {"kept": cand["transaction_id_b"], "discarded": cand["transaction_id_a"]},
    })
    return {"status": "merged", "kept": cand["transaction_id_b"], "discarded": cand["transaction_id_a"]}


@router.post("/dedupe/{candidate_id}/keep-separate")
async def keep_separate(candidate_id: str, user=Depends(get_current_user)):
    now = now_iso()
    email = user.get("email", user.get("id"))
    await db.transaction_dedupe_candidates.update_one(
        {"candidate_id": candidate_id},
        {"$set": {"review_status": "kept_separate", "reviewed_by": email, "reviewed_at": now}}
    )
    # Clear possible_duplicate status on both
    cand = await db.transaction_dedupe_candidates.find_one({"candidate_id": candidate_id}, {"_id": 0})
    if cand:
        for tx_id in [cand.get("transaction_id_a"), cand.get("transaction_id_b")]:
            if tx_id:
                # Only clear if no other pending dupes
                other = await db.transaction_dedupe_candidates.count_documents({
                    "$or": [{"transaction_id_a": tx_id}, {"transaction_id_b": tx_id}],
                    "review_status": "pending", "candidate_id": {"$ne": candidate_id}
                })
                if other == 0:
                    await db.transactions_normalized.update_one(
                        {"transaction_id": tx_id}, {"$set": {"dedupe_status": "unique"}}
                    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": candidate_id,
        "action": "duplicate_kept_separate", "changed_by": email, "changed_at": now,
    })
    return {"status": "kept_separate"}


# ══════════════════════════════════════════
# SECTOR MAPPING
# ══════════════════════════════════════════

@router.get("/sectors/mappings")
async def list_sector_mappings(user=Depends(get_current_user)):
    pipeline = [
        {"$match": {"sector_original": {"$ne": None}, "deleted": {"$ne": True}}},
        {"$group": {
            "_id": "$sector_original",
            "count": {"$sum": 1},
            "cis_category": {"$first": "$cis_category_suggested"},
        }},
        {"$sort": {"count": -1}}
    ]
    sectors = await db.transactions_normalized.aggregate(pipeline).to_list(200)
    return {"sectors": [{"sector_original": s["_id"], "count": s["count"], "cis_category_suggested": s.get("cis_category")} for s in sectors]}


@router.get("/audit/{tx_id}")
async def get_audit_log(tx_id: str, user=Depends(get_current_user)):
    logs = await db.transaction_audit_logs.find({"transaction_id": tx_id}, {"_id": 0}).sort("changed_at", -1).to_list(50)
    return {"logs": logs}


@router.post("/{tx_id}/validate-publish")
async def validate_for_publish(tx_id: str, user=Depends(get_current_user)):
    """Validate a transaction meets all criteria for publishing."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    errors = []
    if tx.get("normalization_status") != "completed":
        errors.append("normalization_status must be 'completed'")
    if tx.get("dedupe_status") == "possible_duplicate":
        errors.append("dedupe_status is 'possible_duplicate' — resolve duplicates first")
    if tx.get("review_status") not in ("reviewed", "approved"):
        errors.append(f"review_status is '{tx.get('review_status')}' — must be 'reviewed' or 'approved'")
    if tx.get("sector_mapping_status") and tx.get("sector_mapping_status") not in ("approved", "not_applicable"):
        errors.append(f"sector_mapping_status is '{tx.get('sector_mapping_status')}' — must be 'approved' or 'not_applicable'")

    if errors:
        return {"valid": False, "errors": errors, "transaction_id": tx_id}

    # Mark as ready
    now = now_iso()
    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {"publish_status": "ready_to_publish", "updated_at": now}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "marked_ready_to_publish",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
    })
    return {"valid": True, "transaction_id": tx_id, "publish_status": "ready_to_publish"}


@router.post("/{tx_id}/review")
async def review_transaction(tx_id: str, status: str = Query(..., regex="^(reviewed|approved|rejected)$"), user=Depends(get_current_user)):
    """Set review status."""
    now = now_iso()
    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {"review_status": status, "updated_at": now, "updated_by": user.get("email", user["id"])}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": f"review_{status}",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
    })
    return {"status": status}


@router.post("/{tx_id}/sector-mapping")
async def set_sector_mapping(tx_id: str, cis_category: str = "", cis_subcategory: str = "", status: str = "approved", user=Depends(get_current_user)):
    """Approve or update sector mapping."""
    now = now_iso()
    update = {"sector_mapping_status": status, "updated_at": now}
    if cis_category:
        update["cis_category_suggested"] = cis_category
    if cis_subcategory:
        update["cis_subcategory_suggested"] = cis_subcategory
    await db.transactions_normalized.update_one({"transaction_id": tx_id}, {"$set": update})
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "sector_mapping_updated",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {"cis_category": cis_category, "cis_subcategory": cis_subcategory, "status": status},
    })
    return {"status": status}


@router.post("/{tx_id}/run-matching")
async def run_matching_single(tx_id: str, user=Depends(get_current_user)):
    """Re-run entity matching for a single transaction."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    links = await run_matching_for_transaction(db, tx)
    return {"transaction_id": tx_id, "links_created": len(links), "matching_status": tx.get("matching_status")}


# ══════════════════════════════════════════
# CLASSIFICATION COPILOT
# ══════════════════════════════════════════

@router.post("/{tx_id}/suggest-classification")
async def suggest_tx_classification(tx_id: str, user=Depends(get_current_user)):
    """Generate an AI classification suggestion for a transaction."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    result = await suggest_classification(tx)
    now = now_iso()
    suggestion_id = f"sug_{new_id()[:12]}"

    suggestion = {
        "suggestion_id": suggestion_id,
        "transaction_id": tx_id,
        "suggested_category": result["suggested_category"],
        "suggested_subcategory": result["suggested_subcategory"],
        "confidence": result["confidence"],
        "confidence_label": result["confidence_label"],
        "reasoning": result["reasoning"],
        "signals_used": result["signals_used"],
        "alternative_suggestions": result["alternative_suggestions"],
        "model_used": result["model_used"],
        "prompt_version": result["prompt_version"],
        "raw_model_response": result["raw_model_response"],
        "validation_status": result["validation_status"],
        "validation_errors": result.get("validation_errors", []),
        "status": "suggested",
        "requires_human_review": True,
        "accepted_by": None,
        "accepted_at": None,
        "rejected_by": None,
        "rejected_at": None,
        "created_by": user.get("email", user["id"]),
        "created_at": now,
        "updated_at": now,
    }

    await db.transaction_classification_suggestions.insert_one({**suggestion})

    # Audit log
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id,
        "action": "classification_suggested",
        "changed_by": user.get("email", user["id"]), "changed_at": now,
        "new_values": {
            "suggestion_id": suggestion_id,
            "category": result["suggested_category"],
            "subcategory": result["suggested_subcategory"],
            "confidence": result["confidence_label"],
            "validation": result["validation_status"],
        },
    })

    # Return without raw_model_response for cleaner API
    resp = {k: v for k, v in suggestion.items() if k != "raw_model_response"}
    return resp


@router.get("/{tx_id}/classification-suggestions")
async def list_classification_suggestions(tx_id: str, user=Depends(get_current_user)):
    """Get all classification suggestions for a transaction."""
    suggestions = await db.transaction_classification_suggestions.find(
        {"transaction_id": tx_id},
        {"_id": 0, "raw_model_response": 0}
    ).sort("created_at", -1).to_list(20)
    return {"suggestions": suggestions}


@router.post("/{tx_id}/classification-suggestions/{suggestion_id}/accept")
async def accept_classification(tx_id: str, suggestion_id: str, user=Depends(get_current_user)):
    """Accept a classification suggestion and apply it to the transaction."""
    suggestion = await db.transaction_classification_suggestions.find_one(
        {"suggestion_id": suggestion_id, "transaction_id": tx_id}, {"_id": 0}
    )
    if not suggestion:
        raise HTTPException(404, "Suggestion not found")
    if suggestion["status"] != "suggested":
        raise HTTPException(400, f"Suggestion already {suggestion['status']}")
    if suggestion["validation_status"] != "valid":
        raise HTTPException(400, "Cannot accept an invalid suggestion")

    now = now_iso()
    email = user.get("email", user["id"])

    # Mark previous suggestions as superseded
    await db.transaction_classification_suggestions.update_many(
        {"transaction_id": tx_id, "status": "suggested", "suggestion_id": {"$ne": suggestion_id}},
        {"$set": {"status": "superseded", "updated_at": now}}
    )

    # Accept this suggestion
    await db.transaction_classification_suggestions.update_one(
        {"suggestion_id": suggestion_id},
        {"$set": {
            "status": "accepted",
            "accepted_by": email,
            "accepted_at": now,
            "updated_at": now,
        }}
    )

    # Apply to transaction
    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {
            "cis_category_suggested": suggestion["suggested_category"],
            "cis_subcategory_suggested": suggestion["suggested_subcategory"],
            "sector_mapping_status": "approved",
            "updated_at": now,
            "updated_by": email,
        }}
    )

    # Audit
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id,
        "action": "classification_accepted",
        "changed_by": email, "changed_at": now,
        "new_values": {
            "suggestion_id": suggestion_id,
            "category": suggestion["suggested_category"],
            "subcategory": suggestion["suggested_subcategory"],
        },
    })

    return {
        "status": "accepted",
        "category": suggestion["suggested_category"],
        "subcategory": suggestion["suggested_subcategory"],
    }


@router.post("/{tx_id}/classification-suggestions/{suggestion_id}/reject")
async def reject_classification(tx_id: str, suggestion_id: str, user=Depends(get_current_user)):
    """Reject a classification suggestion."""
    suggestion = await db.transaction_classification_suggestions.find_one(
        {"suggestion_id": suggestion_id, "transaction_id": tx_id}, {"_id": 0}
    )
    if not suggestion:
        raise HTTPException(404, "Suggestion not found")
    if suggestion["status"] != "suggested":
        raise HTTPException(400, f"Suggestion already {suggestion['status']}")

    now = now_iso()
    email = user.get("email", user["id"])

    await db.transaction_classification_suggestions.update_one(
        {"suggestion_id": suggestion_id},
        {"$set": {
            "status": "rejected",
            "rejected_by": email,
            "rejected_at": now,
            "updated_at": now,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id,
        "action": "classification_rejected",
        "changed_by": email, "changed_at": now,
        "new_values": {"suggestion_id": suggestion_id},
    })

    return {"status": "rejected"}


# ══════════════════════════════════════════
# CIS VALIDATION & APPROVAL
# ══════════════════════════════════════════

@router.post("/{tx_id}/validate-for-cis")
async def validate_for_cis(tx_id: str, user=Depends(get_current_user)):
    """Validate whether a transaction meets CIS publication requirements."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    return await _validate_for_cis(tx)


@router.post("/{tx_id}/approve-for-cis")
async def approve_for_cis(tx_id: str, user=Depends(get_current_user)):
    """Approve a transaction for CIS publication if it meets all requirements."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    validation = await _validate_for_cis(tx)
    if not validation["can_approve"]:
        return {**validation, "status": "rejected"}

    now = now_iso()
    email = user.get("email", user["id"])

    # Compute payload hash
    sources = await db.transaction_sources.find(
        {"transaction_id": tx_id}, {"_id": 0}
    ).to_list(20)
    payload_hash = compute_cis_payload_hash(tx, sources)

    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {
            "publish_status": "approved_for_cis",
            "cis_sync_status": "approved_for_cis",
            "approved_for_cis_at": now,
            "approved_for_cis_by": email,
            "last_published_at": now,
            "last_published_by": email,
            "last_published_payload_hash": payload_hash,
            "updated_at": now,
            "updated_by": email,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id,
        "action": "approved_for_cis",
        "changed_by": email, "changed_at": now,
        "new_values": {"quality_score": validation["quality_score"], "payload_hash": payload_hash},
    })

    return {**validation, "status": "approved_for_cis"}


@router.post("/{tx_id}/update-cis")
async def update_cis(tx_id: str, user=Depends(get_current_user)):
    """Re-validate and update CIS sync after edits to a published transaction."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if tx.get("publish_status") != "approved_for_cis":
        raise HTTPException(400, "Transaction is not published in CIS")

    validation = await _validate_for_cis(tx)
    if not validation["can_approve"]:
        return {**validation, "status": "validation_failed"}

    now = now_iso()
    email = user.get("email", user["id"])

    sources = await db.transaction_sources.find({"transaction_id": tx_id}, {"_id": 0}).to_list(20)
    payload_hash = compute_cis_payload_hash(tx, sources)

    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {
            "cis_sync_status": "approved_for_cis",
            "last_published_at": now,
            "last_published_by": email,
            "last_published_payload_hash": payload_hash,
            "updated_at": now,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id,
        "action": "cis_updated",
        "changed_by": email, "changed_at": now,
        "new_values": {"payload_hash": payload_hash},
    })

    return {**validation, "status": "updated"}


from pydantic import BaseModel as _WithdrawBM

class WithdrawRequest(_WithdrawBM):
    reason: str
    notes: Optional[str] = None


@router.post("/{tx_id}/withdraw-from-cis")
async def withdraw_from_cis(tx_id: str, req: WithdrawRequest, user=Depends(get_current_user)):
    """Withdraw a transaction from CIS with mandatory reason. Does NOT delete from Agency Tool."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if not tx.get("visible_in_cis") and tx.get("publish_status") != "approved_for_cis":
        raise HTTPException(400, "La operacion no esta publicada en CIS")
    if req.reason not in WITHDRAWAL_REASONS:
        raise HTTPException(400, f"Invalid reason. Must be one of: {', '.join(WITHDRAWAL_REASONS)}")

    now = now_iso()
    email = user.get("email", user["id"])

    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {
            "publish_status": "removed_from_cis",
            "cis_sync_status": "removed_from_cis",
            "visible_in_cis": False,
            "withdrawn_from_cis_at": now,
            "withdrawn_from_cis_by": email,
            "withdrawal_reason": req.reason,
            "withdrawal_notes": req.notes,
            "updated_at": now,
            "updated_by": email,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id,
        "action": "withdrawn_from_cis",
        "changed_by": email, "changed_at": now,
        "new_values": {"reason": req.reason, "notes": req.notes},
    })

    return {"status": "withdrawn", "transaction_id": tx_id, "reason": req.reason}


@router.post("/{tx_id}/unapprove-for-cis")
async def unapprove_for_cis(tx_id: str, user=Depends(get_current_user)):
    """Remove CIS approval (legacy — prefer withdraw-from-cis with reason)."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    now = now_iso()
    email = user.get("email", user["id"])

    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {
            "publish_status": "not_published",
            "cis_sync_status": "not_published",
            "approved_for_cis_at": None,
            "approved_for_cis_by": None,
            "updated_at": now,
            "updated_by": email,
        }}
    )

    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id,
        "action": "unapproved_from_cis",
        "changed_by": email, "changed_at": now,
    })

    return {"status": "unapproved", "transaction_id": tx_id}


# ══════════════════════════════════════════
# EDITORIAL REVIEW WORKFLOW
# ══════════════════════════════════════════

@router.post("/{tx_id}/mark-reviewed")
async def mark_reviewed(tx_id: str, user=Depends(get_current_user)):
    """Mark transaction as reviewed. Checks basic requirements."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    blockers = []
    if not tx.get("target_name"):
        blockers.append("Falta target")
    if not (tx.get("announcement_date") or tx.get("year")):
        blockers.append("Falta fecha")
    if not (tx.get("cis_category_suggested") or tx.get("outside_cis_taxonomy")):
        blockers.append("Falta categoria CIS o fuera de taxonomia")

    # Check sources
    src_count = await db.transaction_sources.count_documents({"transaction_id": tx_id})
    has_source = src_count > 0 or bool(tx.get("source") or tx.get("source_url"))
    if not has_source:
        blockers.append("Falta al menos una fuente")

    if not tx.get("summary"):
        blockers.append("Falta descripcion (summary)")

    if blockers:
        return {"status": "blocked", "blockers": blockers}

    now = now_iso()
    email = user.get("email", user["id"])
    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {"review_status": "approved", "updated_at": now, "updated_by": email}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "review_approved",
        "changed_by": email, "changed_at": now,
    })
    return {"status": "reviewed"}


@router.post("/{tx_id}/mark-ready-for-cis")
async def mark_ready_for_cis(tx_id: str, user=Depends(get_current_user)):
    """Mark as ready for CIS. Runs full validation first."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    validation = await _validate_for_cis(tx)
    if not validation["can_approve"]:
        return {**validation, "status": "blocked"}

    now = now_iso()
    email = user.get("email", user["id"])
    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {"publish_status": "ready_to_publish", "updated_at": now, "updated_by": email}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "marked_ready_for_cis",
        "changed_by": email, "changed_at": now,
    })
    return {**validation, "status": "ready_for_cis"}


@router.get("/{tx_id}/validation-checklist")
async def get_validation_checklist(tx_id: str, user=Depends(get_current_user)):
    """Return detailed validation checklist with block references for UI."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    src_count = await db.transaction_sources.count_documents({"transaction_id": tx_id})
    primary_src = await db.transaction_sources.find_one(
        {"transaction_id": tx_id, "is_primary": True}, {"_id": 0}
    )
    has_source = src_count > 0 or bool(tx.get("source") or tx.get("source_url"))
    has_primary = primary_src is not None or bool(tx.get("source") or tx.get("source_url"))

    target_link = await db.transaction_company_links.find_one(
        {"transaction_id": tx_id, "entity_role": "target",
         "match_status": {"$in": ["manual_confirmed", "auto_strong_candidate", "needs_new_company", "external_entity"]}},
        {"_id": 0}
    )

    requirements = [
        {"key": "target", "status": "ok" if tx.get("target_name") else "error",
         "label": "Target informado", "message": "Introduce el nombre del target.", "block": "basics"},
        {"key": "date", "status": "ok" if (tx.get("announcement_date") or tx.get("year")) else "error",
         "label": "Fecha informada", "message": "Introduce fecha de anuncio o año.", "block": "basics"},
        {"key": "type", "status": "ok" if (tx.get("transaction_type") and tx["transaction_type"] != "other") else ("warning" if tx.get("transaction_type") == "other" else "error"),
         "label": "Tipo de operacion", "message": "Selecciona el tipo de operacion.", "block": "basics"},
        {"key": "category", "status": "ok" if (tx.get("cis_category_suggested") or tx.get("outside_cis_taxonomy")) else "error",
         "label": "Categoria CIS o fuera de taxonomia", "message": "Selecciona una categoria CIS o marca como fuera de taxonomia.", "block": "classification"},
        {"key": "source", "status": "ok" if has_source else "error",
         "label": "Al menos una fuente", "message": "Añade al menos una fuente o articulo.", "block": "sources"},
        {"key": "primary_source", "status": "ok" if has_primary else "error",
         "label": "Fuente principal seleccionada", "message": "Marca una fuente como principal.", "block": "sources"},
        {"key": "summary", "status": "ok" if tx.get("summary") else "error",
         "label": "Descripcion informada", "message": "Escribe una descripcion factual de la operacion.", "block": "description"},
        {"key": "dedupe", "status": "error" if tx.get("dedupe_status") == "possible_duplicate" else "ok",
         "label": "Deduplicacion resuelta", "message": "Revisa y resuelve posibles duplicados.", "block": "basics"},
        {"key": "target_entity", "status": "ok" if target_link else "error",
         "label": "Target revisado", "message": "Revisa la vinculacion CIS del target.", "block": "entities"},
        {"key": "review", "status": "ok" if tx.get("review_status") in ("reviewed", "approved") else "error",
         "label": "Review editorial", "message": "Marca la operacion como revisada.", "block": "quality"},
    ]

    can_publish = all(r["status"] != "error" for r in requirements)
    warnings = [r for r in requirements if r["status"] == "warning"]

    return {"requirements": requirements, "can_publish": can_publish, "warnings_count": len(warnings)}


# ══════════════════════════════════════════
# MASS PUBLISH & DELETE
# ══════════════════════════════════════════

from pydantic import BaseModel as _DeleteBM

class DeleteRequest(_DeleteBM):
    reason: Optional[str] = None


@router.post("/{tx_id}/soft-delete")
async def soft_delete_transaction(tx_id: str, req: DeleteRequest, user=Depends(get_current_user)):
    """Soft delete a transaction. Also withdraws from CIS if published."""
    tx = await db.transactions_normalized.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")

    now = now_iso()
    email = user.get("email", user["id"])

    was_in_cis = tx.get("visible_in_cis") or tx.get("publish_status") == "approved_for_cis"

    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {
            "deleted": True, "deleted_at": now, "deleted_by": email,
            "delete_reason": req.reason, "visible_in_cis": False,
            "publish_status": "removed_from_cis" if was_in_cis else tx.get("publish_status", "not_published"),
        }}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "deleted",
        "changed_by": email, "changed_at": now,
        "new_values": {"reason": req.reason, "was_in_cis": was_in_cis},
    })
    return {"status": "deleted", "was_in_cis": was_in_cis}


@router.post("/{tx_id}/mark-ready")
async def mark_ready(tx_id: str, user=Depends(get_current_user)):
    """Manually mark as ready for publishing."""
    now = now_iso()
    email = user.get("email", user["id"])
    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {"publish_status": "ready_to_publish", "updated_at": now, "updated_by": email}}
    )
    await db.transaction_audit_logs.insert_one({
        "log_id": new_id(), "transaction_id": tx_id, "action": "marked_ready",
        "changed_by": email, "changed_at": now,
    })
    return {"status": "ready_to_publish"}
