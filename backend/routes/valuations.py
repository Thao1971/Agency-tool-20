"""Category Valuations — Persistent, auto-rebuilding endpoints."""

from fastapi import APIRouter, Depends, Query
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.category_valuations import (
    rebuild_valuations, get_cached_valuations, get_valuation_summary,
)
import time

router = APIRouter(prefix="/api/v1/valuations", tags=["valuations"])


def _meta(t0):
    return {"contract_version": "1.0", "generated_at": now_iso(),
            "response_time_ms": round((time.time() - t0) * 1000, 1)}


@router.get("/by-category")
async def valuations_by_category(user=Depends(get_current_user)):
    """Valuation multiples by category. Reads from persistent cache."""
    t0 = time.time()
    result = await get_cached_valuations()
    return {**_meta(t0), **result}


@router.get("/summary")
async def valuation_summary(user=Depends(get_current_user)):
    """Quick summary of valuation data availability."""
    t0 = time.time()
    summary = await get_valuation_summary()
    return {**_meta(t0), **summary}


@router.post("/rebuild")
async def rebuild(
    year: int = Query(None),
    buyer_type: str = Query(None),
    country: str = Query(None),
    only_observed: bool = Query(False),
    user=Depends(get_current_user),
):
    """Rebuild all category valuations from M&A transactions. Persists results."""
    t0 = time.time()
    result = await rebuild_valuations(year, buyer_type, country, only_observed, trigger="manual")
    return {**_meta(t0), **result}


@router.get("/rebuild-logs")
async def rebuild_logs(limit: int = Query(10, ge=1, le=50), user=Depends(get_current_user)):
    """Rebuild history logs."""
    t0 = time.time()
    logs = await db.valuation_rebuild_logs.find({}, {"_id": 0}).sort("rebuilt_at", -1).limit(limit).to_list(limit)
    return {**_meta(t0), "logs": logs}


@router.get("/category/{category_name}")
async def category_detail(category_name: str, user=Depends(get_current_user)):
    """Detailed valuation for a specific category from cache."""
    t0 = time.time()
    category = await db.category_valuations.find_one(
        {"category": {"$regex": category_name, "$options": "i"}}, {"_id": 0}
    )
    if not category:
        from fastapi import HTTPException
        raise HTTPException(404, f"Category '{category_name}' not found")
    return {**_meta(t0), "category": category}
