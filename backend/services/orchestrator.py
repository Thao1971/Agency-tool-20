"""Job Orchestrator: manages the analysis pipeline from scraping to persistence."""

import logging
import uuid
import os
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional
from database import db
from services.scraper import scrape_website, compile_text_content
from services.parser import parse_page_content, aggregate_parsed_data
from services.classifier import classify_agency
from services.storage import upload_screenshot

logger = logging.getLogger(__name__)


async def get_scraper_config() -> Dict:
    config = await db.scraper_config.find_one({}, {"_id": 0})
    if not config:
        config = {
            "id": str(uuid.uuid4()),
            "max_depth": 2,
            "max_pages": 10,
            "capture_internal_pages": True,
            "priority_patterns": [
                "about", "nosotros", "quienes-somos", "quien-somos",
                "servicios", "services", "work", "trabajos", "portfolio",
                "clientes", "clients", "casos", "case",
                "equipo", "team", "premios", "awards",
                "contacto", "contact"
            ],
            "timeout_seconds": 30,
            "concurrency_limit": 3,
            "export_format": "json",
            "callback_url": None,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.scraper_config.insert_one({**config})
    return config


async def log_processing(job_id: str, phase: str, level: str, message: str, metadata: Dict = None):
    await db.processing_logs.insert_one({
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "phase": phase,
        "level": level,
        "message": message,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


async def run_analysis(job_id: str, url: str) -> Dict:
    """Execute the full analysis pipeline for a single URL."""
    now = datetime.now(timezone.utc).isoformat()

    # Update job to processing
    await db.analysis_jobs.update_one(
        {"id": job_id},
        {"$set": {"status": "processing", "phase": "scraping", "started_at": now}}
    )
    await log_processing(job_id, "scraping", "info", f"Starting scrape for {url}")

    result_id = str(uuid.uuid4())

    try:
        # Phase 1: Scraping
        config = await get_scraper_config()
        scrape_result = await scrape_website(url, config)
        await log_processing(job_id, "scraping", "info",
            f"Scraped {len(scrape_result.get('visited_pages', []))} pages")

        # Upload screenshot
        screenshot_path = None
        if scrape_result.get("screenshot_bytes"):
            try:
                await db.analysis_jobs.update_one(
                    {"id": job_id}, {"$set": {"phase": "storage"}}
                )
                screenshot_path = upload_screenshot(scrape_result["screenshot_bytes"], result_id)
                await db.screenshots.insert_one({
                    "id": str(uuid.uuid4()),
                    "result_id": result_id,
                    "storage_path": screenshot_path,
                    "original_url": url,
                    "content_type": "image/png",
                    "created_at": now
                })
                await log_processing(job_id, "storage", "info", "Screenshot uploaded")
            except Exception as e:
                logger.warning(f"Screenshot upload failed: {e}")
                await log_processing(job_id, "storage", "warning", f"Screenshot upload failed: {e}")
            finally:
                # Free screenshot bytes from memory immediately
                scrape_result["screenshot_bytes"] = None

        # Upload logo if found
        logo_storage_path = None
        logo_url_original = scrape_result.get("logo_url")
        if logo_url_original and not logo_url_original.startswith("data:"):
            try:
                import requests as req_lib
                logo_resp = req_lib.get(logo_url_original, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
                })
                if logo_resp.status_code == 200 and len(logo_resp.content) > 100:
                    ct = logo_resp.headers.get("Content-Type", "image/png")
                    ext = "svg" if "svg" in ct else "png" if "png" in ct else "jpg"
                    from services.storage import put_object
                    logo_path = f"{os.environ.get('APP_NAME', 'agency-scraper')}/logos/{result_id}/{str(uuid.uuid4())}.{ext}"
                    put_object(logo_path, logo_resp.content, ct)
                    logo_storage_path = logo_path
                    await log_processing(job_id, "storage", "info",
                        f"Logo uploaded ({scrape_result.get('logo_source', '?')})")
            except Exception as e:
                logger.warning(f"Logo download/upload failed: {e}")

        # Phase 2: Parsing
        await db.analysis_jobs.update_one(
            {"id": job_id}, {"$set": {"phase": "parsing"}}
        )

        pages_data = []
        homepage_text = scrape_result.get("homepage_text", "")
        if homepage_text:
            pages_data.append(parse_page_content(homepage_text, url))

        for page_content in scrape_result.get("pages_content", []):
            pages_data.append(parse_page_content(
                page_content.get("text", ""),
                page_content.get("url", "")
            ))

        parsed = aggregate_parsed_data(pages_data)
        await log_processing(job_id, "parsing", "info",
            f"Found {len(parsed['emails'])} emails, {len(parsed['phones'])} phones")

        # Create evidence items for parsed data
        evidence_items = []
        for email in parsed["emails"]:
            evidence_items.append({
                "id": str(uuid.uuid4()),
                "result_id": result_id,
                "field": "contact",
                "evidence_type": "email",
                "source_url": url,
                "fragment": email,
                "confidence": 95,
                "detected_by": "parser",
                "created_at": now
            })
        for phone in parsed["phones"]:
            evidence_items.append({
                "id": str(uuid.uuid4()),
                "result_id": result_id,
                "field": "contact",
                "evidence_type": "phone",
                "source_url": url,
                "fragment": phone,
                "confidence": 90,
                "detected_by": "parser",
                "created_at": now
            })
        for addr in parsed["addresses"]:
            evidence_items.append({
                "id": str(uuid.uuid4()),
                "result_id": result_id,
                "field": "address",
                "evidence_type": "address",
                "source_url": url,
                "fragment": addr,
                "confidence": 70,
                "detected_by": "parser",
                "created_at": now
            })

        # Phase 3: LLM Classification
        await db.analysis_jobs.update_one(
            {"id": job_id}, {"$set": {"phase": "llm"}}
        )
        await log_processing(job_id, "llm", "info", "Starting LLM classification")

        combined_text = compile_text_content(scrape_result)
        classification = await classify_agency(
            combined_text,
            parsed,
            url,
            scrape_result.get("visited_pages", [url])
        )

        # Add LLM evidence items
        evidence_notes = classification.get("evidence_notes", {})
        for field_name, note in evidence_notes.items():
            if note:
                evidence_items.append({
                    "id": str(uuid.uuid4()),
                    "result_id": result_id,
                    "field": field_name,
                    "evidence_type": "text",
                    "source_url": url,
                    "fragment": str(note)[:500],
                    "confidence": classification.get(f"confidence_{field_name}", 50),
                    "detected_by": "llm",
                    "created_at": now
                })

        await log_processing(job_id, "llm", "info",
            f"Classification complete. Category: {classification.get('category')}")

        # Phase 4: Validation
        await db.analysis_jobs.update_one(
            {"id": job_id}, {"$set": {"phase": "validation"}}
        )

        # Validate category against taxonomy
        if classification.get("category"):
            cat = await db.taxonomy_categories.find_one(
                {"name": classification["category"], "active": True}, {"_id": 0}
            )
            if not cat:
                classification["category"] = None
                classification["subcategory"] = None
                classification["confidence_category"] = 0
                await log_processing(job_id, "validation", "warning",
                    f"Category '{classification.get('category')}' not in active taxonomy")

        # Use parser-detected email as main contact email if LLM didn't find one
        if not classification.get("main_contact_email") and parsed["emails"]:
            classification["main_contact_email"] = parsed["emails"][0]

        # Get taxonomy version
        tax_ver = await db.taxonomy_categories.find_one({}, {"_id": 0, "taxonomy_version": 1})
        taxonomy_version = tax_ver.get("taxonomy_version", "v1.0") if tax_ver else "v1.0"

        # Phase 5: Persistence
        await db.analysis_jobs.update_one(
            {"id": job_id}, {"$set": {"phase": "persistence"}}
        )

        agency_result = {
            "id": result_id,
            "job_id": job_id,
            "input_url": url,
            "company_name": classification.get("company_name"),
            "description": classification.get("description"),
            "category": classification.get("category"),
            "subcategory": classification.get("subcategory"),
            "tags": classification.get("tags", []),
            "has_awards": bool(classification.get("has_awards", False)),
            "awards_evidence": classification.get("awards_evidence") or [],
            "main_clients": classification.get("main_clients") or [],
            "main_contact_name": classification.get("main_contact_name"),
            "main_contact_role": classification.get("main_contact_role"),
            "main_contact_email": classification.get("main_contact_email"),
            "phone": parsed["phones"][0] if parsed["phones"] else classification.get("phone"),
            "address_street": classification.get("address_street"),
            "address_city": classification.get("address_city"),
            "address_province": classification.get("address_province"),
            "postal_code": classification.get("postal_code") or (parsed["postal_codes"][0] if parsed["postal_codes"] else None),
            "country": classification.get("country"),
            "screenshot_path": screenshot_path,
            "logo_url": logo_url_original,
            "logo_storage_path": logo_storage_path,
            "logo_source": scrape_result.get("logo_source"),
            "candidate_pages": scrape_result.get("candidate_pages", []),
            "visited_pages": scrape_result.get("visited_pages", []),
            "failed_pages": scrape_result.get("failed_pages", []),
            "skipped_pages": scrape_result.get("skipped_pages", []),
            "confidence_overall": int(classification.get("confidence_overall") or 0),
            "confidence_category": int(classification.get("confidence_category") or 0),
            "confidence_clients": int(classification.get("confidence_clients") or 0),
            "confidence_contact": int(classification.get("confidence_contact") or 0),
            "confidence_awards": int(classification.get("confidence_awards") or 0),
            "confidence_address": int(classification.get("confidence_address") or 0),
            "confidence_description": int(classification.get("confidence_description") or 0),
            "taxonomy_version": taxonomy_version,
            "status": "completed",
            "review_status": "pending_review",
            "validated": False,
            "validated_by": None,
            "validated_at": None,
            "last_edited_by": None,
            "last_edited_at": None,
            "created_at": now
        }

        await db.agency_results.insert_one({**agency_result})

        # Store evidence items
        if evidence_items:
            await db.evidence_items.insert_many([{**e} for e in evidence_items])

        # Update job as completed
        completed_at = datetime.now(timezone.utc).isoformat()
        await db.analysis_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "completed",
                "result_id": result_id,
                "phase": None,
                "completed_at": completed_at
            }}
        )
        await log_processing(job_id, "persistence", "info", "Analysis completed and persisted")

        # Free large objects from memory
        del scrape_result, evidence_items, combined_text, classification
        import gc
        gc.collect()

        return agency_result

    except Exception as e:
        logger.error(f"Analysis pipeline failed for {url}: {e}")
        await db.analysis_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "error",
                "error_message": str(e)[:500],
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        await log_processing(job_id, "orchestrator", "error", f"Pipeline failed: {e}")
        import gc
        gc.collect()
        raise


async def run_bulk_analysis(bulk_job_id: str):
    """Process all items in a bulk job."""
    bulk_job = await db.bulk_jobs.find_one({"id": bulk_job_id}, {"_id": 0})
    if not bulk_job:
        return

    await db.bulk_jobs.update_one(
        {"id": bulk_job_id},
        {"$set": {"status": "processing"}}
    )

    items = await db.bulk_job_items.find(
        {"bulk_job_id": bulk_job_id, "status": "pending"},
        {"_id": 0}
    ).sort("order", 1).to_list(10000)

    config = await get_scraper_config()
    concurrency = config.get("concurrency_limit", 3)
    semaphore = asyncio.Semaphore(concurrency)

    async def process_item(item):
        async with semaphore:
            job_id = item["job_id"]
            try:
                await db.bulk_job_items.update_one(
                    {"id": item["id"]}, {"$set": {"status": "processing"}}
                )
                result = await run_analysis(job_id, item["url"])
                await db.bulk_job_items.update_one(
                    {"id": item["id"]},
                    {"$set": {
                        "status": "completed",
                        "result_id": result["id"],
                        "completed_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                await db.bulk_jobs.update_one(
                    {"id": bulk_job_id},
                    {"$inc": {"processed": 1, "succeeded": 1}}
                )
            except Exception as e:
                await db.bulk_job_items.update_one(
                    {"id": item["id"]},
                    {"$set": {
                        "status": "error",
                        "error_message": str(e)[:500],
                        "completed_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                await db.bulk_jobs.update_one(
                    {"id": bulk_job_id},
                    {"$inc": {"processed": 1, "failed": 1}}
                )

    tasks = [process_item(item) for item in items]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Update bulk job status
    bulk = await db.bulk_jobs.find_one({"id": bulk_job_id}, {"_id": 0})
    final_status = "completed"
    if bulk and bulk.get("failed", 0) > 0:
        final_status = "partial" if bulk.get("succeeded", 0) > 0 else "error"

    await db.bulk_jobs.update_one(
        {"id": bulk_job_id},
        {"$set": {
            "status": final_status,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    # Fire webhook if configured
    if bulk_job.get("callback_url"):
        await _fire_webhook(bulk_job["callback_url"], {
            "event": "bulk.completed",
            "bulk_job_id": bulk_job_id,
            "status": final_status
        })


async def _fire_webhook(url: str, payload: Dict):
    import requests as req
    try:
        req.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"Webhook failed to {url}: {e}")
