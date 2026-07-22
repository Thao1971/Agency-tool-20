"""Geo Intelligence — Public endpoints for Arroba/Valuo consumption.

Territorial hierarchy: CCAA → Province (→ Municipality future).
Multi-score: size_score, growth_score, activity_score → dynamism_score.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.geo_intelligence import compute_geo_intelligence
from services.geo_catalog import build_geo_catalog, CCAA, PROVINCES
import time

router = APIRouter(prefix="/api/v1/public/geo-intelligence", tags=["geo_intelligence"])

CONTRACT_VERSION = "1.0"


def _meta(t0):
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now_iso(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
        "source_attribution": "INE Demografia Empresarial, BORME, Contratacion Publica, Iberinform",
    }


def _geo_card(g):
    """Compact card for lists."""
    return {
        "geo_id": g.get("geo_id"),
        "geo_level": g.get("geo_level"),
        "geo_name": g.get("geo_name"),
        "active_companies": g.get("active_companies", 0),
        "new_companies": g.get("new_companies", 0),
        "closed_companies": g.get("closed_companies", 0),
        "net_company_creation": g.get("net_company_creation", 0),
        "public_contracts_count": g.get("public_contracts_count", 0),
        "borme_activity_count": g.get("borme_activity_count", 0),
        "size_score": g.get("size_score", 0),
        "growth_score": g.get("growth_score", 0),
        "activity_score": g.get("activity_score", 0),
        "dynamism_score": g.get("dynamism_score", 0),
        "trend_direction": g.get("trend_direction"),
        "signal": g.get("signal"),
        "primary_driver": g.get("primary_driver"),
        "partial_data": g.get("partial_data", True),
    }


# ══════════════════════════════════════════
# CATALOG
# ══════════════════════════════════════════

@router.get("/catalog")
async def geo_catalog():
    """Full geographic catalog: CCAA → Provinces."""
    t0 = time.time()
    catalog = build_geo_catalog()
    return {
        **_meta(t0),
        "catalog": catalog,
        "total_ccaa": len(catalog),
        "total_provinces": sum(len(c["provinces"]) for c in catalog),
    }


# ══════════════════════════════════════════
# OVERVIEW & RANKINGS
# ══════════════════════════════════════════

@router.get("/overview")
async def overview(
    level: str = Query("ccaa", regex="^(ccaa|province)$"),
):
    """All territories at specified level, ranked by dynamism_score."""
    t0 = time.time()
    territories = await db.geo_intelligence.find(
        {"geo_level": level}, {"_id": 0}
    ).sort([("dynamism_score", -1), ("geo_id", 1)]).to_list(200)

    return {
        **_meta(t0),
        "level": level,
        "territories": [_geo_card(t) for t in territories],
        "count": len(territories),
    }


@router.get("/top-dynamic")
async def top_dynamic(
    limit: int = Query(10, ge=1, le=52),
    level: str = Query("ccaa", regex="^(ccaa|province)$"),
):
    """Top territories by dynamism_score."""
    t0 = time.time()
    territories = await db.geo_intelligence.find(
        {"geo_level": level, "dynamism_score": {"$gt": 0}}, {"_id": 0}
    ).sort([("dynamism_score", -1), ("geo_id", 1)]).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "ranking_by": "dynamism_score",
        "level": level,
        "territories": [_geo_card(t) for t in territories],
    }


@router.get("/largest")
async def largest(
    limit: int = Query(10, ge=1, le=52),
    level: str = Query("ccaa", regex="^(ccaa|province)$"),
):
    """Top territories by size_score (active companies)."""
    t0 = time.time()
    territories = await db.geo_intelligence.find(
        {"geo_level": level}, {"_id": 0}
    ).sort([("size_score", -1), ("geo_id", 1)]).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "ranking_by": "size_score",
        "level": level,
        "territories": [_geo_card(t) for t in territories],
    }


@router.get("/fastest-growing")
async def fastest_growing(
    limit: int = Query(10, ge=1, le=52),
    level: str = Query("ccaa", regex="^(ccaa|province)$"),
):
    """Top territories by growth_score (company creation dynamics)."""
    t0 = time.time()
    territories = await db.geo_intelligence.find(
        {"geo_level": level}, {"_id": 0}
    ).sort([("growth_score", -1), ("geo_id", 1)]).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "ranking_by": "growth_score",
        "level": level,
        "territories": [_geo_card(t) for t in territories],
    }


@router.get("/most-active")
async def most_active(
    limit: int = Query(10, ge=1, le=52),
    level: str = Query("ccaa", regex="^(ccaa|province)$"),
):
    """Top territories by activity_score (BORME + procurement + Iberinform)."""
    t0 = time.time()
    territories = await db.geo_intelligence.find(
        {"geo_level": level}, {"_id": 0}
    ).sort([("activity_score", -1), ("geo_id", 1)]).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "ranking_by": "activity_score",
        "level": level,
        "territories": [_geo_card(t) for t in territories],
    }


# ══════════════════════════════════════════
# DRILL-DOWN
# ══════════════════════════════════════════

@router.get("/ccaa/{code}")
async def ccaa_detail(code: str):
    """Drill-down: CCAA → its Provinces with scores."""
    t0 = time.time()

    ccaa = await db.geo_intelligence.find_one(
        {"geo_id": code, "geo_level": "ccaa"}, {"_id": 0}
    )
    if not ccaa:
        raise HTTPException(404, f"CCAA {code} not found. Run /sync first.")

    provinces = await db.geo_intelligence.find(
        {"parent_ccaa": code, "geo_level": "province"}, {"_id": 0}
    ).sort([("dynamism_score", -1), ("geo_id", 1)]).to_list(52)

    return {
        **_meta(t0),
        "ccaa": ccaa,
        "provinces": [_geo_card(p) for p in provinces],
        "provinces_count": len(provinces),
    }


@router.get("/province/{code}")
async def province_detail(code: str):
    """Full detail for a specific province."""
    t0 = time.time()

    province = await db.geo_intelligence.find_one(
        {"geo_id": code, "geo_level": "province"}, {"_id": 0}
    )
    if not province:
        raise HTTPException(404, f"Province {code} not found")

    return {
        **_meta(t0),
        "province": province,
    }


# ══════════════════════════════════════════
# ADMIN: SYNC
# ══════════════════════════════════════════

@router.post("/sync")
async def sync(user=Depends(get_current_user)):
    """Recompute all geo intelligence scores."""
    result = await compute_geo_intelligence()
    from services.intelligence_scheduler import log_manual_sync
    await log_manual_sync("geo_intelligence", result.get("total", 0))
    return result
