from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from auth_utils import get_current_user
from database import db

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("")
async def get_stats(user=Depends(get_current_user)):
    total_results = await db.agency_results.count_documents({})
    completed = await db.agency_results.count_documents({"status": "completed"})
    errors = await db.analysis_jobs.count_documents({"status": "error"})
    validated = await db.agency_results.count_documents({"validated": True})
    pending_review = await db.agency_results.count_documents({"review_status": "pending_review"})

    # Category distribution
    pipeline = [
        {"$match": {"category": {"$ne": None}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    cat_dist = await db.agency_results.aggregate(pipeline).to_list(10)
    category_distribution = [{"category": c["_id"], "count": c["count"]} for c in cat_dist]

    sub_pipeline = [
        {"$match": {"subcategory": {"$ne": None}}},
        {"$group": {"_id": "$subcategory", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    sub_dist = await db.agency_results.aggregate(sub_pipeline).to_list(10)
    subcategory_distribution = [{"subcategory": s["_id"], "count": s["count"]} for s in sub_dist]

    fields = [
        "company_name", "description", "category", "subcategory",
        "main_contact_email", "phone", "address_city", "country"
    ]
    field_completion = {}
    for field in fields:
        filled = await db.agency_results.count_documents({
            "$and": [{field: {"$ne": None}}, {field: {"$ne": ""}}]
        })
        field_completion[field] = round((filled / total_results * 100) if total_results > 0 else 0, 1)

    total_jobs = await db.analysis_jobs.count_documents({})
    success_rate = round((completed / total_jobs * 100) if total_jobs > 0 else 0, 1)

    return {
        "total_processed": total_results,
        "total_jobs": total_jobs,
        "completed": completed,
        "errors": errors,
        "validated": validated,
        "pending_review": pending_review,
        "success_rate": success_rate,
        "review_rate": round((validated / total_results * 100) if total_results > 0 else 0, 1),
        "category_distribution": category_distribution,
        "subcategory_distribution": subcategory_distribution,
        "field_completion": field_completion
    }


@router.get("/operational")
async def get_operational_stats(user=Depends(get_current_user)):
    """Full operational stats for the dashboard: pipeline, consumers, recent activity."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Pipeline stats
    pending = await db.analysis_jobs.count_documents({"status": "pending"})
    processing = await db.analysis_jobs.count_documents({"status": {"$in": ["processing", "claimed"]}})
    completed_today = await db.analysis_jobs.count_documents({"status": "completed", "completed_at": {"$gte": today_start}})
    errors_today = await db.analysis_jobs.count_documents({"status": "error", "completed_at": {"$gte": today_start}})
    received_today = await db.analysis_jobs.count_documents({"created_at": {"$gte": today_start}})
    callbacks_pending = await db.agency_results.count_documents({"callback_status": "pending"})
    callbacks_failed = await db.agency_results.count_documents({"callback_status": "failed"})

    # All time
    total_jobs = await db.analysis_jobs.count_documents({})
    total_completed = await db.analysis_jobs.count_documents({"status": "completed"})
    total_errors = await db.analysis_jobs.count_documents({"status": "error"})

    # Per-consumer breakdown
    consumer_pipeline = [
        {"$match": {"created_at": {"$gte": today_start}}},
        {"$group": {
            "_id": {"$ifNull": ["$consumer_id", {"$ifNull": ["$enrichment_source", "direct"]}]},
            "received": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
            "processing": {"$sum": {"$cond": [{"$in": ["$status", ["processing", "claimed", "pending"]]}, 1, 0]}}
        }},
        {"$sort": {"received": -1}}
    ]
    consumer_stats = await db.analysis_jobs.aggregate(consumer_pipeline).to_list(20)
    consumers = [{
        "consumer_id": c["_id"] or "direct",
        "received_today": c["received"],
        "completed_today": c["completed"],
        "errors_today": c["errors"],
        "in_progress": c["processing"]
    } for c in consumer_stats]

    # Recent jobs (last 10)
    recent = await db.analysis_jobs.find(
        {}, {"_id": 0, "id": 1, "url": 1, "status": 1, "consumer_id": 1,
             "enrichment_source": 1, "entity_id": 1, "cis_company_id": 1,
             "phase": 1, "created_at": 1, "completed_at": 1, "error_message": 1}
    ).sort("created_at", -1).limit(10).to_list(10)

    # Chromium process count
    chromium_count = 0
    try:
        import psutil
        for p in psutil.process_iter(['name']):
            if any(x in p.info['name'].lower() for x in ['chromium', 'chrome', 'headless_shell']):
                chromium_count += 1
    except Exception:
        pass

    return {
        "pipeline": {
            "received_today": received_today,
            "in_queue": pending,
            "processing": processing,
            "completed_today": completed_today,
            "errors_today": errors_today,
            "callbacks_pending": callbacks_pending,
            "callbacks_failed": callbacks_failed
        },
        "totals": {
            "all_time_jobs": total_jobs,
            "all_time_completed": total_completed,
            "all_time_errors": total_errors,
            "success_rate": round((total_completed / total_jobs * 100) if total_jobs > 0 else 0, 1)
        },
        "consumers": consumers,
        "recent_jobs": recent,
        "chromium_processes": chromium_count
    }


@router.get("/hub-dashboard")
async def hub_dashboard_stats(user=Depends(get_current_user)):
    """Unified stats for all 4 tools in the hub dashboard."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Scraper stats
    scraper_total = await db.agency_results.count_documents({})
    scraper_today = await db.analysis_jobs.count_documents({"created_at": {"$gte": today_start}})
    scraper_completed = await db.analysis_jobs.count_documents({"status": "completed"})
    scraper_errors = await db.analysis_jobs.count_documents({"status": "error"})
    scraper_pending = await db.analysis_jobs.count_documents({"status": {"$in": ["pending", "claimed", "processing"]}})

    # Document Generator stats
    doc_total = await db.document_outputs.count_documents({})
    doc_today = await db.document_jobs.count_documents({"created_at": {"$gte": today_start}})
    doc_completed = await db.document_jobs.count_documents({"status": "completed"})
    doc_failed = await db.document_jobs.count_documents({"status": "failed"})
    doc_templates = await db.document_templates.count_documents({})
    doc_brands = await db.document_brand_profiles.count_documents({})

    # BORME stats
    borme_events = await db.borme_events.count_documents({})
    borme_days = await db.borme_summaries.count_documents({"status": "completed"})
    borme_pdfs_ok = await db.borme_raw_items.count_documents({"status": "completed"})
    borme_pdfs_fail = await db.borme_raw_items.count_documents({"status": {"$in": ["download_failed", "extraction_failed"]}})
    borme_ma = await db.borme_events.count_documents({"event_type": "ma"})

    # Assets stats
    assets_total = await db.document_assets.count_documents({})
    brands_total = doc_brands or 3  # hardcoded defaults

    # Recent activity across all tools
    recent_scraper = await db.analysis_jobs.find(
        {}, {"_id": 0, "id": 1, "url": 1, "status": 1, "created_at": 1}
    ).sort("created_at", -1).limit(3).to_list(3)
    recent_docs = await db.document_jobs.find(
        {}, {"_id": 0, "job_id": 1, "template_id": 1, "output_format": 1, "status": 1, "created_at": 1}
    ).sort("created_at", -1).limit(3).to_list(3)
    recent_borme = await db.borme_summaries.find(
        {"status": "completed"}, {"_id": 0, "publication_date": 1, "events_extracted": 1, "updated_at": 1}
    ).sort("updated_at", -1).limit(3).to_list(3)

    # Editorial stats
    editorial_sources = await db.editorial_sources.count_documents({"active": True})
    editorial_items = await db.editorial_items.count_documents({})
    editorial_pending = await db.editorial_items.count_documents({"status": "new"})
    editorial_approved = await db.editorial_items.count_documents({"status": "approved"})
    editorial_digests = await db.editorial_digests.count_documents({})

    # Transaction Intelligence stats
    tx_total = await db.transactions_normalized.count_documents({"deleted": {"$ne": True}})
    tx_imported = await db.transactions_normalized.count_documents({"source_type": "file_import", "deleted": {"$ne": True}})
    tx_manual = await db.transactions_normalized.count_documents({"source_type": "manual", "deleted": {"$ne": True}})
    tx_pending_review = await db.transactions_normalized.count_documents({"review_status": "pending", "deleted": {"$ne": True}})
    tx_dupes = await db.transaction_dedupe_candidates.count_documents({"review_status": "pending"})
    tx_approved_cis = await db.transactions_normalized.count_documents({"publish_status": "approved_for_cis", "deleted": {"$ne": True}})
    tx_matching_review = await db.transactions_normalized.count_documents({"matching_status": "needs_review", "deleted": {"$ne": True}})
    tx_recent = await db.transactions_normalized.find(
        {"deleted": {"$ne": True}},
        {"_id": 0, "transaction_id": 1, "target_name": 1, "buyer_name": 1, "publish_status": 1, "created_at": 1}
    ).sort("created_at", -1).limit(3).to_list(3)

    result = {
        "scraper": {
            "total_results": scraper_total,
            "today": scraper_today,
            "completed": scraper_completed,
            "errors": scraper_errors,
            "in_progress": scraper_pending,
            "success_rate": round(scraper_completed / max(scraper_completed + scraper_errors, 1) * 100, 1),
            "recent": [{"url": j.get("url", "")[:50], "status": j["status"], "at": j.get("created_at", "")[:19]} for j in recent_scraper]
        },
        "documents": {
            "total_outputs": doc_total,
            "today": doc_today,
            "completed": doc_completed,
            "failed": doc_failed,
            "templates": doc_templates,
            "brands": brands_total,
            "recent": [{"template": j.get("template_id", ""), "format": j.get("output_format", ""), "status": j["status"], "at": j.get("created_at", "")[:19]} for j in recent_docs]
        },
        "borme": {
            "total_events": borme_events,
            "days_processed": borme_days,
            "pdfs_processed": borme_pdfs_ok,
            "pdfs_failed": borme_pdfs_fail,
            "ma_events": borme_ma,
            "success_rate": round(borme_pdfs_ok / max(borme_pdfs_ok + borme_pdfs_fail, 1) * 100, 1),
            "recent": [{"date": s.get("publication_date", ""), "events": s.get("events_extracted", 0)} for s in recent_borme]
        },
        "editorial": {
            "sources_active": editorial_sources,
            "items_total": editorial_items,
            "items_pending": editorial_pending,
            "items_approved": editorial_approved,
            "digests": editorial_digests,
        },
        "transactions": {
            "total": tx_total,
            "imported": tx_imported,
            "manual": tx_manual,
            "pending_review": tx_pending_review,
            "possible_duplicates": tx_dupes,
            "approved_for_cis": tx_approved_cis,
            "matching_needs_review": tx_matching_review,
            "recent": [{"target": t.get("target_name", "")[:40], "buyer": (t.get("buyer_name") or "")[:30], "status": t.get("publish_status", ""), "at": (t.get("created_at") or "")[:19]} for t in tx_recent]
        },
    }

    # Add providers data
    providers = await db.data_providers.find({"active": True}, {"_id": 0, "api_key": 0}).to_list(10)
    providers_data = []
    for p in providers:
        last_file = await db.provider_files.find_one(
            {"provider_id": p["provider_id"]}, {"_id": 0},
            sort=[("uploaded_at", -1)]
        )
        total_files = await db.provider_files.count_documents({"provider_id": p["provider_id"]})
        providers_data.append({
            "provider_id": p["provider_id"],
            "name": p.get("name"),
            "frequency": p.get("frequency", "weekly"),
            "total_uploads": total_files,
            "last_upload_at": p.get("last_upload_at"),
            "last_filename": p.get("last_filename"),
            "last_file_size": p.get("last_file_size"),
            "last_file": {
                "file_id": last_file["file_id"],
                "filename": last_file["filename"],
                "size_bytes": last_file["size_bytes"],
                "checksum_sha256": last_file.get("checksum_sha256"),
                "status": last_file["status"],
                "uploaded_at": last_file["uploaded_at"],
            } if last_file else None,
        })
    result["providers"] = providers_data

    return result
