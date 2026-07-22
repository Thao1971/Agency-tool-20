"""BORME routes — API endpoints for BORME capability."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from database import db
from auth_utils import get_current_user
from models import new_id, now_iso
from borme import (
    BormeFetchDayRequest, BormeFetchRangeRequest,
    BormeEnrichCompanyRequest, BormeEnrichBatchRequest
)
from borme.fetcher import fetch_summary, extract_items_from_summary, download_pdf, pdf_hash, date_range
from borme.parser import (
    extract_text_from_pdf, segment_entries, detect_events,
    build_idempotency_key, normalize_company_name
)
from borme.matcher import match_events_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/borme", tags=["borme"])


async def _process_date(date_str: str, force: bool = False) -> dict:
    """Process a single BORME date: fetch → download PDFs → parse → classify → persist."""
    stats = {"date": date_str, "items": 0, "pdfs_ok": 0, "pdfs_failed": 0,
             "events_extracted": 0, "events_new": 0, "events_duplicate": 0,
             "sector_verified": 0, "sector_inferred": 0, "sector_unavailable": 0,
             "errors": []}

    # Load company activity profiles cache for sector resolution
    _company_profiles_cache = {}
    try:
        profiles = await db.company_activity_profiles.find(
            {"status": "verified"}, {"_id": 0, "company_key": 1, "canonical_cnae_code": 1, "evidence_text": 1, "status": 1}
        ).to_list(50000)
        _company_profiles_cache = {p["company_key"]: p for p in profiles}
    except Exception:
        pass

    # Check if already processed (skip unless force)
    existing = await db.borme_summaries.find_one({"publication_date": date_str})
    if existing and existing.get("status") == "completed" and existing.get("events_extracted", 0) > 0 and not force:
        stats["skipped"] = True
        return stats

    # If force or stale (completed but 0 events), clear old data for this date
    if existing and (force or existing.get("events_extracted", 0) == 0):
        await db.borme_summaries.delete_one({"publication_date": date_str})
        await db.borme_raw_items.delete_many({"publication_date": date_str})
        # Don't delete events — idempotency handles duplicates

    # Fetch summary
    summary = fetch_summary(date_str)
    if not summary:
        stats["errors"].append({"type": "fetch_failed", "detail": f"No summary for {date_str}"})
        await db.borme_summaries.update_one(
            {"publication_date": date_str},
            {"$set": {"publication_date": date_str, "status": "no_publication", "updated_at": now_iso()}},
            upsert=True
        )
        return stats

    items = extract_items_from_summary(summary)
    stats["items"] = len(items)

    await db.borme_summaries.update_one(
        {"publication_date": date_str},
        {"$set": {
            "publication_date": date_str, "status": "processing",
            "borme_number": items[0]["borme_number"] if items else None,
            "item_count": len(items), "updated_at": now_iso()
        }},
        upsert=True
    )

    for item in items:
        identifier = item["official_identifier"]
        province = item.get("title", "")
        pdf_url = item.get("pdf_url", "")

        # Skip section C (announcements, no company events)
        if item.get("section_code") == "C":
            continue

        # Check if item already processed
        existing_item = await db.borme_raw_items.find_one({"official_identifier": identifier, "status": "completed"})
        if existing_item:
            continue

        # Download PDF
        pdf_bytes = download_pdf(pdf_url) if pdf_url else None
        if not pdf_bytes:
            stats["pdfs_failed"] += 1
            await db.borme_raw_items.update_one(
                {"official_identifier": identifier},
                {"$set": {"official_identifier": identifier, "publication_date": date_str,
                          "province": province, "pdf_url": pdf_url, "status": "download_failed",
                          "updated_at": now_iso()}},
                upsert=True
            )
            await db.borme_processing_errors.insert_one({
                "id": new_id(), "official_identifier": identifier, "date": date_str,
                "error_type": "download_failed", "detail": f"PDF download failed: {pdf_url}",
                "created_at": now_iso()
            })
            continue

        stats["pdfs_ok"] += 1
        content_hash = pdf_hash(pdf_bytes)

        # Extract text
        text, method = extract_text_from_pdf(pdf_bytes)
        if not text:
            stats["pdfs_failed"] += 1
            await db.borme_raw_items.update_one(
                {"official_identifier": identifier},
                {"$set": {"official_identifier": identifier, "publication_date": date_str,
                          "province": province, "pdf_url": pdf_url, "pdf_hash": content_hash,
                          "status": "extraction_failed", "updated_at": now_iso()}},
                upsert=True
            )
            await db.borme_processing_errors.insert_one({
                "id": new_id(), "official_identifier": identifier, "date": date_str,
                "error_type": "extraction_failed", "detail": "Both PyPDF2 and pdfminer failed",
                "created_at": now_iso()
            })
            continue

        # Segment entries
        entries = segment_entries(text)

        # Persist raw item as completed
        await db.borme_raw_items.update_one(
            {"official_identifier": identifier},
            {"$set": {
                "official_identifier": identifier, "publication_date": date_str,
                "province": province, "section_code": item.get("section_code"),
                "section_name": item.get("section_name"), "pdf_url": pdf_url,
                "pdf_hash": content_hash, "extraction_method": method,
                "entry_count": len(entries), "status": "completed", "updated_at": now_iso()
            }},
            upsert=True
        )

        # Process each entry → events
        for entry in entries:
            events = detect_events(entry)
            for event in events:
                idem_key = build_idempotency_key(
                    date_str, identifier, entry["entry_number"], entry["company_name_raw"]
                )
                # Add event_subtype to make key unique per event type in same entry
                full_key = f"{idem_key}_{event['event_subtype']}"

                # Deduplication check
                existing_ev = await db.borme_events.find_one({"idempotency_key": full_key})
                if existing_ev:
                    stats["events_duplicate"] += 1
                    continue

                event_doc = {
                    "id": new_id(),
                    "source": "BORME",
                    "publication_date": date_str,
                    "borme_number": item.get("borme_number"),
                    "official_identifier": identifier,
                    "section": item.get("section_code"),
                    "section_name": item.get("section_name"),
                    "registry_province": province,
                    "entry_number": entry["entry_number"],
                    "company_name_raw": entry["company_name_raw"],
                    "company_name_normalized": normalize_company_name(entry["company_name_raw"]),
                    "event_type": event["event_type"],
                    "event_subtype": event["event_subtype"],
                    "event_title": event["event_title"],
                    "event_text_raw": entry.get("full_text", "")[:2000],
                    "event_text_excerpt": event.get("event_text_excerpt", "")[:500],
                    "pdf_url": pdf_url,
                    "idempotency_key": full_key,
                    "has_registry_data": entry.get("has_registry_data", False),
                    "created_at": now_iso()
                }

                # Sector classification (CNAE-2025)
                from borme.sector_classifier import classify_event
                sector = classify_event(event_doc, _company_profiles_cache)
                event_doc.update(sector)

                # Update company activity profile cache
                comp_norm = event_doc.get("company_name_normalized", "")
                if comp_norm and sector.get("sector_status") in ("verified", "inferred"):
                    _company_profiles_cache[comp_norm] = {
                        "canonical_cnae_code": sector.get("cnae_code"),
                        "sector_status": sector.get("sector_status"),
                        "evidence_text": sector.get("sector_evidence_text", ""),
                    }
                    # Persist to DB
                    await db.company_activity_profiles.update_one(
                        {"company_key": comp_norm},
                        {"$set": {
                            "company_key": comp_norm,
                            "company_name": entry["company_name_raw"],
                            "canonical_cnae_code": sector.get("cnae_code"),
                            "canonical_cnae_title": sector.get("cnae_title"),
                            "status": sector.get("sector_status"),
                            "source": sector.get("sector_source"),
                            "confidence": sector.get("sector_confidence"),
                            "evidence_text": sector.get("sector_evidence_text"),
                            "updated_at": now_iso()
                        }},
                        upsert=True
                    )

                await db.borme_events.insert_one({**event_doc})
                stats["events_extracted"] += 1
                stats["events_new"] += 1

    # Mark summary as completed
    await db.borme_summaries.update_one(
        {"publication_date": date_str},
        {"$set": {"status": "completed", "events_extracted": stats["events_extracted"],
                  "updated_at": now_iso()}}
    )

    return stats


# ══════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════

@router.post("/fetch-day")
async def fetch_day(req: BormeFetchDayRequest, force: bool = Query(False), user=Depends(get_current_user)):
    """Fetch and process BORME for a single day. Use force=true to reprocess."""
    result = await _process_date(req.date, force=force)
    return result


@router.post("/fetch-range")
async def fetch_range_endpoint(req: BormeFetchRangeRequest, user=Depends(get_current_user)):
    """Fetch and process BORME for a date range."""
    dates = date_range(req.date_from, req.date_to)
    results = {"total_dates": len(dates), "processed": 0, "skipped": 0, "errors": 0, "events_total": 0}

    for d in dates:
        r = await _process_date(d)
        if r.get("skipped"):
            results["skipped"] += 1
        elif r.get("errors"):
            results["errors"] += 1
        else:
            results["processed"] += 1
        results["events_total"] += r.get("events_new", 0)

    return results


@router.post("/enrich-company")
async def enrich_company(req: BormeEnrichCompanyRequest, user=Depends(get_current_user)):
    """Find BORME events matching a specific company."""
    # Build query for events
    query = {}
    if req.date_from:
        query["publication_date"] = {"$gte": req.date_from}
    if req.date_to:
        if "publication_date" in query:
            query["publication_date"]["$lte"] = req.date_to
        else:
            query["publication_date"] = {"$lte": req.date_to}

    # Get all events in range
    events = await db.borme_events.find(query, {"_id": 0}).to_list(50000)

    if not events:
        # Try to fetch the dates first
        if req.date_from and req.date_to:
            dates = date_range(req.date_from, req.date_to)
            for d in dates[:30]:  # Limit to avoid overload
                await _process_date(d)
            events = await db.borme_events.find(query, {"_id": 0}).to_list(50000)

    # Match
    company = {
        "company_id": req.company_id,
        "cif": req.cif,
        "company_name": req.company_name,
        "province": req.province,
    }

    matches, candidates = match_events_batch(events, company)

    # Tag matches with requested company info
    for m in matches + candidates:
        m["requested_company_id"] = req.company_id
        m["requested_cif"] = req.cif
        m["requested_name"] = req.company_name

    return {
        "source": "BORME",
        "requested_company": company,
        "total_events_searched": len(events),
        "matches": matches[:100],
        "unmatched_candidates": candidates[:50],
        "errors": []
    }


@router.post("/enrich-batch")
async def enrich_batch(req: BormeEnrichBatchRequest, user=Depends(get_current_user)):
    """Enrich multiple companies against BORME events."""
    results = []
    for company_req in req.companies:
        # Build query
        query = {}
        if company_req.date_from:
            query["publication_date"] = {"$gte": company_req.date_from}
        if company_req.date_to:
            if "publication_date" in query:
                query["publication_date"]["$lte"] = company_req.date_to
            else:
                query["publication_date"] = {"$lte": company_req.date_to}

        events = await db.borme_events.find(query, {"_id": 0}).to_list(50000)

        company = {
            "company_id": company_req.company_id,
            "cif": company_req.cif,
            "company_name": company_req.company_name,
            "province": company_req.province,
        }

        matches, candidates = match_events_batch(events, company)

        for m in matches + candidates:
            m["requested_company_id"] = company_req.company_id
            m["requested_cif"] = company_req.cif
            m["requested_name"] = company_req.company_name

        results.append({
            "requested_company": company,
            "matches": matches[:100],
            "unmatched_candidates": candidates[:20],
        })

    return {"source": "BORME", "results": results, "total_companies": len(results)}



@router.get("/events")
async def list_events(
    date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    company_name: Optional[str] = None,
    event_type: Optional[str] = None,
    province: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """Query processed BORME events with filters."""
    query = {}
    if date:
        query["publication_date"] = date
    elif date_from or date_to:
        date_q = {}
        if date_from: date_q["$gte"] = date_from
        if date_to: date_q["$lte"] = date_to
        query["publication_date"] = date_q
    if company_name:
        query["company_name_normalized"] = {"$regex": normalize_company_name(company_name), "$options": "i"}
    if event_type:
        query["event_type"] = event_type
    if province:
        query["registry_province"] = {"$regex": province, "$options": "i"}

    total = await db.borme_events.count_documents(query)
    events = await db.borme_events.find(query, {"_id": 0}).sort("publication_date", -1).skip(offset).limit(limit).to_list(limit)

    return {"events": events, "total": total, "limit": limit, "offset": offset}


@router.get("/events/{event_id}")
async def get_event(event_id: str, user=Depends(get_current_user)):
    event = await db.borme_events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@router.post("/reprocess-failures")
async def reprocess_failures(user=Depends(get_current_user)):
    """Retry failed PDF downloads and extractions."""
    failed = await db.borme_raw_items.find(
        {"status": {"$in": ["download_failed", "extraction_failed"]}},
        {"_id": 0}
    ).to_list(500)

    results = {"total": len(failed), "recovered": 0, "still_failed": 0}

    for item in failed:
        pdf_bytes = download_pdf(item.get("pdf_url", ""))
        if not pdf_bytes:
            results["still_failed"] += 1
            continue

        text, method = extract_text_from_pdf(pdf_bytes)
        if not text:
            results["still_failed"] += 1
            continue

        # Re-parse
        entries = segment_entries(text)
        for entry in entries:
            events = detect_events(entry)
            for event in events:
                full_key = f"{build_idempotency_key(item['publication_date'], item['official_identifier'], entry['entry_number'], entry['company_name_raw'])}_{event['event_subtype']}"
                existing = await db.borme_events.find_one({"idempotency_key": full_key})
                if not existing:
                    await db.borme_events.insert_one({
                        "id": new_id(), "source": "BORME",
                        "publication_date": item["publication_date"],
                        "official_identifier": item["official_identifier"],
                        "registry_province": item.get("province"),
                        "entry_number": entry["entry_number"],
                        "company_name_raw": entry["company_name_raw"],
                        "company_name_normalized": normalize_company_name(entry["company_name_raw"]),
                        "event_type": event["event_type"], "event_subtype": event["event_subtype"],
                        "event_title": event["event_title"],
                        "event_text_raw": entry.get("full_text", "")[:2000],
                        "event_text_excerpt": event.get("event_text_excerpt", "")[:500],
                        "pdf_url": item.get("pdf_url"),
                        "idempotency_key": full_key,
                        "created_at": now_iso()
                    })

        await db.borme_raw_items.update_one(
            {"official_identifier": item["official_identifier"]},
            {"$set": {"status": "completed", "extraction_method": method, "updated_at": now_iso()}}
        )
        results["recovered"] += 1

    return results


@router.post("/classify-historical")
async def classify_historical(
    limit_events: int = Query(5000, ge=100, le=50000),
    user=Depends(get_current_user)
):
    """Retroactively apply CNAE classification to existing events without sector data."""
    from borme.sector_classifier import classify_event

    # Load company profiles cache
    profiles = await db.company_activity_profiles.find(
        {"status": "verified"}, {"_id": 0, "company_key": 1, "canonical_cnae_code": 1, "evidence_text": 1, "status": 1}
    ).to_list(50000)
    cache = {p["company_key"]: p for p in profiles}

    # Find events without sector classification
    unclassified = await db.borme_events.find(
        {"$or": [{"sector_status": {"$exists": False}}, {"sector_status": None}]},
        {"_id": 0}
    ).limit(limit_events).to_list(limit_events)

    stats = {"total_processed": 0, "verified": 0, "inferred": 0, "unavailable": 0, "profiles_updated": 0}

    for event in unclassified:
        sector = classify_event(event, cache)

        # Update event with sector data
        await db.borme_events.update_one(
            {"idempotency_key": event["idempotency_key"]},
            {"$set": sector}
        )

        status = sector.get("sector_status", "unavailable")
        stats[status] = stats.get(status, 0) + 1
        stats["total_processed"] += 1

        # Update cache and profiles for verified/inferred
        comp_norm = event.get("company_name_normalized", "")
        if comp_norm and status in ("verified", "inferred"):
            if comp_norm not in cache or status == "verified":
                cache[comp_norm] = {
                    "canonical_cnae_code": sector.get("cnae_code"),
                    "sector_status": status,
                    "evidence_text": sector.get("sector_evidence_text", ""),
                }
                await db.company_activity_profiles.update_one(
                    {"company_key": comp_norm},
                    {"$set": {
                        "company_key": comp_norm,
                        "company_name": event.get("company_name_raw"),
                        "canonical_cnae_code": sector.get("cnae_code"),
                        "canonical_cnae_title": sector.get("cnae_title"),
                        "status": status,
                        "source": sector.get("sector_source"),
                        "confidence": sector.get("sector_confidence"),
                        "evidence_text": sector.get("sector_evidence_text"),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                stats["profiles_updated"] += 1

    # Coverage metrics
    total_events = await db.borme_events.count_documents({})
    verified = await db.borme_events.count_documents({"sector_status": "verified"})
    inferred = await db.borme_events.count_documents({"sector_status": "inferred"})
    unavailable = await db.borme_events.count_documents({"sector_status": "unavailable"})
    unclassified_remaining = await db.borme_events.count_documents(
        {"$or": [{"sector_status": {"$exists": False}}, {"sector_status": None}]}
    )

    # Coverage by event type
    type_coverage = await db.borme_events.aggregate([
        {"$group": {
            "_id": {"type": "$event_type", "sector": "$sector_status"},
            "count": {"$sum": 1}
        }}
    ]).to_list(100)

    type_stats = {}
    for tc in type_coverage:
        etype = tc["_id"]["type"]
        sector = tc["_id"].get("sector") or "unclassified"
        if etype not in type_stats:
            type_stats[etype] = {}
        type_stats[etype][sector] = tc["count"]

    return {
        "processed_this_run": stats,
        "coverage": {
            "total_events": total_events,
            "verified": verified,
            "inferred": inferred,
            "unavailable": unavailable,
            "unclassified_remaining": unclassified_remaining,
            "coverage_rate": round((verified + inferred) / max(total_events, 1) * 100, 1),
            "verified_rate": round(verified / max(total_events, 1) * 100, 1),
        },
        "by_event_type": type_stats,
        "profiles_total": await db.company_activity_profiles.count_documents({})
    }



@router.get("/stats")
async def borme_stats(user=Depends(get_current_user)):
    """Operational metrics for BORME capability."""
    total_summaries = await db.borme_summaries.count_documents({})
    completed = await db.borme_summaries.count_documents({"status": "completed"})
    total_items = await db.borme_raw_items.count_documents({})
    items_ok = await db.borme_raw_items.count_documents({"status": "completed"})
    items_failed = await db.borme_raw_items.count_documents({"status": {"$in": ["download_failed", "extraction_failed"]}})
    total_events = await db.borme_events.count_documents({})

    # Event type distribution
    type_dist = await db.borme_events.aggregate([
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]).to_list(20)

    # Errors by type
    error_dist = await db.borme_processing_errors.aggregate([
        {"$group": {"_id": "$error_type", "count": {"$sum": 1}}}
    ]).to_list(10)

    # CNAE sector coverage
    verified = await db.borme_events.count_documents({"sector_status": "verified"})
    inferred = await db.borme_events.count_documents({"sector_status": "inferred"})
    unavailable_s = await db.borme_events.count_documents({"sector_status": "unavailable"})
    unclassified = total_events - verified - inferred - unavailable_s

    # Top CNAE divisions
    cnae_dist = await db.borme_events.aggregate([
        {"$match": {"cnae_division": {"$ne": None}}},
        {"$group": {"_id": {"div": "$cnae_division", "title": "$cnae_title"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]).to_list(10)

    return {
        "total_days_fetched": total_summaries,
        "days_completed": completed,
        "total_items_downloaded": total_items,
        "total_pdfs_processed": items_ok,
        "total_pdfs_failed": items_failed,
        "pdf_success_rate": round(items_ok / max(total_items, 1) * 100, 1),
        "total_events_extracted": total_events,
        "event_type_distribution": {d["_id"]: d["count"] for d in type_dist},
        "errors_by_type": {d["_id"]: d["count"] for d in error_dist},
        "sector_coverage": {
            "verified": verified,
            "inferred": inferred,
            "unavailable": unavailable_s,
            "unclassified": unclassified,
            "coverage_rate": round((verified + inferred) / max(total_events, 1) * 100, 1),
        },
        "top_cnae_divisions": [{"division": d["_id"]["div"], "title": (d["_id"].get("title") or "")[:40], "count": d["count"]} for d in cnae_dist],
    }


@router.get("/ma")
async def get_ma_events(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    subtype: Optional[str] = None,
    province: Optional[str] = None,
    company_name: Optional[str] = None,
    cnae_code: Optional[str] = None,
    cnae_division: Optional[str] = None,
    sector_status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """M&A-specific endpoint with CNAE sector filters."""
    query = {"event_type": "ma"}
    if date_from or date_to:
        dq = {}
        if date_from: dq["$gte"] = date_from
        if date_to: dq["$lte"] = date_to
        query["publication_date"] = dq
    if subtype:
        query["event_subtype"] = subtype
    if province:
        query["registry_province"] = {"$regex": province, "$options": "i"}
    if company_name:
        query["company_name_normalized"] = {"$regex": normalize_company_name(company_name), "$options": "i"}
    if cnae_code:
        query["cnae_code"] = cnae_code
    if cnae_division:
        query["cnae_division"] = cnae_division
    if sector_status:
        query["sector_status"] = sector_status

    total = await db.borme_events.count_documents(query)
    events = await db.borme_events.find(query, {"_id": 0}).sort("publication_date", -1).skip(offset).limit(limit).to_list(limit)

    # Aggregations
    subtype_dist = await db.borme_events.aggregate([
        {"$match": {"event_type": "ma"}},
        {"$group": {"_id": "$event_subtype", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]).to_list(10)

    province_dist = await db.borme_events.aggregate([
        {"$match": {"event_type": "ma"}},
        {"$group": {"_id": "$registry_province", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]).to_list(10)

    date_dist = await db.borme_events.aggregate([
        {"$match": {"event_type": "ma"}},
        {"$group": {"_id": "$publication_date", "count": {"$sum": 1}}},
        {"$sort": {"_id": -1}},
        {"$limit": 30}
    ]).to_list(30)

    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
        "analytics": {
            "by_subtype": {d["_id"]: d["count"] for d in subtype_dist},
            "by_province": {d["_id"]: d["count"] for d in province_dist},
            "by_date": [{"date": d["_id"], "count": d["count"]} for d in date_dist],
        }
    }
