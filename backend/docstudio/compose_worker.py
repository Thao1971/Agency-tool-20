"""Async document composition + in-platform notifications (Fase 4, decisión 9).

A document takes time to compose (data + AI narrative). The user must NOT wait: the
compose request is queued, a background worker composes it, and on completion an
in-platform notification is written. The UI shows an estimated time (ETA) from real
telemetry, and a notification bell.

Additive: the synchronous `POST /compose/*` endpoints stay for backward compatibility;
this adds `POST /compose-async`. Email notification is a SEPARATE infra dependency
(no SMTP/SES/SendGrid connected yet) — documented, not implemented here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

_running = False
POLL_SECONDS = 3


# Dispatch: doc_type -> async composer call built from the job's params.
async def _dispatch(doc_type: str, params: Dict, brand_id: str, user: Optional[str]) -> Dict:
    from docstudio import composer as C
    p = params or {}
    if doc_type == "sector_report":
        return await C.compose_sector_report(p.get("cnae_code"), brand_id, user)
    if doc_type == "benchmark":
        return await C.compose_benchmark_report(p.get("cnae_code"), brand_id, user)
    if doc_type == "benchmark_advanced":
        return await C.compose_benchmark_advanced(p.get("cnae_code"), p.get("company_id"), brand_id, user)
    if doc_type == "company_profile":
        return await C.compose_company_profile(p.get("company_id"), p.get("cif"), brand_id, user)
    if doc_type == "company_snapshot":
        return await C.compose_company_snapshot(p.get("company_id"), p.get("cif"), brand_id, user)
    if doc_type == "teaser":
        return await C.compose_teaser(p.get("company_id"), p.get("cif"), brand_id, user)
    if doc_type == "investment_memo":
        return await C.compose_investment_memo(p.get("company_id"), p.get("cif"), brand_id, user)
    if doc_type == "information_memorandum":
        return await C.compose_information_memorandum(p.get("company_id"), p.get("cif"), brand_id, user)
    if doc_type == "opportunities":
        return await C.compose_opportunities_document(
            cnae_section=p.get("cnae_section"), provincia=p.get("provincia"),
            signal_types=p.get("signal_types"), mandate_id=p.get("mandate_id"),
            brand_id=brand_id, user=user, limit=p.get("limit", 40))
    if doc_type == "from_template":
        return await C.compose_from_template(p.get("template_id"), company_id=p.get("company_id"),
            cif=p.get("cif"), cnae_code=p.get("cnae_code"), brand_id=brand_id, user=user)
    if doc_type == "ranking":
        return await C.compose_ranking_document(cnae_section=p.get("cnae_section"), cnae_code=p.get("cnae_code"),
            provincia=p.get("provincia"), sort_by=p.get("sort_by", "revenue"), brand_id=brand_id, user=user,
            limit=p.get("limit", 25))
    if doc_type == "fragmentation":
        return await C.compose_fragmentation_document(cnae_section=p.get("cnae_section"),
            cnae_code=p.get("cnae_code"), brand_id=brand_id, user=user)
    if doc_type == "rollup":
        return await C.compose_rollup_document(cnae_section=p.get("cnae_section"),
            cnae_code=p.get("cnae_code"), brand_id=brand_id, user=user)
    if doc_type == "succession":
        return await C.compose_succession_document(company_id=p.get("company_id"), cif=p.get("cif"),
            brand_id=brand_id, user=user)
    if doc_type == "valuation_approx":
        return await C.compose_valuation_approx(company_id=p.get("company_id"), cif=p.get("cif"),
            brand_id=brand_id, user=user)
    if doc_type == "valuation_advanced":
        return await C.compose_valuation_advanced(company_id=p.get("company_id"), cif=p.get("cif"),
            brand_id=brand_id, user=user)
    if doc_type == "strategic_analysis":
        return await C.compose_strategic_analysis(company_id=p.get("company_id"), cif=p.get("cif"),
            brand_id=brand_id, user=user)
    if doc_type == "comparative":
        return await C.compose_comparative_analysis(company_id=p.get("company_id"), cif=p.get("cif"),
            brand_id=brand_id, user=user)
    return {"error": f"Unknown doc_type: {doc_type}"}


async def notify(user: Optional[str], ntype: str, title: str,
                 document_id: Optional[str] = None, level: str = "info") -> Dict:
    """Write an in-platform notification."""
    doc = {
        "notification_id": f"ntf_{new_id()[:12]}",
        "user": user, "type": ntype, "title": title,
        "document_id": document_id, "level": level,
        "read": False, "created_at": now_iso(),
    }
    await db.docstudio_notifications.insert_one({**doc})
    return doc


async def estimate_ms(doc_type: str) -> Optional[int]:
    """ETA from REAL telemetry: average generation time of this document type.
    Falls back to the overall average, then None (never a fabricated number)."""
    pipeline = [
        {"$match": {"metadata.type": doc_type, "metadata.generation_time_ms": {"$exists": True}}},
        {"$group": {"_id": None, "avg": {"$avg": "$metadata.generation_time_ms"}}},
    ]
    r = await db.docstudio_documents.aggregate(pipeline).to_list(1)
    if r and r[0].get("avg"):
        return round(r[0]["avg"])
    r2 = await db.docstudio_documents.aggregate([
        {"$match": {"metadata.generation_time_ms": {"$exists": True}}},
        {"$group": {"_id": None, "avg": {"$avg": "$metadata.generation_time_ms"}}},
    ]).to_list(1)
    if r2 and r2[0].get("avg"):
        return round(r2[0]["avg"])
    return None


async def enqueue_compose(doc_type: str, params: Dict, brand_id: str, user: Optional[str]) -> Dict:
    """Queue an async compose job. Returns job_id + ETA (never blocks the user)."""
    job = {
        "job_id": f"cjob_{new_id()[:12]}",
        "doc_type": doc_type, "params": params or {}, "brand_id": brand_id or "brand_bud",
        "user": user, "status": "queued", "document_id": None, "error": None,
        "created_at": now_iso(), "started_at": None, "finished_at": None,
    }
    await db.docstudio_compose_jobs.insert_one({**job})
    eta = await estimate_ms(doc_type)
    return {"job_id": job["job_id"], "status": "queued", "eta_ms": eta}


async def _run_compose_job(job: Dict) -> Dict:
    """Execute one compose job: dispatch, persist status, write a notification."""
    jid = job["job_id"]
    await db.docstudio_compose_jobs.update_one(
        {"job_id": jid}, {"$set": {"status": "running", "started_at": now_iso()}})
    try:
        doc = await _dispatch(job["doc_type"], job.get("params", {}),
                              job.get("brand_id", "brand_bud"), job.get("user"))
        if not doc or "error" in doc:
            msg = (doc or {}).get("error", "Error desconocido")
            await db.docstudio_compose_jobs.update_one(
                {"job_id": jid}, {"$set": {"status": "error", "error": msg, "finished_at": now_iso()}})
            await notify(job.get("user"), "document_failed",
                         f"No se pudo generar el documento: {msg}", level="error")
            return {"status": "error", "error": msg}
        await db.docstudio_compose_jobs.update_one(
            {"job_id": jid}, {"$set": {"status": "done", "document_id": doc["document_id"],
                                       "finished_at": now_iso()}})
        await notify(job.get("user"), "document_ready",
                     f"Documento listo: {doc.get('title', 'Documento')}",
                     document_id=doc["document_id"], level="success")
        return {"status": "done", "document_id": doc["document_id"]}
    except Exception as e:  # noqa: BLE001
        logger.exception("compose job %s failed", jid)
        await db.docstudio_compose_jobs.update_one(
            {"job_id": jid}, {"$set": {"status": "error", "error": str(e), "finished_at": now_iso()}})
        await notify(job.get("user"), "document_failed", f"Error generando documento: {e}", level="error")
        return {"status": "error", "error": str(e)}


async def _loop():
    global _running
    while _running:
        try:
            job = await db.docstudio_compose_jobs.find_one_and_update(
                {"status": "queued"}, {"$set": {"status": "claimed"}},
                sort=[("created_at", 1)])
            if not job:
                await asyncio.sleep(POLL_SECONDS)
                continue
            await _run_compose_job(job)
        except Exception:  # noqa: BLE001
            logger.exception("compose worker loop error")
            await asyncio.sleep(POLL_SECONDS)


async def start_compose_worker():
    global _running
    if _running:
        return
    _running = True
    logger.info("DocStudio compose worker started")
    asyncio.create_task(_loop())


async def stop_compose_worker():
    global _running
    _running = False
