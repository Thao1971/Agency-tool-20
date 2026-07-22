"""Canonical Enriched Company API — explicit, stable contract for Valuo / arroba.

GET /api/v1/company/{master_company_id}/enriched
GET /api/v1/company/by-valuo-id/{valuo_company_id}/enriched

Returns a denormalized + structured view. Consumer products can read either:
  - top-level flat fields (description, tags, logo_url, …) for direct UI binding
  - `sources.{web,bme,borme,…}` for full lineage / advanced consumers
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict

from database import db

router = APIRouter(prefix="/api/v1/company", tags=["enriched_company"])


CANONICAL_SOURCES = ["web", "bme", "borme", "cnmv", "iberinform",
                     "procurement", "datacomex", "economic_intel", "oepm"]


def _resolve_logo_url(web: Dict, base_url: str) -> str | None:
    """Storage path → public binary URL. Falls back to raw logo_url if present."""
    storage_path = web.get("logo_storage_path")
    if storage_path:
        return f"{base_url}/api/v1/screenshots/{storage_path}"
    return web.get("logo_url") or None


def _build_enriched_view(master: Dict, request: Request) -> Dict:
    """Build the canonical Valuo/arroba response.

    Two layers:
      • Top-level flat fields (description, tags, logo_url, …) — for UI binding.
      • `sources.{web,bme,…}` — full lineage for advanced consumers.
    """
    sources = master.get("sources") or {}
    web = sources.get("web") or {}
    bme = sources.get("bme") or {}
    borme = sources.get("borme") or {}
    iberinform = sources.get("iberinform") or {}
    cnmv = sources.get("cnmv") or {}
    economic = sources.get("economic_intel") or {}

    base = str(request.base_url).rstrip("/")
    logo_url = _resolve_logo_url(web, base)

    # Flat top-level (denormalized) — what Valuo's UI binds to
    flat = {
        "master_company_id": master.get("master_company_id"),
        "legal_name": master.get("legal_name"),
        "cif": master.get("cif"),
        "domain": master.get("domain"),
        "website": master.get("website"),
        "commercial_names": master.get("commercial_names") or [],
        "category_name": master.get("category_name"),

        # Web layer (description / classification)
        "description": web.get("description"),
        "category": web.get("category"),
        "subcategory": web.get("subcategory"),
        "tags": web.get("tags") or [],
        "main_clients": web.get("main_clients") or [],
        "has_awards": web.get("has_awards"),
        "awards": web.get("awards_evidence") or [],

        # Contact
        "email": web.get("contact_email"),
        "phone": web.get("phone"),
        "address": web.get("address") or {},

        # Logo (resolved)
        "logo_url": logo_url,
        "logo_storage_path": web.get("logo_storage_path"),

        # Public market presence
        "is_public_company": bool(bme),
        "isin": bme.get("isin"),
        "market_cap": bme.get("market_cap"),
        "market_segment": bme.get("market_segment"),
        "ticker": bme.get("ticker"),

        # Financials (Iberinform)
        "revenue_latest": iberinform.get("revenue_latest"),
        "employees_latest": iberinform.get("employees_latest"),
        "ebitda_latest": iberinform.get("ebitda_latest"),
        "year_latest": iberinform.get("year_latest"),
        "cnae_code": iberinform.get("cnae_code") or master.get("cnae_primary"),

        # Corporate activity
        "borme_events_count": borme.get("events_count"),

        # Investor / fund presence
        "cnmv_entity_type": cnmv.get("entity_type"),
        "potential_buyers_count": cnmv.get("potential_buyers_count"),

        # Sector benchmark
        "sector_trend": economic.get("sector_trend"),
        "sector_revenue": economic.get("revenue_sector"),
    }

    # Per-source presence map + nested lineage
    sources_present = {name: bool(sources.get(name)) for name in CANONICAL_SOURCES}

    # `updated_fields` = top-level keys with non-empty values (caller-friendly)
    updated_fields = [
        k for k, v in flat.items()
        if k not in ("master_company_id", "legal_name", "cif", "domain")
        and v not in (None, "", [], {}, False)
    ]

    return {
        **flat,
        "sources": sources,
        "sources_present": sources_present,
        "sources_count": sum(1 for v in sources_present.values() if v),
        "updated_fields": updated_fields,
        "linked_valuo_ids": master.get("linked_valuo_ids") or [],
        "last_enriched_at": master.get("last_enriched_at"),
        "enrichment_source": master.get("enrichment_source"),
        "updated_at": master.get("updated_at"),
    }


@router.get("/{master_company_id}/enriched")
async def get_enriched_company(master_company_id: str, request: Request):
    """Canonical enriched-company endpoint. PUBLIC — Valuo/arroba consume this
    immediately after a Valuo request reaches status `completed`.
    """
    master = await db.companies_master.find_one(
        {"master_company_id": master_company_id}, {"_id": 0}
    )
    if not master:
        raise HTTPException(404, f"Master company {master_company_id} not found")
    return _build_enriched_view(master, request)


@router.get("/by-valuo-id/{valuo_company_id}/enriched")
async def get_enriched_company_by_valuo_id(valuo_company_id: str, request: Request):
    """Resolve Valuo's external ID → return canonical enriched payload."""
    master = await db.companies_master.find_one(
        {"linked_valuo_ids": valuo_company_id}, {"_id": 0}
    )
    if not master:
        raise HTTPException(404, f"No master linked to valuo_company_id={valuo_company_id}")
    return _build_enriched_view(master, request)
