"""Valuo Enrichment Processor — Actually processes pending Valuo requests.

Gathers data from all platform sources for a company and marks the request complete.
Sources: companies_master, Economic Intelligence, BORME, CNMV, BME, Iberinform.
"""

import logging
from typing import Dict, List
from database import db
from models import now_iso
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def process_valuo_request(request_id: str) -> Dict:
    """Process a single Valuo enrichment request. Gather all available data."""
    started_at = datetime.now(timezone.utc)
    now = now_iso()

    req = await db.valuo_update_requests.find_one({"request_id": request_id})
    if not req:
        return {"error": "Request not found"}

    master_id = req.get("master_company_id")
    if not master_id:
        await _mark_failed(request_id, "No master_company_id", now)
        return {"error": "No master_company_id"}

    try:
        # Mark as processing
        await db.valuo_update_requests.update_one(
            {"request_id": request_id},
            {"$set": {"enrichment_status": "processing", "updated_at": now}}
        )

        # Gather enrichment data from all sources
        enriched_data, updated_fields = await _gather_enrichment(master_id)

        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        completed_at = finished_at.isoformat().replace("+00:00", "Z")

        # Update companies_master with enriched data (always touch last_enriched_at to track polling)
        master_update = {"updated_at": completed_at, "last_enriched_at": completed_at, "enrichment_source": "valuo_pipeline"}
        if enriched_data:
            master_update.update(enriched_data)
        await db.companies_master.update_one(
            {"master_company_id": master_id},
            {"$set": master_update}
        )

        # Mark request completed
        await db.valuo_update_requests.update_one(
            {"request_id": request_id},
            {"$set": {
                "enrichment_status": "completed",
                "status": "completed",
                "merge_status": req.get("merge_status", "discovered"),
                "updated_fields": updated_fields,
                "enriched_data": enriched_data,
                "completed_at": completed_at,
                "updated_at": completed_at,
                "error": None,
                "enrichment_meta": {
                    "sources_consulted": _get_sources_consulted(enriched_data, updated_fields),
                    "sources_count": len(_get_sources_consulted(enriched_data, updated_fields)),
                    "fields_count": len(updated_fields),
                    "duration_ms": duration_ms,
                    "processed_at": completed_at,
                },
            }}
        )

        logger.info(f"Valuo request {request_id}: completed in {duration_ms}ms, {len(updated_fields)} fields enriched")

        return {
            "status": "completed",
            "request_id": request_id,
            "master_company_id": master_id,
            "updated_fields": updated_fields,
            "fields_count": len(updated_fields),
            "duration_ms": duration_ms,
        }

    except Exception as e:
        await _mark_failed(request_id, str(e)[:200], now_iso())
        logger.error(f"Valuo request {request_id} failed: {e}")
        return {"error": str(e)}


async def process_all_pending() -> Dict:
    """Process all pending Valuo requests."""
    pending = await db.valuo_update_requests.find(
        {"enrichment_status": "pending"},
        {"_id": 0, "request_id": 1}
    ).to_list(100)

    results = {"processed": 0, "completed": 0, "failed": 0}

    for req in pending:
        result = await process_valuo_request(req["request_id"])
        results["processed"] += 1
        if result.get("status") == "completed":
            results["completed"] += 1
        else:
            results["failed"] += 1

    return results


async def _gather_enrichment(master_id: str) -> tuple:
    """Gather all available data via the unified Intelligence Engine.

    Phase 1 migration: delegates to services.intelligence_engine.enrich_company()
    with profile='valuo'. The output is flattened to the legacy contract
    (enriched_data dict + updated_fields list) so downstream code stays unchanged.
    """
    from services.intelligence_engine import enrich_company

    result = await enrich_company(master_id, profile="valuo")
    raw_fields = result.get("fields", {})

    # Flatten "<source>.<key>" → top-level key (backward-compatible names)
    # Last source wins on key collision (rare; e.g. cnae_code from bme/iberinform).
    # Legacy aliases for fields the Valuo UI already reads.
    legacy_alias = {
        "borme.events_count": "borme_events_count",
        "procurement.contracts_count": "procurement_contracts_count",
        "iberinform.revenue_latest": "revenue_latest",
        "iberinform.employees_latest": "employees_latest",
        "iberinform.cnae_code": "cnae_primary_inferred",
        "cnmv.potential_buyers_count": "potential_buyers_count",
        "economic_intel.cnae_code": "economic_profile_cnae",
    }

    enriched = {}
    fields_set = []

    # Preserve full engine output for traceability
    enriched["_engine"] = {
        "version": result.get("engine_version"),
        "profile": result.get("profile"),
        "duration_ms": result.get("duration_ms"),
        "sources_with_data": result.get("sources_with_data", []),
        "sources_consulted": result.get("sources_consulted", []),
    }

    # Group fields by source under enriched_data.sources for clean lineage
    sources_block: Dict = {}
    for dotted_key, value in raw_fields.items():
        if "." in dotted_key:
            src, sub = dotted_key.split(".", 1)
            sources_block.setdefault(src, {})[sub] = value
        else:
            enriched[dotted_key] = value
            fields_set.append(dotted_key)

        # Backward-compatible flat alias if defined
        alias = legacy_alias.get(dotted_key)
        if alias:
            enriched[alias] = value
            if alias not in fields_set:
                fields_set.append(alias)

    if sources_block:
        enriched["sources"] = sources_block
        # Add top-level convenience flags
        if "bme" in sources_block and sources_block["bme"].get("isin"):
            enriched["bme_listing"] = sources_block["bme"]
            enriched["is_public_company"] = True
            fields_set.extend(["bme_listing", "is_public_company"])
        if "cnmv" in sources_block and sources_block["cnmv"].get("entity_type"):
            enriched["cnmv_entity"] = {
                "entity_type": sources_block["cnmv"].get("entity_type"),
                "name": sources_block["cnmv"].get("entity_name"),
            }
            fields_set.append("cnmv_entity")
        if "economic_intel" in sources_block:
            enriched["economic_profile"] = sources_block["economic_intel"]
            fields_set.append("economic_profile")
        if "web" in sources_block:
            # Promote key web fields to top level for legacy Valuo UI
            w = sources_block["web"]
            for src_key, dst_key in [
                ("description", "description"),
                ("category", "category"),
                ("subcategory", "subcategory"),
                ("tags", "tags"),
                ("logo_storage_path", "logo_storage_path"),
                ("logo_url", "logo_url"),
                ("contact_email", "main_contact_email"),
                ("contact_name", "main_contact_name"),
                ("phone", "phone"),
            ]:
                if w.get(src_key):
                    enriched[dst_key] = w[src_key]
                    fields_set.append(dst_key)

    # Dedup preserving order
    seen = set()
    fields = [f for f in fields_set if not (f in seen or seen.add(f))]

    return enriched, fields


async def _mark_failed(request_id: str, error: str, now: str):
    await db.valuo_update_requests.update_one(
        {"request_id": request_id},
        {"$set": {
            "enrichment_status": "failed",
            "status": "failed",
            "error": error,
            "updated_at": now,
        }}
    )


def _get_sources_consulted(enriched_data: Dict, updated_fields: List) -> List[str]:
    """Return the sources consulted by the Intelligence Engine for this run.

    Uses the live `_engine.sources_consulted` block when available, falling back
    to the full set of profile sources to guarantee traceability.
    """
    engine = (enriched_data or {}).get("_engine") or {}
    consulted = engine.get("sources_consulted") or []
    if consulted:
        names = [s.get("source") for s in consulted if s.get("source")]
        # Stable order, dedupe, prepend canonical companies_master
        seen = set()
        out = ["companies_master"]
        for n in names:
            if n not in seen:
                out.append(n)
                seen.add(n)
        return out

    # Fallback (engine not available) — list all valuo profile sources
    return [
        "companies_master", "identity", "web", "iberinform", "bme",
        "economic_intel", "borme", "procurement", "cnmv",
    ]
