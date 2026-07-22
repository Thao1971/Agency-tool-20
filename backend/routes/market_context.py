"""Market Context API v2 — Stable contract for Valuo consumption.

Contract: GET /api/v1/market-context/{cnae}
Always returns the same field set. Never dynamic.
"""

from fastapi import APIRouter
from database import db
from models import now_iso
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/market-context", tags=["market_context"])

CONTRACT_VERSION = "2.0"


@router.get("/{cnae}")
async def get_market_context(cnae: str):
    """Public: Market context for a CNAE. Stable contract — always same fields."""
    obs = await db.ine_observations.find(
        {"cnae_code": {"$regex": f"^{cnae}"}}, {"_id": 0}
    ).sort([("year", -1), ("period", -1)]).to_list(200)

    # Always return the same structure
    result = {
        "contract_version": CONTRACT_VERSION,
        "cnae": cnae,
        "market_name": None,
        "activity_index": None,
        "annual_growth": None,
        "monthly_growth": None,
        "trend": None,
        "source": "INE",
        "source_table": None,
        "confidence": None,
        "updated_at": None,
        "status": "no_data" if not obs else "ok",
    }

    if not obs:
        return result

    by_metric = {}
    for o in obs:
        by_metric.setdefault(o.get("metric") or "other", []).append(o)

    result["market_name"] = obs[0].get("cnae_label")
    result["source_table"] = obs[0].get("table_id")
    result["updated_at"] = obs[0].get("fetched_at")

    # Index
    idx = sorted(by_metric.get("index", []), key=lambda x: (x.get("year", 0), x.get("period") or 0), reverse=True)
    if idx:
        result["activity_index"] = idx[0]["value"]

    # YoY
    yoy = sorted(by_metric.get("yoy_change", []), key=lambda x: (x.get("year", 0), x.get("period") or 0), reverse=True)
    if yoy:
        result["annual_growth"] = yoy[0]["value"]

    # MoM
    mom = sorted(by_metric.get("mom_change", []), key=lambda x: (x.get("year", 0), x.get("period") or 0), reverse=True)
    if mom:
        result["monthly_growth"] = mom[0]["value"]

    # Trend
    ag = result["annual_growth"]
    result["trend"] = "growing" if ag and ag > 2 else "stable" if ag and ag > -2 else "declining" if ag else "unknown"

    # Confidence based on data availability
    metrics_available = len([m for m in ["index", "yoy_change", "mom_change"] if m in by_metric])
    result["confidence"] = round(metrics_available / 3, 2)

    return result
