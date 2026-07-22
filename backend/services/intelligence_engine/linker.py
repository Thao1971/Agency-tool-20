"""Link agency_results to companies_master — bidirectional bridge.

Two purposes:
1. One-shot migration of historical agency_results that exist before Phase 2.
2. Post-hook for the worker: when run_analysis() finishes from a scrape that
   was queued by the engine, push the result into master.sources.web and link
   the agency_result back to its master.

Lineage convention:
- master.sources.web = {description, category, tags, logo_storage_path, ...}
- master.last_enriched_at, master.enrichment_source = 'intelligence_engine'
- agency_result.master_company_id = backref
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from database import db
from models import now_iso

logger = logging.getLogger(__name__)


# ── domain normalization ────────────────────────────────────────────────────
def normalize_domain(value: str) -> Optional[str]:
    """Return apex domain (no scheme, no www, no path). None if invalid."""
    if not value:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if "://" not in v:
        v = "http://" + v
    try:
        host = urlparse(v).netloc or urlparse(v).path
    except Exception:
        return None
    host = host.split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    host = host.split(":")[0]  # strip port
    if not host or "." not in host:
        return None
    return host


# ── per-result mapping ──────────────────────────────────────────────────────
WEB_FIELD_MAP = {
    "company_name":        "company_name",
    "description":         "description",
    "category":            "category",
    "subcategory":         "subcategory",
    "tags":                "tags",
    "logo_storage_path":   "logo_storage_path",
    "logo_url":            "logo_url",
    "main_contact_email":  "contact_email",
    "main_contact_name":   "contact_name",
    "main_contact_role":   "contact_role",
    "phone":               "phone",
    "address_street":      "address.street",
    "address_city":        "address.city",
    "address_province":    "address.province",
    "postal_code":         "address.postal_code",
    "country":             "address.country",
    "main_clients":        "main_clients",
    "has_awards":          "has_awards",
    "awards_evidence":     "awards_evidence",
    "confidence_category": "confidence_category",
    "confidence_description": "confidence_description",
}


def build_web_block(agency_result: Dict) -> Dict:
    """Translate an agency_result document into the master.sources.web subdocument."""
    web: Dict = {}
    for src_key, dst_path in WEB_FIELD_MAP.items():
        v = agency_result.get(src_key)
        if v in (None, "", [], {}):
            continue
        if "." in dst_path:
            top, sub = dst_path.split(".", 1)
            web.setdefault(top, {})[sub] = v
        else:
            web[dst_path] = v
    web["_agency_result_id"] = agency_result.get("id")
    web["_scraped_at"] = agency_result.get("created_at")
    web["_input_url"] = agency_result.get("input_url")
    return web


# ── core linking ────────────────────────────────────────────────────────────
async def link_one(agency_result: Dict, master_company_id: str) -> Dict:
    """Push one agency_result into master.sources.web and set the backref."""
    web = build_web_block(agency_result)
    now = now_iso()

    update = {
        "sources.web": web,
        "last_enriched_at": now,
        "enrichment_source": "intelligence_engine",
        "updated_at": now,
    }
    await db.companies_master.update_one(
        {"master_company_id": master_company_id},
        {"$set": update},
    )

    await db.agency_results.update_one(
        {"id": agency_result.get("id")},
        {"$set": {"master_company_id": master_company_id, "linked_at": now}},
    )

    return {
        "agency_result_id": agency_result.get("id"),
        "master_company_id": master_company_id,
        "fields_linked": list(web.keys()),
    }


# ── bulk migration ──────────────────────────────────────────────────────────
async def migrate_all(dry_run: bool = False) -> Dict:
    """One-shot migration. Scan all agency_results, link each to its master by
    domain match. Returns counters + per-result decisions.
    """
    cursor = db.agency_results.find(
        {}, {"_id": 0, "id": 1, "input_url": 1, "company_name": 1, "description": 1,
             "category": 1, "subcategory": 1, "tags": 1, "logo_storage_path": 1,
             "logo_url": 1, "main_contact_email": 1, "main_contact_name": 1,
             "main_contact_role": 1, "phone": 1, "address_street": 1,
             "address_city": 1, "address_province": 1, "postal_code": 1,
             "country": 1, "main_clients": 1, "has_awards": 1, "awards_evidence": 1,
             "confidence_category": 1, "confidence_description": 1,
             "created_at": 1, "master_company_id": 1},
    )
    stats = {"scanned": 0, "linked": 0, "already_linked": 0, "no_domain": 0,
             "no_master_match": 0, "errors": 0, "dry_run": dry_run, "details": []}

    async for ar in cursor:
        stats["scanned"] += 1
        if ar.get("master_company_id"):
            stats["already_linked"] += 1
            continue

        domain = normalize_domain(ar.get("input_url"))
        if not domain:
            stats["no_domain"] += 1
            continue

        # Try several match strategies
        master = await _find_master_by_domain(domain)
        if not master:
            stats["no_master_match"] += 1
            if len(stats["details"]) < 50:
                stats["details"].append({"agency_result_id": ar.get("id"), "domain": domain, "status": "no_master"})
            continue

        try:
            if dry_run:
                stats["linked"] += 1
                if len(stats["details"]) < 50:
                    stats["details"].append({
                        "agency_result_id": ar.get("id"), "domain": domain,
                        "master_company_id": master["master_company_id"], "status": "would_link"})
            else:
                res = await link_one(ar, master["master_company_id"])
                stats["linked"] += 1
                if len(stats["details"]) < 50:
                    stats["details"].append({**res, "domain": domain, "status": "linked"})
        except Exception as e:
            stats["errors"] += 1
            logger.exception(f"link_one failed for {ar.get('id')}")

    return stats


async def _find_master_by_domain(domain: str) -> Optional[Dict]:
    """Look up a master by domain or website with tolerant matching."""
    if not domain:
        return None

    # Direct exact match on domain or website (case-insensitive, with/without www)
    patterns = [
        re.escape(domain),
        re.escape("www." + domain),
    ]
    rx = "^(?:https?://)?(?:www\\.)?" + re.escape(domain) + "/?$"

    m = await db.companies_master.find_one(
        {"$or": [
            {"domain": {"$regex": f"^{re.escape(domain)}$", "$options": "i"}},
            {"website": {"$regex": rx, "$options": "i"}},
        ]},
        {"_id": 0, "master_company_id": 1, "legal_name": 1, "domain": 1, "website": 1},
    )
    return m
