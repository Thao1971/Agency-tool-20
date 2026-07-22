"""CNMV Intelligence — Investor intelligence endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.cnmv_connector import (
    sync_cnmv_entities, generate_cnmv_signals, get_cnmv_stats,
    match_cnmv_to_companies, get_managers_with_funds, get_entity_detail,
)
from services.cnmv_catalog import get_full_catalog, get_entity_info
from services.cnmv_investor_intelligence import (
    build_investor_sector_map, get_buyers_for_cnae, get_buyers_summary_by_cnae,
    get_confidence_stats, _build_data_lineage,
)
import time

router = APIRouter(prefix="/api/v1/cnmv", tags=["cnmv"])


def _meta(t0):
    return {
        "contract_version": "1.0",
        "generated_at": now_iso(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
        "source": "CNMV — Comision Nacional del Mercado de Valores",
    }


@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    """CNMV Intelligence dashboard with confidence stats."""
    t0 = time.time()
    stats = await get_cnmv_stats()
    signals = await db.cnmv_signals.find({}, {"_id": 0}).to_list(20)
    matched = await db.cnmv_entities.count_documents({"matched_company_id": {"$exists": True, "$ne": None}})
    confidence = await get_confidence_stats()

    return {
        **_meta(t0),
        "kpis": {**stats, "matched_to_companies": matched},
        "confidence": confidence,
        "signals": signals,
    }


@router.get("/catalog")
async def catalog():
    """Entity type catalog with descriptions, M&A relevance, and use cases."""
    t0 = time.time()
    return {**_meta(t0), "catalog": get_full_catalog()}


@router.get("/entities")
async def list_entities(
    entity_type: str = Query(None),
    is_manager: bool = Query(None),
    limit: int = Query(50, ge=1, le=500),
    page: int = Query(1, ge=1),
    search: str = Query(None),
    user=Depends(get_current_user),
):
    """List CNMV registered entities with filters."""
    t0 = time.time()
    query = {}
    if entity_type:
        query["entity_type"] = entity_type
    if is_manager is not None:
        query["is_manager"] = is_manager
    if search:
        query["name"] = {"$regex": search, "$options": "i"}

    skip = (page - 1) * limit
    entities = await db.cnmv_entities.find(query, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    total = await db.cnmv_entities.count_documents(query)

    # Enrich with catalog info
    for e in entities:
        info = get_entity_info(e.get("entity_type", ""))
        if info:
            e["mna_relevance"] = info.get("mna_relevance", 0)
            e["mna_label"] = info.get("mna_label", "")
            e["short_description"] = info.get("short_description", "")

    return {**_meta(t0), "entities": entities, "total": total, "page": page, "limit": limit}


@router.get("/managers")
async def list_managers(user=Depends(get_current_user)):
    """List all fund managers (SGEIC, SGIIC, ESI, EAF)."""
    t0 = time.time()
    managers = await get_managers_with_funds()
    return {**_meta(t0), "managers": managers, "count": len(managers)}


@router.get("/entity/{entity_id}")
async def entity_detail(entity_id: str, user=Depends(get_current_user)):
    """Full detail for a CNMV entity with data lineage."""
    t0 = time.time()
    entity = await get_entity_detail(entity_id)
    if not entity:
        raise HTTPException(404, f"Entity {entity_id} not found")

    lineage = _build_data_lineage(entity)
    return {**_meta(t0), "entity": entity, "data_lineage": lineage}


@router.get("/company/{company_id}")
async def company_cnmv(company_id: str, user=Depends(get_current_user)):
    """Find CNMV entities linked to a company_id from companies_master."""
    t0 = time.time()
    entities = await db.cnmv_entities.find(
        {"matched_company_id": company_id}, {"_id": 0}
    ).to_list(20)

    for e in entities:
        info = get_entity_info(e.get("entity_type", ""))
        if info:
            e["catalog"] = info

    return {**_meta(t0), "entities": entities, "count": len(entities)}


@router.get("/signals")
async def list_signals(user=Depends(get_current_user)):
    """CNMV investor signals."""
    t0 = time.time()
    signals = await db.cnmv_signals.find({}, {"_id": 0}).to_list(50)
    return {**_meta(t0), "signals": signals, "count": len(signals)}


@router.get("/entity-types")
async def entity_types():
    """Available CNMV entity types with full descriptions."""
    return {"entity_types": get_full_catalog()}


@router.post("/sync")
async def sync(
    types: str = Query(None),
    max_pages: int = Query(100, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Sync entities from CNMV official registers."""
    type_list = None
    if types:
        type_list = [t.strip() for t in types.split(",")]
    result = await sync_cnmv_entities(entity_types=type_list, max_pages_per_type=max_pages)
    if result.get("status") == "error":
        # Previously this always returned 200 OK even on a fatal scraping failure
        # (e.g. Chromium missing), so the frontend's try/catch never fired and
        # showed a false "success" toast. Surface it as a real HTTP error.
        raise HTTPException(502, result.get("message", "Error sincronizando CNMV"))
    return result


@router.post("/match-companies")
async def match_companies(user=Depends(get_current_user)):
    """Match CNMV entities against companies_master by NIF."""
    return await match_cnmv_to_companies()


@router.post("/rebuild-signals")
async def rebuild_signals(user=Depends(get_current_user)):
    """Rebuild investor intelligence signals and metrics."""
    return await generate_cnmv_signals()


@router.post("/map-sectors")
async def map_sectors(user=Depends(get_current_user)):
    """Map CNMV entities to CNAE sectors based on name analysis."""
    return await build_investor_sector_map()


@router.get("/buyers/{cnae_code}")
async def buyers_for_cnae(cnae_code: str):
    """Find financial buyers for a CNAE sector. PUBLIC endpoint for arroba.com.
    
    Returns specialist funds (sector-focused) + generalist funds (multi-sector).
    """
    t0 = time.time()
    result = await get_buyers_for_cnae(cnae_code)

    from services.cnae_catalog import CNAE_DIVISIONS
    cnae_label = CNAE_DIVISIONS.get(cnae_code, {}).get("label", "")

    return {
        **_meta(t0),
        "cnae_code": cnae_code,
        "cnae_label": cnae_label,
        **result,
    }


@router.get("/buyers-summary")
async def buyers_summary():
    """Buyer count per CNAE sector. PUBLIC endpoint."""
    t0 = time.time()
    summary = await get_buyers_summary_by_cnae()
    return {**_meta(t0), "sectors": summary, "count": len(summary)}


@router.get("/confidence")
async def confidence(user=Depends(get_current_user)):
    """Confidence and data quality stats for CNMV module."""
    t0 = time.time()
    stats = await get_confidence_stats()
    return {**_meta(t0), **stats}
