"""Threshold Resolver (D1) — thresholds are NEVER hardcoded in the engine.

Each signal type resolves its threshold from versioned config (`signal_thresholds`
collection), by CONTEXT: self_history · sector · size_band · territory · default.
v1 ships provisional defaults (`thr-v1`); calibration is a later, evidence-based sprint.
The resolved threshold AND its origin are recorded on every signal (full explainability).
"""

from typing import Dict, Optional, Tuple

from database import db

THRESHOLDS_VERSION = "thr-v1"

# Provisional config seed (thr-v1). This is CONFIG (data), not engine logic.
# baselines = ordered context preference; resolver falls back to default_threshold.
DEFAULT_THRESHOLDS: Dict[str, Dict] = {
    "financial.margin_strong":   {"metric": "ebitda_margin", "operator": ">",  "default_threshold": 0.15},
    "financial.margin_weak":     {"metric": "ebitda_margin", "operator": "<",  "default_threshold": 0.05},
    "financial.low_liquidity":   {"metric": "current_ratio", "operator": "<",  "default_threshold": 1.0},
    "financial.high_leverage":   {"metric": "debt_to_equity", "operator": ">", "default_threshold": 3.0},
    "financial.negative_equity": {"metric": "equity", "operator": "<",         "default_threshold": 0.0},
    "financial.net_loss":        {"metric": "net_income", "operator": "<",      "default_threshold": 0.0},
    "financial.quality_low":     {"metric": "financial_quality_score", "operator": "<", "default_threshold": 40},
    "growth.revenue_surge":      {"metric": "revenue_growth_yoy", "operator": ">", "default_threshold": 0.20},
    "growth.ebitda_expansion":   {"metric": "ebitda_growth_yoy", "operator": ">",  "default_threshold": 0.20},
    "growth.sustained":          {"metric": "revenue_cagr", "operator": ">",       "default_threshold": 0.15},
    "risk.revenue_decline":      {"metric": "revenue_growth_yoy", "operator": "<", "default_threshold": -0.15},
    "risk.revenue_anomaly":      {"metric": "abs_revenue_growth_yoy", "operator": ">", "default_threshold": 0.50},
    "market.outperforms_peers":  {"metric": "ebitda_margin_percentile", "operator": ">", "default_threshold": 0.75},
    "market.underperforms_peers":{"metric": "ebitda_margin_percentile", "operator": "<", "default_threshold": 0.25},
    "market.fragmented_sector":  {"metric": "peers_count", "operator": ">",        "default_threshold": 6},
    "operational.productivity_high": {"metric": "revenue_per_employee", "operator": ">", "default_threshold": 200000},
    "operational.productivity_low":  {"metric": "revenue_per_employee", "operator": "<", "default_threshold": 50000},
    "operational.capital_intensive": {"metric": "capital_intensity", "operator": ">",   "default_threshold": 2.0},
    "ownership.consolidator":    {"metric": "investees_count", "operator": ">=",   "default_threshold": 2},
    "ownership.group_member":    {"metric": "group_size", "operator": ">=",        "default_threshold": 2},
    # Q1 — real proxy for succession risk (see borme_bridge.py): tenure of the sole/majority
    # administrator, computed from Iberinform's real `appointment_date` field (norm_officers).
    # Provisional default (15y); calibration against actual closed successions is a later sprint.
    "opportunity.succession_signal": {"metric": "administrator_tenure_years", "operator": ">=", "default_threshold": 15},
    # structural booleans (no numeric threshold): balance_inconsistency, foreign_parent, standalone,
    # sustained_decline → evaluated directly in engine; resolver returns passthrough.
}

_cache: Optional[Dict[str, Dict]] = None


async def ensure_thresholds() -> None:
    """Idempotently seed the versioned threshold config on startup."""
    for st, cfg in DEFAULT_THRESHOLDS.items():
        await db.signal_thresholds.update_one(
            {"signal_type": st, "thresholds_version": THRESHOLDS_VERSION},
            {"$setOnInsert": {**cfg, "signal_type": st,
                              "thresholds_version": THRESHOLDS_VERSION, "baselines": {}}},
            upsert=True,
        )


async def _load() -> Dict[str, Dict]:
    global _cache
    if _cache is None:
        docs = await db.signal_thresholds.find(
            {"thresholds_version": THRESHOLDS_VERSION}, {"_id": 0}).to_list(500)
        _cache = {d["signal_type"]: d for d in docs} or dict(DEFAULT_THRESHOLDS)
    return _cache


async def set_contextual(signal_type: str, metric: str, percentile: int) -> None:
    """Q3 — mark a signal type as having a real, computed sector baseline (called by
    `baselines.py::ensure_indexes()`). Only stores the metric/percentile the baseline
    represents; the actual per-company numeric value is resolved via `context` at
    call time (see `resolve()` below), never hardcoded here."""
    await db.signal_thresholds.update_one(
        {"signal_type": signal_type, "thresholds_version": THRESHOLDS_VERSION},
        {"$set": {"baselines.sector": {"metric": metric, "percentile": percentile}}},
        upsert=True,
    )
    global _cache
    _cache = None


async def resolve(signal_type: str, context: Optional[Dict] = None) -> Tuple[float, str, Optional[Dict]]:
    """Resolve (threshold, threshold_source, baseline) for a signal type given context.

    v1: returns the versioned default (calibration deferred). Architecture supports
    baselines (self_history/sector/size_band/territory) without changing the engine.
    """
    cfg = (await _load()).get(signal_type) or DEFAULT_THRESHOLDS.get(signal_type) or {}
    baselines = cfg.get("baselines") or {}
    # Context-aware baselines (e.g. precomputed sector p75) take precedence when provided.
    if context and baselines:
        for source in ("self_history", "sector", "size_band", "territory"):
            spec = baselines.get(source)
            if spec and context.get(source) is not None:
                return float(context[source]), source, {"type": source, **spec}
    return float(cfg.get("default_threshold", 0)), "default", None
