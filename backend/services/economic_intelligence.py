"""Economic Intelligence Layer — Unified economic metrics per CNAE.

Aggregates ALL sources into a single queryable layer:
  - Iberinform: revenue, EBITDA, employees, margins
  - INE: active companies, creation/dissolution, YoY
  - BORME: corporate activity count
  - Procurement: public contracts count + amount
  - DataComex: exports, imports, trade balance
  - Banco de España: macro context (national)

Collection: economic_metrics — one doc per (cnae_code, source, metric, period)
Collection: economic_signals — derived signals per CNAE

Any module in arroba.com queries this layer instead of individual sources.
"""

import logging
import math
from typing import Dict, List
from database import db
from models import new_id, now_iso
from services.cnae_catalog import CNAE_DIVISIONS, get_section_for_division

logger = logging.getLogger(__name__)


async def rebuild_economic_metrics() -> Dict:
    """Rebuild all economic_metrics from source collections."""
    now = now_iso()
    metrics = []

    # 1. Iberinform — revenue, EBITDA, employees per CNAE per year
    metrics += await _aggregate_iberinform(now)

    # 2. INE — active companies, creation, dissolution (national, distributed by CNAE)
    metrics += await _aggregate_ine_demography(now)

    # 3. BORME — corporate events per CNAE
    metrics += await _aggregate_borme(now)

    # 4. Procurement — public contracts per CNAE
    metrics += await _aggregate_procurement(now)

    # 5. DataComex — trade per TARIC→CNAE
    metrics += await _aggregate_datacomex(now)

    # 6. Banco de España — macro (national level, not per CNAE)
    metrics += await _aggregate_macro(now)

    # Persist
    await db.economic_metrics.delete_many({})
    if metrics:
        await db.economic_metrics.insert_many(metrics)

    # Create indexes
    await db.economic_metrics.create_index([("cnae_code", 1), ("source", 1), ("metric", 1), ("period", 1)])
    await db.economic_metrics.create_index("cnae_code")
    await db.economic_metrics.create_index("metric")

    return {
        "status": "completed",
        "total_metrics": len(metrics),
        "sources": _count_by_source(metrics),
        "cnae_codes": len(set(m["cnae_code"] for m in metrics if m.get("cnae_code"))),
        "generated_at": now,
    }


async def rebuild_economic_signals() -> Dict:
    """Generate economic signals from metrics."""
    now = now_iso()
    signals = []

    # Get all CNAE divisions with data
    cnae_codes = await db.economic_metrics.distinct("cnae_code", {"cnae_code": {"$ne": "national"}})

    for cnae in cnae_codes:
        cnae_metrics = await db.economic_metrics.find(
            {"cnae_code": cnae}, {"_id": 0}
        ).to_list(200)

        s = _compute_signals_for_cnae(cnae, cnae_metrics, now)
        signals.extend(s)

    await db.economic_signals.delete_many({})
    if signals:
        await db.economic_signals.insert_many(signals)

    return {
        "status": "completed",
        "signals_generated": len(signals),
        "cnae_codes": len(cnae_codes),
        "generated_at": now,
    }


async def get_cnae_economic_profile(cnae_code: str) -> Dict:
    """Get complete economic profile for a CNAE code. The main query endpoint."""
    metrics = await db.economic_metrics.find(
        {"cnae_code": cnae_code}, {"_id": 0}
    ).to_list(500)

    signals = await db.economic_signals.find(
        {"cnae_code": cnae_code}, {"_id": 0}
    ).to_list(50)

    # Organize by category
    profile = {
        "cnae_code": cnae_code,
        "cnae_label": CNAE_DIVISIONS.get(cnae_code, {}).get("label", ""),
        "cnae_section": get_section_for_division(cnae_code),
        "revenue": _extract_latest(metrics, "iberinform", "avg_revenue"),
        "ebitda": _extract_latest(metrics, "iberinform", "avg_ebitda"),
        "ebitda_margin": _extract_latest(metrics, "iberinform", "avg_ebitda_margin"),
        "employment": _extract_latest(metrics, "iberinform", "avg_employees"),
        "companies_count": _extract_latest(metrics, "iberinform", "companies_count"),
        "active_companies_national": _extract_latest(metrics, "ine", "active_companies_estimate"),
        "new_companies_estimate": _extract_latest(metrics, "ine", "new_companies_estimate"),
        "dissolved_estimate": _extract_latest(metrics, "ine", "dissolved_estimate"),
        "exports_eur": _extract_latest(metrics, "datacomex", "exports_eur"),
        "imports_eur": _extract_latest(metrics, "datacomex", "imports_eur"),
        "trade_balance_eur": _extract_latest(metrics, "datacomex", "trade_balance_eur"),
        "coverage_ratio": _extract_latest(metrics, "datacomex", "coverage_ratio"),
        "procurement_contracts": _extract_latest(metrics, "procurement", "contracts_count"),
        "procurement_amount_eur": _extract_latest(metrics, "procurement", "contracts_amount"),
        "borme_events": _extract_latest(metrics, "borme", "events_count"),
        "revenue_growth": _compute_growth(metrics, "iberinform", "avg_revenue"),
        "employment_growth": _compute_growth(metrics, "iberinform", "avg_employees"),
        "export_growth": _compute_growth(metrics, "datacomex", "exports_eur"),
        "signals": signals,
        "sources_available": list(set(m["source"] for m in metrics)),
        "total_metrics": len(metrics),
    }

    # Trend
    rev_growth = profile["revenue_growth"]
    if rev_growth and rev_growth.get("yoy_pct") is not None:
        yoy = rev_growth["yoy_pct"]
        profile["trend"] = "up" if yoy > 2 else "down" if yoy < -2 else "stable"
    else:
        profile["trend"] = "stable"

    return profile


# ══════════════════════════════════════════
# SOURCE AGGREGATORS
# ══════════════════════════════════════════

async def _aggregate_iberinform(now: str) -> List[Dict]:
    """Aggregate Iberinform financials per CNAE per year."""
    pipeline = [
        {"$lookup": {
            "from": "iberinform_companies",
            "localField": "company_id",
            "foreignField": "company_id",
            "as": "comp",
        }},
        {"$unwind": "$comp"},
        {"$match": {"comp.cnae_division": {"$ne": None}}},
        {"$group": {
            "_id": {"cnae": "$comp.cnae_division", "year": "$year"},
            "avg_revenue": {"$avg": "$revenue"},
            "avg_ebitda": {"$avg": "$ebitda"},
            "avg_ebitda_margin": {"$avg": "$ebitda_margin"},
            "avg_employees": {"$avg": "$employees"},
            "total_revenue": {"$sum": "$revenue"},
            "companies_count": {"$sum": 1},
        }},
    ]
    raw = await db.iberinform_financials.aggregate(pipeline).to_list(500)

    metrics = []
    for r in raw:
        cnae = r["_id"]["cnae"]
        year = r["_id"]["year"]
        period = f"{year}"

        for metric_name in ["avg_revenue", "avg_ebitda", "avg_ebitda_margin", "avg_employees", "total_revenue", "companies_count"]:
            val = r.get(metric_name)
            if val is not None:
                unit = "EUR" if "revenue" in metric_name or "ebitda" in metric_name else (
                    "ratio" if "margin" in metric_name else "count"
                )
                metrics.append(_metric_doc(cnae, "iberinform", metric_name, period, round(val, 2), unit, now))

    return metrics


async def _aggregate_ine_demography(now: str) -> List[Dict]:
    """INE business demography — national figures distributed by CNAE."""
    from services.iberinform_processor import CNAE_DIVISION_DISTRIBUTION

    active = await db.business_demography.find_one(
        {"indicator_key": "companies_active", "status": "ok"}, {"_id": 0}, sort=[("date", -1)]
    )
    created = await db.business_demography.find_one(
        {"indicator_key": "companies_created", "status": "ok"}, {"_id": 0}, sort=[("date", -1)]
    )
    dissolved = await db.business_demography.find_one(
        {"indicator_key": "companies_dissolved", "status": "ok"}, {"_id": 0}, sort=[("date", -1)]
    )

    total_active = (active.get("value", 0) if active else 0) or 3_300_000
    total_created = created.get("value", 0) if created else 0
    total_dissolved = dissolved.get("value", 0) if dissolved else 0
    yoy = created.get("yoy_change_pct", 0) if created else 0

    period = str(active.get("year", 2025)) if active else "2025"
    metrics = []

    for div_code, share in CNAE_DIVISION_DISTRIBUTION.items():
        est_active = round(total_active * share)
        est_created = round(total_created * share)
        est_dissolved = round(total_dissolved * share)

        metrics.append(_metric_doc(div_code, "ine", "active_companies_estimate", period, est_active, "count", now))
        if total_created > 0:
            metrics.append(_metric_doc(div_code, "ine", "new_companies_estimate", period, est_created, "count", now))
        if total_dissolved > 0:
            metrics.append(_metric_doc(div_code, "ine", "dissolved_estimate", period, est_dissolved, "count", now))
        if yoy:
            metrics.append(_metric_doc(div_code, "ine", "national_yoy_pct", period, round(yoy, 2), "pct", now))

    # National totals
    metrics.append(_metric_doc("national", "ine", "active_companies", period, total_active, "count", now))
    metrics.append(_metric_doc("national", "ine", "companies_created", period, total_created, "count", now))
    metrics.append(_metric_doc("national", "ine", "companies_dissolved", period, total_dissolved, "count", now))

    return metrics


async def _aggregate_borme(now: str) -> List[Dict]:
    """BORME corporate events per CNAE."""
    pipeline = [
        {"$match": {"cnae_division": {"$ne": None}}},
        {"$group": {"_id": "$cnae_division", "count": {"$sum": 1}}},
    ]
    raw = await db.borme_events.aggregate(pipeline).to_list(100)

    return [_metric_doc(r["_id"], "borme", "events_count", "all_time", r["count"], "count", now) for r in raw]


async def _aggregate_procurement(now: str) -> List[Dict]:
    """Procurement contracts mapped to CNAE via CPV."""
    from services.cnae_catalog import cpv_to_cnae_division

    pipeline = [
        {"$group": {
            "_id": "$cpv_code",
            "count": {"$sum": 1},
            "amount": {"$sum": {"$ifNull": ["$amount", 0]}},
        }},
    ]
    raw = await db.public_procurement_contracts.aggregate(pipeline).to_list(200)

    by_cnae = {}
    for r in raw:
        cnae = cpv_to_cnae_division(r["_id"] or "")
        if cnae:
            if cnae not in by_cnae:
                by_cnae[cnae] = {"count": 0, "amount": 0}
            by_cnae[cnae]["count"] += r["count"]
            by_cnae[cnae]["amount"] += r["amount"]

    metrics = []
    for cnae, data in by_cnae.items():
        metrics.append(_metric_doc(cnae, "procurement", "contracts_count", "all_time", data["count"], "count", now))
        metrics.append(_metric_doc(cnae, "procurement", "contracts_amount", "all_time", round(data["amount"], 2), "EUR", now))

    return metrics


async def _aggregate_datacomex(now: str) -> List[Dict]:
    """DataComex trade data mapped to CNAE via TARIC."""
    from services.taxonomy_intelligence import resolve_batch

    # Get trade metrics by TARIC
    raw = await db.datacomex_trade_metrics.find({}, {"_id": 0}).to_list(5000)
    if not raw:
        return []

    taric_codes = list(set(r["taric_code"] for r in raw))
    taric_to_cnae = await resolve_batch("taric", taric_codes)

    metrics = []
    for r in raw:
        cnae_list = taric_to_cnae.get(r["taric_code"], [])
        for mapping in cnae_list:
            cnae = mapping["cnae"]
            # Signals Weighted Engine: split value by normalized weight (weights sum to 1.0
            # per TARIC code → the full economic value is distributed, never discarded).
            weight = mapping["weight"]
            period = str(r.get("year", ""))

            exports = round(r.get("exports_eur", 0) * weight, 2)
            imports = round(r.get("imports_eur", 0) * weight, 2)
            balance = round(exports - imports, 2)
            coverage = round(exports / imports, 4) if imports > 0 else None

            if exports > 0:
                metrics.append(_metric_doc(cnae, "datacomex", "exports_eur", period, exports, "EUR", now))
            if imports > 0:
                metrics.append(_metric_doc(cnae, "datacomex", "imports_eur", period, imports, "EUR", now))
            if balance != 0:
                metrics.append(_metric_doc(cnae, "datacomex", "trade_balance_eur", period, balance, "EUR", now))
            if coverage is not None:
                metrics.append(_metric_doc(cnae, "datacomex", "coverage_ratio", period, coverage, "ratio", now))

    return metrics


async def _aggregate_macro(now: str) -> List[Dict]:
    """Banco de España macro indicators (national level)."""
    latest = await db.macro_indicators.find(
        {}, {"_id": 0, "indicator_key": 1, "value": 1, "unit": 1, "date": 1}
    ).sort("date", -1).limit(20).to_list(20)

    seen = set()
    metrics = []
    for ind in latest:
        key = ind["indicator_key"]
        if key in seen:
            continue
        seen.add(key)
        metrics.append(_metric_doc(
            "national", "banco_espana", key,
            str(ind.get("date", ""))[:10],
            ind.get("value"),
            ind.get("unit", ""),
            now,
        ))

    return metrics


# ══════════════════════════════════════════
# SIGNAL COMPUTATION
# ══════════════════════════════════════════

def _compute_signals_for_cnae(cnae: str, metrics: List[Dict], now: str) -> List[Dict]:
    """Compute economic signals for a single CNAE from its metrics."""
    signals = []
    sources_used = list(set(m["source"] for m in metrics))

    # Revenue growth signal
    rev_growth = _compute_growth_from_metrics(metrics, "iberinform", "avg_revenue")
    if rev_growth and rev_growth.get("yoy_pct") is not None:
        yoy = rev_growth["yoy_pct"]
        if yoy > 15:
            signals.append(_signal_doc(cnae, "revenue_boom", 0.85, sources_used, now,
                f"Crecimiento ingresos {yoy:.1f}% interanual"))
        elif yoy < -10:
            signals.append(_signal_doc(cnae, "revenue_decline", 0.85, sources_used, now,
                f"Caida ingresos {yoy:.1f}% interanual"))

    # High corporate activity (BORME)
    borme = [m for m in metrics if m["source"] == "borme" and m["metric"] == "events_count"]
    if borme and borme[0]["value"] > 200:
        signals.append(_signal_doc(cnae, "high_corporate_activity", 0.9, ["borme"], now,
            f"{borme[0]['value']} eventos mercantiles registrados"))

    # Export strength
    exports = [m for m in metrics if m["source"] == "datacomex" and m["metric"] == "exports_eur"]
    if exports:
        total_exp = sum(m["value"] for m in exports if m["value"])
        if total_exp > 1_000_000_000:
            signals.append(_signal_doc(cnae, "export_powerhouse", 0.9, ["datacomex"], now,
                "Exportaciones >1.000M EUR"))

    # Trade surplus
    balance = [m for m in metrics if m["source"] == "datacomex" and m["metric"] == "trade_balance_eur"]
    if balance:
        latest_balance = sorted(balance, key=lambda x: x["period"], reverse=True)[0]
        if latest_balance["value"] and latest_balance["value"] > 500_000_000:
            signals.append(_signal_doc(cnae, "trade_surplus", 0.85, ["datacomex"], now,
                "Superavit comercial >500M EUR"))
        elif latest_balance["value"] and latest_balance["value"] < -500_000_000:
            signals.append(_signal_doc(cnae, "trade_deficit", 0.85, ["datacomex"], now,
                "Deficit comercial >500M EUR"))

    # Employment growth
    emp_growth = _compute_growth_from_metrics(metrics, "iberinform", "avg_employees")
    if emp_growth and emp_growth.get("yoy_pct") is not None:
        if emp_growth["yoy_pct"] > 10:
            signals.append(_signal_doc(cnae, "employment_growth", 0.8, ["iberinform"], now,
                f"Crecimiento empleo {emp_growth['yoy_pct']:.1f}%"))

    # Public demand
    proc = [m for m in metrics if m["source"] == "procurement" and m["metric"] == "contracts_count"]
    if proc and proc[0]["value"] >= 3:
        signals.append(_signal_doc(cnae, "public_demand", 0.8, ["procurement"], now,
            f"{proc[0]['value']} contratos publicos adjudicados"))

    return signals


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════

def _metric_doc(cnae: str, source: str, metric: str, period: str, value, unit: str, now: str) -> Dict:
    return {
        "metric_id": new_id(),
        "cnae_code": cnae,
        "source": source,
        "metric": metric,
        "period": period,
        "value": value,
        "unit": unit,
        "last_updated": now,
    }


def _signal_doc(cnae: str, signal_type: str, confidence: float, sources: List[str], now: str, description: str = "") -> Dict:
    return {
        "signal_id": new_id(),
        "cnae_code": cnae,
        "signal_type": signal_type,
        "confidence": confidence,
        "sources_used": sources,
        "description": description,
        "generated_at": now,
    }


def _extract_latest(metrics: List[Dict], source: str, metric_name: str) -> Dict | None:
    """Extract the latest value for a specific source+metric."""
    filtered = [m for m in metrics if m["source"] == source and m["metric"] == metric_name]
    if not filtered:
        return None
    latest = sorted(filtered, key=lambda x: x.get("period", ""), reverse=True)[0]
    return {"value": latest["value"], "period": latest["period"], "unit": latest["unit"]}


def _compute_growth(metrics: List[Dict], source: str, metric_name: str) -> Dict | None:
    """Compute YoY growth for a metric."""
    return _compute_growth_from_metrics(metrics, source, metric_name)


def _compute_growth_from_metrics(metrics: List[Dict], source: str, metric_name: str) -> Dict | None:
    filtered = [m for m in metrics if m["source"] == source and m["metric"] == metric_name and m.get("period", "").isdigit()]
    if len(filtered) < 2:
        return None
    sorted_m = sorted(filtered, key=lambda x: x["period"], reverse=True)
    current = sorted_m[0]
    previous = sorted_m[1]
    if previous["value"] and previous["value"] > 0 and current["value"] is not None:
        yoy = ((current["value"] - previous["value"]) / previous["value"]) * 100
        return {"yoy_pct": round(yoy, 2), "current_period": current["period"], "previous_period": previous["period"]}
    return None


def _count_by_source(metrics: List[Dict]) -> Dict[str, int]:
    counts = {}
    for m in metrics:
        s = m["source"]
        counts[s] = counts.get(s, 0) + 1
    return counts
