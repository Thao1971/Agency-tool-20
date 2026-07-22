"""Document Worker — MongoDB-based async job processor for PDF and PPTX generation."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from database import db
from services.storage import put_object

logger = logging.getLogger(__name__)

_running = False
_active = 0
POLL_INTERVAL = 3


async def start_doc_worker():
    global _running
    if _running:
        return
    _running = True
    logger.info("Document worker started")
    asyncio.create_task(_doc_worker_loop())


async def _doc_worker_loop():
    global _running, _active

    while _running:
        try:
            if _active >= 2:  # Max 2 concurrent doc generations
                await asyncio.sleep(POLL_INTERVAL)
                continue

            job = await db.document_jobs.find_one_and_update(
                {"status": "queued", "job_type": "document_generation"},
                {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc).isoformat()}},
                sort=[("created_at", 1)],
                return_document=True
            )

            if not job:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            asyncio.create_task(_process_doc_job(job))

        except Exception as e:
            logger.error(f"Doc worker loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


async def _process_doc_job(job: dict):
    global _active
    _active += 1
    job_id = job["job_id"]

    try:
        logger.info(f"DocWorker: processing {job_id} ({job['output_format']})")

        # Get template
        template = await db.document_templates.find_one(
            {"template_id": job["template_id"]}, {"_id": 0}
        )
        if not template:
            raise ValueError(f"Template {job['template_id']} not found")

        # Get brand
        brand = None
        if job.get("brand_id"):
            brand = await db.document_brand_profiles.find_one(
                {"brand_id": job["brand_id"]}, {"_id": 0}
            )

        # Build manifest
        manifest = {
            "template_id": job["template_id"],
            "template_version": job.get("template_version"),
            "brand_id": job.get("brand_id"),
            "output_format": job["output_format"],
            "locale": job.get("locale", "es"),
            "source_app": job.get("source_app"),
            "source_entity_type": job.get("source_entity_type"),
            "source_entity_id": job.get("source_entity_id"),
            "data_payload": job.get("data_payload", {}),
            "generated_blocks": job.get("generated_blocks", {}),
            "manual_overrides": job.get("manual_overrides", {}),
            "legal_footer": template.get("legal_disclaimer"),
            "sections": template.get("sections", []),
            "assets": []
        }

        # Render
        output_bytes = None
        content_type = None
        ext = None

        if job["output_format"] == "pdf":
            await db.document_jobs.update_one(
                {"job_id": job_id}, {"$set": {"phase": "rendering_pdf"}}
            )

            # Route to appropriate renderer based on template type
            doc_type = template.get("document_type", "report")
            if doc_type == "valuation":
                from documents.renderers.valuation_renderer import build_valuation_report
                from documents.renderers import render_pdf
                html, css = build_valuation_report(manifest.get("data_payload", {}), brand)
            else:
                from documents.renderers import render_pdf, build_html_from_manifest
                html_tpl = template.get("html_template")
                css_tpl = template.get("css_template")
                html, css = build_html_from_manifest(manifest, html_tpl, css_tpl, brand)

            output_bytes = render_pdf(html, css)
            content_type = "application/pdf"
            ext = "pdf"

        elif job["output_format"] == "pptx":
            await db.document_jobs.update_one(
                {"job_id": job_id}, {"$set": {"phase": "rendering_pptx"}}
            )
            from documents.renderers.pptx_renderer import render_pptx
            output_bytes = render_pptx(manifest, brand)
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ext = "pptx"

        else:
            raise ValueError(f"Unsupported format: {job['output_format']}")

        # Validate output quality
        MIN_PDF_SIZE = 5000  # 5KB minimum — anything less is broken
        MIN_PPTX_SIZE = 10000
        min_size = MIN_PDF_SIZE if ext == "pdf" else MIN_PPTX_SIZE
        if len(output_bytes) < min_size:
            raise ValueError(f"Output too small ({len(output_bytes)} bytes). Render likely failed. Min: {min_size}")

        # Upload to storage
        await db.document_jobs.update_one(
            {"job_id": job_id}, {"$set": {"phase": "uploading"}}
        )
        output_id = f"out_{str(uuid.uuid4())[:12]}"
        storage_path = f"agency-scraper/documents/{output_id}/{job_id}.{ext}"
        put_object(storage_path, output_bytes, content_type)

        # Save output record
        now = datetime.now(timezone.utc).isoformat()
        output = {
            "output_id": output_id,
            "job_id": job_id,
            "template_id": job["template_id"],
            "output_format": ext,
            "storage_path": storage_path,
            "content_type": content_type,
            "size_bytes": len(output_bytes),
            "source_app": job.get("source_app"),
            "source_entity_id": job.get("source_entity_id"),
            "created_by": job.get("created_by"),
            "created_at": now
        }
        await db.document_outputs.insert_one({**output})

        # Mark job complete
        await db.document_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "completed",
                "phase": None,
                "output_id": output_id,
                "completed_at": now
            }}
        )

        # Audit
        await db.document_audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": "generation_completed",
            "job_id": job_id,
            "output_id": output_id,
            "template_id": job["template_id"],
            "output_format": ext,
            "size_bytes": len(output_bytes),
            "user": job.get("created_by"),
            "timestamp": now
        })

        logger.info(f"DocWorker: completed {job_id} → {output_id} ({len(output_bytes)} bytes)")

    except Exception as e:
        logger.error(f"DocWorker: job {job_id} failed: {e}")
        await db.document_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "failed",
                "error_message": str(e)[:500],
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    finally:
        _active -= 1
        import gc
        gc.collect()


async def stop_doc_worker():
    global _running
    _running = False
    logger.info("Document worker stopped")
