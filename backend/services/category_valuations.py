"""Category Valuation Engine — Persistent, auto-recalculating, resilient.

Architecture:
  transactions_normalized (with EV/EBITDA)
    ↓ on create/update/rebuild
  category_valuations (persisted, pre-calculated)
    ↓
  API → Frontend

Auto-recalculates when:
  - A transaction is created or updated with financial data
  - POST /valuations/rebuild is called
  - Startup detects stale data (>24h since last rebuild)
"""

from typing import Dict, List, Optional
from database import db
from models import new_id, now_iso
from docstudio.financial_engine import quartiles, percentile
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

CATEGORIES = [
    "Estrategia, Marca y Diseno",
    "Creatividad y Produccion",
    "Digital, Growth y Commerce",
    "Exclusivistas y Medios",
    "Comunicacion, PR y Reputacion",
    "Influencer & Creator Economy",
    "Experiencias y Activaciones",
    "Consultoria de Transformacion",
    "Data, AdTech y MarTech",
]

# Q6 — minimum number of real deals (with a usable EV/EBITDA multiple) before a
# category's median is reported as sample-sufficient. Provisional, uncalibrated,
# same convention as `thresholds.THRESHOLDS_VERSION`/`baselines.MIN_SAMPLE_SIZE`:
# before this, `_compute_metrics()` reported a "median" from as little as 1 deal.
MIN_SAMPLE_SIZE = 5


async def rebuild_valuations(
    year: int = None,
    buyer_type: str = None,
    country: str = None,
    only_observed: bool = False,
    trigger: str = "manual",
) -> Dict:
    """Rebuild all category valuations from transactions. Persist results."""
    now = now_iso()

    # Query transactions with financial data
    query = {"deleted": {"$ne": True}}

    if only_observed:
        query["confidence_level"] = {"$in": ["high", "confirmed"]}
    else:
        query["confidence_level"] = {"$ne": "low"}

    if year:
        query["year"] = year
    if buyer_type:
        query["buyer_type"] = buyer_type
    if country:
        query["geography_primary"] = {"$regex": country, "$options": "i"}

    all_transactions = await db.transactions_normalized.find(query, {"_id": 0}).to_list(5000)

    # Separate: with EV (for valuation) vs all (for count)
    transactions_with_ev = [t for t in all_transactions if t.get("ev_eurm") and t["ev_eurm"] > 0]

    # Group by category
    by_category = {}
    for tx in all_transactions:
        cat = tx.get("cis_category_suggested") or tx.get("mapped_category_name") or tx.get("sector_original") or "Sin clasificar"
        if cat not in by_category:
            by_category[cat] = {"all": [], "with_ev": []}
        by_category[cat]["all"].append(tx)
        if tx.get("ev_eurm") and tx["ev_eurm"] > 0:
            by_category[cat]["with_ev"].append(tx)

    # Calculate and persist per category
    categories = []
    for cat_name in CATEGORIES + list(set(by_category.keys()) - set(CATEGORIES)):
        cat_data = by_category.get(cat_name)
        if not cat_data:
            continue

        all_deals = cat_data["all"]
        ev_deals = cat_data["with_ev"]

        metrics = _compute_metrics(ev_deals)
        metrics["category"] = cat_name
        metrics["deals_total"] = len(all_deals)
        metrics["deals_with_financials"] = len(ev_deals)
        metrics["last_rebuilt"] = now
        metrics["rebuild_trigger"] = trigger

        categories.append(metrics)

    # Persist to category_valuations collection
    await db.category_valuations.delete_many({})
    if categories:
        await db.category_valuations.insert_many(categories)

    # Persist summary
    summary = {
        "total_deals": len(all_transactions),
        "deals_with_ev": len(transactions_with_ev),
        "deals_with_ebitda": len([t for t in all_transactions if t.get("ebitda_eurm") and t["ebitda_eurm"] > 0]),
        "deals_with_revenue": len([t for t in all_transactions if t.get("revenue_eurm") and t["revenue_eurm"] > 0]),
        "categories_covered": len([c for c in categories if c.get("deals_with_financials", 0) > 0]),
        "categories_total": len(categories),
        "total_ev_eurm": round(sum(t.get("ev_eurm", 0) for t in transactions_with_ev), 2),
        "data_available": len(transactions_with_ev) > 0,
        "last_rebuilt": now,
        "rebuild_trigger": trigger,
        "filters": {"year": year, "buyer_type": buyer_type, "country": country, "only_observed": only_observed},
    }

    await db.category_valuations_meta.delete_many({})
    await db.category_valuations_meta.insert_one(summary)

    # Return a clean copy (insert_one mutates the dict with _id)
    summary.pop("_id", None)

    # Log
    await db.valuation_rebuild_logs.insert_one({
        "log_id": new_id(),
        "rebuilt_at": now,
        "trigger": trigger,
        "total_deals": summary["total_deals"],
        "deals_with_ev": summary["deals_with_ev"],
        "categories": len(categories),
        "status": "completed",
    })

    logger.info(f"Valuations rebuilt: {summary['total_deals']} deals, {summary['deals_with_ev']} with EV, {len(categories)} categories")

    return {
        "status": "completed",
        **summary,
    }


async def get_cached_valuations() -> Dict:
    """Get pre-calculated valuations from persistent cache."""
    meta = await db.category_valuations_meta.find_one({}, {"_id": 0})
    categories = await db.category_valuations.find({}, {"_id": 0}).sort("deals_total", -1).to_list(50)

    # Heatmap
    heatmap = []
    for cat in categories:
        if cat.get("ev_ebitda_aggregate"):
            heatmap.append({
                "category": cat["category"],
                "ev_ebitda": cat["ev_ebitda_aggregate"],
                "deals": cat.get("deals_with_financials", 0),
            })

    return {
        "categories": categories,
        "heatmap": heatmap,
        "summary": meta or {
            "total_deals": 0, "deals_with_ev": 0, "deals_with_ebitda": 0,
            "categories_covered": 0, "data_available": False, "last_rebuilt": None,
        },
    }


async def get_valuation_summary() -> Dict:
    """Quick summary from persistent cache."""
    meta = await db.category_valuations_meta.find_one({}, {"_id": 0})
    if meta:
        return meta

    # Fallback: compute live
    total_deals = await db.transactions_normalized.count_documents({"deleted": {"$ne": True}})
    deals_with_ev = await db.transactions_normalized.count_documents({"ev_eurm": {"$gt": 0}, "deleted": {"$ne": True}})
    deals_with_ebitda = await db.transactions_normalized.count_documents({"ebitda_eurm": {"$gt": 0}, "deleted": {"$ne": True}})

    return {
        "total_deals": total_deals,
        "deals_with_ev": deals_with_ev,
        "deals_with_ebitda": deals_with_ebitda,
        "categories_covered": 0,
        "data_available": deals_with_ev > 0,
        "last_rebuilt": None,
    }


async def auto_rebuild_if_stale():
    """Check if valuations need rebuilding (called on startup or by scheduler)."""
    meta = await db.category_valuations_meta.find_one({}, {"_id": 0})

    if not meta or not meta.get("last_rebuilt"):
        await rebuild_valuations(trigger="startup")
        return

    # Check staleness (>24h)
    try:
        last = datetime.fromisoformat(meta["last_rebuilt"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - last > timedelta(hours=24):
            await rebuild_valuations(trigger="stale_check")
    except Exception:
        await rebuild_valuations(trigger="startup_error")


def _compute_metrics(deals: List[Dict]) -> Dict:
    """Compute valuation metrics for a set of deals. Deterministic."""
    evs = [d["ev_eurm"] for d in deals if d.get("ev_eurm") and d["ev_eurm"] > 0]
    revenues = [d["revenue_eurm"] for d in deals if d.get("revenue_eurm") and d["revenue_eurm"] > 0]
    ebitdas = [d["ebitda_eurm"] for d in deals if d.get("ebitda_eurm") and d["ebitda_eurm"] > 0]

    ev_ebitda_multiples = []
    ev_revenue_multiples = []
    for d in deals:
        ev = d.get("ev_eurm", 0)
        ebitda = d.get("ebitda_eurm", 0)
        rev = d.get("revenue_eurm", 0)
        if ev > 0 and ebitda > 0:
            ev_ebitda_multiples.append(ev / ebitda)
        if ev > 0 and rev > 0:
            ev_revenue_multiples.append(ev / rev)

    for d in deals:
        if d.get("ve_ebitda") and d["ve_ebitda"] > 0:
            ev_ebitda_multiples.append(d["ve_ebitda"])
        if d.get("ve_sales") and d["ve_sales"] > 0:
            ev_revenue_multiples.append(d["ve_sales"])

    result = {
        "deals_count": len(deals),
        "deals_with_ev": len(evs),
        "deals_with_ebitda": len(ebitdas),
        "deals_with_revenue": len(revenues),
    }

    if evs:
        result["sum_ev_eurm"] = round(sum(evs), 2)
        result["average_ev_eurm"] = round(sum(evs) / len(evs), 2)
        result["median_ev_eurm"] = round(percentile(evs, 50), 2) if len(evs) >= 2 else round(evs[0], 2)

    if evs and revenues:
        result["ev_revenue_aggregate"] = round(sum(evs) / sum(revenues), 2) if sum(revenues) > 0 else None

    if ev_revenue_multiples:
        result["ev_revenue_median"] = round(percentile(ev_revenue_multiples, 50), 2)
        result["ev_revenue_p25"] = round(percentile(ev_revenue_multiples, 25), 2)
        result["ev_revenue_p75"] = round(percentile(ev_revenue_multiples, 75), 2)

    if evs and ebitdas:
        result["ev_ebitda_aggregate"] = round(sum(evs) / sum(ebitdas), 2) if sum(ebitdas) > 0 else None

    # Q6: expose the real sample size behind the multiple, and gate "sample_sufficient"
    # on MIN_SAMPLE_SIZE — previously this reported a "median" from 1-2 deals with no
    # way for a caller to tell the difference from a well-sampled one.
    result["ev_ebitda_multiples_count"] = len(ev_ebitda_multiples)
    result["sample_sufficient"] = len(ev_ebitda_multiples) >= MIN_SAMPLE_SIZE

    if ev_ebitda_multiples:
        result["ev_ebitda_median"] = round(percentile(ev_ebitda_multiples, 50), 2)
        result["ev_ebitda_p25"] = round(percentile(ev_ebitda_multiples, 25), 2)
        result["ev_ebitda_p75"] = round(percentile(ev_ebitda_multiples, 75), 2)
        result["ev_ebitda_range"] = f"{result['ev_ebitda_p25']}x - {result['ev_ebitda_p75']}x"
        result["confidence_label"] = ("high" if len(ev_ebitda_multiples) >= MIN_SAMPLE_SIZE * 2
                                       else "medium" if len(ev_ebitda_multiples) >= MIN_SAMPLE_SIZE
                                       else "low")
    else:
        result["confidence_label"] = "insufficient_data"

    return result


async def get_marketing_agency_aggregate(min_sample_size: int = MIN_SAMPLE_SIZE) -> Optional[Dict]:
    """Q6 — pools ALL real transactions already classified into the CIS
    marketing-agency taxonomy (any of `CATEGORIES`, regardless of specific
    subcategory) into ONE real EV/EBITDA statistic.

    Deliberately coarse: there is no verified, deterministic mapping from a
    transaction's specific CIS subcategory (or from a target company's CNAE code)
    down to one of the 9 `CATEGORIES` — that classification is an LLM suggestion
    that always requires human review (`transactions/classification.py`), so this
    module has no authority to split by subcategory. Pooling all 9 avoids inventing
    that granularity while still being a real, market-observed aggregate.

    Returns None if the pooled sample doesn't meet `min_sample_size` — never
    fabricates a "market multiple" from a handful of deals.
    """
    query = {"deleted": {"$ne": True}, "confidence_level": {"$ne": "low"}}
    all_deals = await db.transactions_normalized.find(query, {"_id": 0}).to_list(5000)
    pooled = []
    for tx in all_deals:
        cat = tx.get("cis_category_suggested") or tx.get("mapped_category_name") or tx.get("sector_original") or "Sin clasificar"
        if cat in CATEGORIES:
            pooled.append(tx)
    if not pooled:
        return None

    metrics = _compute_metrics(pooled)
    if not metrics.get("sample_sufficient") or "ev_ebitda_median" not in metrics:
        return None

    return {
        "ev_ebitda_median": metrics["ev_ebitda_median"],
        "ev_ebitda_p25": metrics.get("ev_ebitda_p25"), "ev_ebitda_p75": metrics.get("ev_ebitda_p75"),
        "ev_revenue_median": metrics.get("ev_revenue_median"),
        "sample_size": metrics["ev_ebitda_multiples_count"],
        "categories_pooled": CATEGORIES,
        "source": "mna_radar", "basis": "marketing_agency_pooled",
        "min_sample_size": min_sample_size,
    }
