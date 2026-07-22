"""Intelligence Engine API — Unified enrichment endpoint for all products.

POST /api/v1/intelligence/enrich      — run enrichment for a master_company_id
GET  /api/v1/intelligence/profiles    — list available profiles
GET  /api/v1/intelligence/profile/{name}  — describe one profile
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional

from services.intelligence_engine import enrich_company, list_profiles, get_profile_definition

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence_engine"])


class EnrichRequest(BaseModel):
    master_company_id: str = Field(..., description="companies_master.master_company_id")
    profile: str = Field("basic", description="basic | valuo | arroba")
    force_refresh: bool = Field(False, description="(Phase 2) re-run cached web scrapes")


@router.post("/enrich")
async def enrich(req: EnrichRequest):
    """Run unified enrichment for a company. Profile decides which sources run."""
    try:
        get_profile_definition(req.profile)
    except ValueError as e:
        raise HTTPException(400, str(e))

    result = await enrich_company(
        master_company_id=req.master_company_id,
        profile=req.profile,
        force_refresh=req.force_refresh,
    )
    if result.get("error") == "master_not_found":
        raise HTTPException(404, f"master_company_id {req.master_company_id} not found")
    return result


@router.get("/profiles")
async def profiles():
    """List all available enrichment profiles."""
    return {"profiles": list_profiles()}


@router.get("/profile/{name}")
async def profile_detail(name: str):
    """Describe a single profile (which sources it runs)."""
    try:
        return get_profile_definition(name)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/migrate-agency-results")
async def migrate_agency_results(dry_run: bool = False):
    """One-shot migration: link existing agency_results (Agency Tool legacy)
    to their master_company by domain match. Idempotent: re-running is safe.

    Use ?dry_run=true to preview without writing.
    """
    from services.intelligence_engine.linker import migrate_all
    return await migrate_all(dry_run=dry_run)


@router.get("/scrape-queue")
async def scrape_queue_status():
    """Status of the web scrape queue (jobs created by the engine)."""
    from database import db
    base = {"consumer_id": "intelligence_engine"}
    counts = {}
    for s in ("pending", "claimed", "processing", "failed"):
        counts[s] = await db.analysis_jobs.count_documents({**base, "status": s})
    recent = await db.analysis_jobs.find(
        base, {"_id": 0, "id": 1, "url": 1, "status": 1, "entity_id": 1,
               "metadata": 1, "created_at": 1, "claimed_at": 1, "heartbeat_at": 1},
    ).sort("created_at", -1).limit(20).to_list(20)
    return {"counts": counts, "recent_jobs": recent}


@router.post("/signals/rebuild-public-sources")
async def rebuild_public_signals():
    """Recompute signals derived from public-data sources (ayudas/empleo/territoriales)."""
    from services.intelligence_engine.public_signals import rebuild_public_signals as _rebuild
    return await _rebuild()


@router.get("/scheduler/audit")
async def scheduler_audit(limit: int = 20):
    """Last N public-sources ingestion runs from er_audit_logs."""
    from database import db
    rows = await db.er_audit_logs.find(
        {"action": {"$regex": "^public_source_ingest_"}},
        {"_id": 0},
    ).sort("started_at", -1).limit(limit).to_list(limit)
    return {"runs": rows, "count": len(rows)}


@router.post("/sources/ingest/{source}")
async def ingest_source(source: str):
    """Run real ingestion for a public-data source. NO synthetic data.

    Fully dynamic: resolves the runner from each source module's own
    `META['ingest_runner']`. Accepts the engine source name (e.g. `grants`,
    `employment`, `territorial`), legacy aliases (`ayudas`, `empleo`,
    `territoriales`), or `all`. Every run is audited in `er_audit_logs` so the
    Console reflects manual triggers immediately.
    """
    from services.intelligence_engine import engine_info, ingestion as ing_mod
    from services.intelligence_engine.scheduler import _run_and_audit

    # Legacy aliases → engine source names (backward compat for old callers).
    LEGACY_ALIASES = {"ayudas": "grants", "empleo": "employment", "territoriales": "territorial"}

    async def _run_one(name: str):
        meta = engine_info.get_source_meta(name)
        if not meta["supports_manual_ingestion"] or not meta["ingest_runner"]:
            return None
        runner = getattr(ing_mod, meta["ingest_runner"], None)
        if not runner:
            return {"status": "error", "reason": f"runner '{meta['ingest_runner']}' not found"}
        # Audit under the collection name so action == META['audit_action'].
        log = await _run_and_audit(meta["collection"], runner, performed_by="manual_trigger")
        return log.get("result", {"status": log.get("status")})

    if source == "all":
        results = {}
        for name in engine_info.get_all_sources():
            res = await _run_one(name)
            if res is not None:
                results[name] = res
        return results

    name = LEGACY_ALIASES.get(source, source)
    if name not in engine_info.get_all_sources():
        raise HTTPException(400, f"Unknown source '{source}'.")
    meta = engine_info.get_source_meta(name)
    if not meta["supports_manual_ingestion"] or not meta["ingest_runner"]:
        raise HTTPException(400, f"Source '{name}' does not support manual ingestion.")
    return await _run_one(name)


@router.get("/sources/coverage")
async def sources_coverage():
    """Report counts per public-data collection so the team can see ingestion status."""
    from database import db
    cols = ["ayudas_subvenciones_publicas", "estadisticas_empleo", "estadisticas_territoriales"]
    return {c: {"count": await db[c].count_documents({})} for c in cols}


@router.get("/sources/sidebar")
async def sources_sidebar():
    """Dynamic sidebar catalog. Derived 100% from the Intelligence Engine.

    Iterates `engine_info.get_all_sources()` (engine order = sidebar order),
    keeps sources whose META declares `show_in_sidebar=True`, and groups them by
    `META['sidebar_group']`. ZERO hardcoded arrays — adding a source module with
    `show_in_sidebar=True` makes it appear here (and in the UI) automatically.
    """
    from services.intelligence_engine import engine_info
    groups: dict = {}
    for name in engine_info.get_all_sources():
        meta = engine_info.get_source_meta(name)
        if not meta["show_in_sidebar"]:
            continue
        group = meta["sidebar_group"] or "data"
        groups.setdefault(group, []).append({
            "source": name,
            "label": meta["display_name"],
            "route": f"/data/source/{name}",
            "dot": meta["sidebar_dot"] or "bg-zinc-500",
            "phase": meta["phase"],
            "frequency": meta["frequency"],
        })
    return {"groups": groups, "total": sum(len(v) for v in groups.values())}


@router.get("/sources/{source}/sample")
async def source_sample(source: str, page: int = 1, page_size: int = 50):
    """Paginated real-document sample for any engine source. Fully dynamic.

    The collection is resolved from the source module's own `META['collection']`
    and gated by `META['supports_sample']`. NO switches, NO manual maps, NO
    synthetic data — a new source with a collection becomes explorable here
    automatically.
    """
    from services.intelligence_engine import engine_info
    from database import db

    if source not in engine_info.get_all_sources():
        raise HTTPException(404, f"Unknown source '{source}'.")
    meta = engine_info.get_source_meta(source)
    coll = meta["collection"]
    if not coll or not meta["supports_sample"]:
        raise HTTPException(400, f"Source '{source}' does not support data sampling.")

    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    skip = (page - 1) * page_size

    total = await db[coll].count_documents({})
    items = await db[coll].find({}, {"_id": 0}).skip(skip).limit(page_size).to_list(page_size)

    return {
        "source": source,
        "name": meta["display_name"],
        "collection": coll,
        "total_records": total,
        "current_page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
        "items": items,
    }


@router.get("/sources/{source}/query")
async def source_query(
    source: str,
    page: int = 1,
    page_size: int = 50,
    sort_by: str | None = None,
    sort_order: str = "asc",
    field: str | None = None,
    value: str | None = None,
):
    """Dynamic query/filter over any queryable engine source.

    Collection resolved from `META['collection']`, gated by `META['queryable']`.
    NO hardcoded fields — available fields are derived from real documents and
    returned in `fields`. Numeric values match by equality; strings match by
    case-insensitive substring (regex). NO synthetic data.
    """
    import re
    from services.intelligence_engine import engine_info
    from database import db

    if source not in engine_info.get_all_sources():
        raise HTTPException(404, f"Unknown source '{source}'.")
    meta = engine_info.get_source_meta(source)
    coll = meta["collection"]
    if not coll or not meta["queryable"]:
        raise HTTPException(400, f"Source '{source}' is not queryable.")

    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    skip = (page - 1) * page_size

    q: dict = {}
    if field and value not in (None, ""):
        num = None
        try:
            num = int(value)
        except (TypeError, ValueError):
            try:
                num = float(value)
            except (TypeError, ValueError):
                num = None
        q = {field: num} if num is not None else {field: {"$regex": re.escape(value), "$options": "i"}}

    cursor = db[coll].find(q, {"_id": 0})
    if sort_by:
        direction = -1 if str(sort_order).lower() in ("desc", "-1") else 1
        cursor = cursor.sort([(sort_by, direction)])

    total = await db[coll].count_documents(q)
    items = await cursor.skip(skip).limit(page_size).to_list(page_size)

    # Available fields derived dynamically from a sample (union of keys).
    sample_docs = await db[coll].find({}, {"_id": 0}).limit(25).to_list(25)
    fields: list = []
    for d in sample_docs:
        for k in d.keys():
            if k not in fields:
                fields.append(k)

    return {
        "source": source,
        "name": meta["display_name"],
        "collection": coll,
        "fields": fields,
        "filter": ({"field": field, "value": value} if field and value not in (None, "") else None),
        "sort": ({"by": sort_by, "order": sort_order} if sort_by else None),
        "total_records": total,
        "current_page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
        "items": items,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Canonical enriched company endpoints (consumed by Valuo, arroba, …)
# Public: no JWT required — these are product-facing read endpoints.
# ─────────────────────────────────────────────────────────────────────────────

CANONICAL_SOURCES = ["web", "bme", "borme", "cnmv", "iberinform",
                     "procurement", "datacomex", "economic_intel", "oepm"]


def _build_company_view(master: dict, request) -> dict:
    """Return the canonical enriched-company payload consumed by products."""
    sources_block = master.get("sources") or {}

    # Logo URL: resolve storage path → public binary endpoint
    logo_url = None
    web = sources_block.get("web") or {}
    storage_path = web.get("logo_storage_path")
    if storage_path:
        base = str(request.base_url).rstrip("/")
        logo_url = f"{base}/api/v1/screenshots/{storage_path}"
    elif web.get("logo_url"):
        logo_url = web["logo_url"]

    # Per-source presence map (which sources contributed data to this master)
    sources_present = {name: bool(sources_block.get(name)) for name in CANONICAL_SOURCES}

    return {
        "master_company_id": master.get("master_company_id"),
        "identity": {
            "legal_name": master.get("legal_name"),
            "cif": master.get("cif"),
            "domain": master.get("domain"),
            "website": master.get("website"),
            "commercial_names": master.get("commercial_names") or [],
            "aliases": master.get("aliases") or [],
            "category_name": master.get("category_name"),
            "cnae_primary": master.get("cnae_primary"),
            "country": master.get("country"),
            "confidence_score": master.get("confidence_score"),
            "merge_status": master.get("merge_status"),
        },
        "sources": sources_block,
        "sources_present": sources_present,
        "sources_count": sum(1 for v in sources_present.values() if v),
        "logo_url": logo_url,
        "linked_valuo_ids": master.get("linked_valuo_ids") or [],
        "last_enriched_at": master.get("last_enriched_at"),
        "enrichment_source": master.get("enrichment_source"),
        "updated_at": master.get("updated_at"),
    }


@router.get("/company/{master_company_id}")
async def get_enriched_company(master_company_id: str, request: Request):
    """Canonical enriched-company endpoint. Public — consumed by Valuo, arroba.

    Returns identity + every `master.sources.*` block + resolved logo URL.
    This is the single source of truth for products that need to read
    enriched data after an enrichment completes.
    """
    from database import db
    master = await db.companies_master.find_one(
        {"master_company_id": master_company_id}, {"_id": 0}
    )
    if not master:
        raise HTTPException(404, f"Master company {master_company_id} not found")
    return _build_company_view(master, request)


@router.get("/company/by-valuo-id/{valuo_company_id}")
async def get_enriched_company_by_valuo_id(valuo_company_id: str, request: Request):
    """Lookup canonical enriched company by Valuo's external ID.

    Resolves through linked_valuo_ids → returns the same payload as
    /company/{master_company_id}.
    """
    from database import db
    master = await db.companies_master.find_one(
        {"linked_valuo_ids": valuo_company_id}, {"_id": 0}
    )
    if not master:
        raise HTTPException(404, f"No master linked to valuo_company_id={valuo_company_id}")
    return _build_company_view(master, request)
