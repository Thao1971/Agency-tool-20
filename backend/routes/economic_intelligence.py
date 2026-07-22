"""Economic Intelligence Layer — Unified economic endpoints for Arroba/Valuo.

Single entry point: GET /economic-intelligence/cnae/{code}
Returns combined metrics from all sources without connecting to each one directly.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.economic_intelligence import (
    rebuild_economic_metrics, rebuild_economic_signals, get_cnae_economic_profile,
)
import time

router = APIRouter(prefix="/api/v1/economic-intelligence", tags=["economic_intelligence"])

CONTRACT_VERSION = "1.0"


def _meta(t0):
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now_iso(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
        "layer": "Economic Intelligence Layer",
    }


# ══════════════════════════════════════════
# PUBLIC — For Arroba/Valuo consumption
# ══════════════════════════════════════════

@router.get("/cnae/{cnae_code}")
async def cnae_profile(cnae_code: str):
    """Complete economic profile for a CNAE code.
    
    Returns: revenue, EBITDA, employment, exports, imports, procurement,
    growth trends, signals — all from a single endpoint.
    """
    t0 = time.time()
    profile = await get_cnae_economic_profile(cnae_code)

    if not profile.get("sources_available"):
        raise HTTPException(404, f"No economic data for CNAE {cnae_code}. Run /rebuild first.")

    return {**_meta(t0), **profile}


@router.get("/overview")
async def overview(limit: int = Query(20, ge=1, le=88)):
    """Top CNAE divisions by data richness (number of metrics available)."""
    t0 = time.time()

    pipeline = [
        {"$match": {"cnae_code": {"$ne": "national"}}},
        {"$group": {
            "_id": "$cnae_code",
            "metrics_count": {"$sum": 1},
            "sources": {"$addToSet": "$source"},
        }},
        {"$sort": {"metrics_count": -1}},
        {"$limit": limit},
    ]
    raw = await db.economic_metrics.aggregate(pipeline).to_list(limit)

    from services.cnae_catalog import CNAE_DIVISIONS, get_section_for_division
    items = []
    for r in raw:
        cnae = r["_id"]
        items.append({
            "cnae_code": cnae,
            "cnae_label": CNAE_DIVISIONS.get(cnae, {}).get("label", ""),
            "cnae_section": get_section_for_division(cnae),
            "metrics_count": r["metrics_count"],
            "sources": r["sources"],
            "sources_count": len(r["sources"]),
        })

    return {
        **_meta(t0),
        "cnae_divisions": items,
        "count": len(items),
    }


@router.get("/signals")
async def all_signals(limit: int = Query(50, ge=1, le=200)):
    """All economic signals across all CNAE codes."""
    t0 = time.time()
    signals = await db.economic_signals.find(
        {}, {"_id": 0}
    ).sort("confidence", -1).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "signals": signals,
        "count": len(signals),
    }


@router.get("/stats")
async def stats():
    """Stats about the Economic Intelligence Layer."""
    t0 = time.time()

    total_metrics = await db.economic_metrics.count_documents({})
    total_signals = await db.economic_signals.count_documents({})
    cnae_codes = len(await db.economic_metrics.distinct("cnae_code", {"cnae_code": {"$ne": "national"}}))

    source_pipeline = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    ]
    by_source = await db.economic_metrics.aggregate(source_pipeline).to_list(20)

    return {
        **_meta(t0),
        "total_metrics": total_metrics,
        "total_signals": total_signals,
        "cnae_codes_covered": cnae_codes,
        "by_source": {r["_id"]: r["count"] for r in by_source},
    }


# ══════════════════════════════════════════
# ADMIN — Rebuild
# ══════════════════════════════════════════

@router.post("/rebuild")
async def rebuild(user=Depends(get_current_user)):
    """Rebuild all economic metrics + signals from sources."""
    t0 = time.time()

    metrics_result = await rebuild_economic_metrics()
    signals_result = await rebuild_economic_signals()

    return {
        "status": "completed",
        "metrics": metrics_result,
        "signals": signals_result,
        "processing_time_ms": round((time.time() - t0) * 1000, 1),
    }
