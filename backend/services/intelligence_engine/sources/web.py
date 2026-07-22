"""Source: web — description, logo, tags, contacts.

Behavior:
1. Cache-first: look up an agency_result linked to this master OR matching its domain.
2. If no cache and master has a domain → enqueue a scrape job (analysis_jobs) so
   the existing Playwright+LLM worker runs run_analysis() asynchronously. The next
   enrichment call will find the freshly created agency_result.

This makes the web source the single, canonical entry point for web enrichment
across all products. run_analysis() is no longer a separate pipeline.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Tuple

from database import db
from ..linker import normalize_domain, build_web_block

logger = logging.getLogger(__name__)

# How long a queued scrape stays valid before we re-enqueue it
SCRAPE_REQUEUE_TTL_SECONDS = 24 * 3600


META = {
    "display_name": "Web (scraping + LLM)",
    "collection": "agency_results",
    "frequency": "Bajo demanda (cola de scraping)",
    "signal_source": None,
    "audit_action": None,
    "phase": "active",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "display_fields": ["company_name", "category", "address_city", "address_province", "main_contact_email", "phone", "status"],
    "field_labels": {"company_name": "Empresa", "category": "Categoría", "address_city": "Ciudad", "address_province": "Provincia", "main_contact_email": "Email", "phone": "Teléfono", "status": "Estado"},
    "sidebar_dot": "bg-sky-500",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    master_id = master.get("master_company_id")
    domain_raw = master.get("domain") or master.get("website")
    domain = normalize_domain(domain_raw)

    if not domain:
        return {}, {"source": "web", "found": False, "reason": "no_domain"}

    # ── 1. Cache: by master backref first (strongest signal) ─────────────────
    ar = None
    if master_id:
        ar = await db.agency_results.find_one(
            {"master_company_id": master_id},
            sort=[("created_at", -1)],
        )

    # ── 2. Cache: by domain regex on input_url ───────────────────────────────
    if not ar:
        rx = f"^(?:https?://)?(?:www\\.)?{re.escape(domain)}(?:[:/?].*)?$"
        ar = await db.agency_results.find_one(
            {"input_url": {"$regex": rx, "$options": "i"}},
            sort=[("created_at", -1)],
        )
        # If we found one and master_id is set, opportunistically link it
        if ar and master_id and not ar.get("master_company_id"):
            try:
                await db.agency_results.update_one(
                    {"id": ar.get("id")},
                    {"$set": {"master_company_id": master_id, "linked_at": _now_iso()}},
                )
            except Exception:
                pass

    if ar:
        web = build_web_block(ar)
        # Re-shape into "web.*" dotted fields for the engine output
        fields = _flatten_web(web)
        return fields, {
            "source": "web",
            "found": True,
            "from_cache": True,
            "agency_result_id": ar.get("id"),
            "scraped_at": ar.get("created_at"),
            "domain": domain,
        }

    # ── 3. No cache → enqueue a scrape job (background worker picks it up) ───
    queued = await _enqueue_scrape(master, domain)
    return {}, {
        "source": "web",
        "found": False,
        "status": "scrape_queued" if queued else "scrape_already_queued",
        "domain": domain,
        "job_id": queued,
    }


# ── helpers ─────────────────────────────────────────────────────────────────
def _flatten_web(web: Dict) -> Dict:
    """Turn nested web block into dotted keys for engine output."""
    fields: Dict = {}
    for k, v in web.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            for sk, sv in v.items():
                fields[f"web.{k}.{sk}"] = sv
        else:
            fields[f"web.{k}"] = v
    if web.get("_agency_result_id"):
        fields["web._agency_result_id"] = web["_agency_result_id"]
    if web.get("_scraped_at"):
        fields["web._scraped_at"] = web["_scraped_at"]
    return fields


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _enqueue_scrape(master: Dict, domain: str) -> str:
    """Insert a job into analysis_jobs so the existing worker picks it up.

    Idempotency: don't re-enqueue if a recent job (pending/processing) already
    exists for the same master_company_id within SCRAPE_REQUEUE_TTL_SECONDS.
    """
    master_id = master.get("master_company_id")
    if not master_id:
        return ""

    # Skip if a recent job already exists
    cutoff = datetime.now(timezone.utc).timestamp() - SCRAPE_REQUEUE_TTL_SECONDS
    existing = await db.analysis_jobs.find_one({
        "metadata.master_company_id": master_id,
        "status": {"$in": ["pending", "claimed", "processing"]},
    })
    if existing:
        return ""

    url = master.get("website") or master.get("domain") or f"https://{domain}"
    if not url.startswith("http"):
        url = "https://" + url

    job_id = str(uuid.uuid4())
    now = _now_iso()
    await db.analysis_jobs.insert_one({
        "id": job_id,
        "url": url,
        "status": "pending",
        "consumer_id": "intelligence_engine",
        "entity_id": master_id,
        "metadata": {
            "master_company_id": master_id,
            "source": "intelligence_engine.web",
            "domain": domain,
            "queued_at": now,
        },
        "created_at": now,
    })
    logger.info(f"Intelligence Engine: queued scrape job {job_id[:12]} for master {master_id} url={url}")
    return job_id
