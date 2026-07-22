"""Contextual baselines (Q3 — Activar baselines contextuales de Signal).

`thresholds.py::resolve()` already supports a `context` parameter and a per-type
`baselines.sector` config (D1 architecture placeholder), but nothing ever computed
a real sector-relative value or called `resolve()` with a non-empty context — every
signal used the flat `thr-v1` default regardless of sector or company size. This
module closes that gap using ONLY data the platform already computes:

- Sector: `master_companies.classification.cnae_section` (real, structural, Iberinform).
- Size band: derived from `master_companies.financials.latest.revenue` (real field,
  already populated by `master_builder.py`). No new bucket concept invented — this is
  the same "0.3x-3x revenue" comparables logic `financial/engine.py::financial_comparables`
  already uses, made into discrete, reusable bands.
- Metrics: `ebitda_margin`, `revenue_per_employee`, `revenue_growth_yoy` — already
  computed per company by `services/engines/financial/engine.py`. This module only
  aggregates values ALREADY produced by that engine across companies in the same
  (sector, size_band); it does not compute any new financial metric.

Every bucket below a minimum sample size is treated as absent (falls back to the
`thr-v1` default) — a contextual threshold from 3 companies is worse than no
context at all, and `resolve()`'s explainability contract must stay honest about it.
"""

import statistics
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from database import db
from services.engines.financial import engine as fin_engine
from services.engines.signal import thresholds as TH

BASELINES_VERSION = "baselines-v1"
MIN_SAMPLE_SIZE = 12
MAX_COMPANIES_PER_BUCKET = 300  # bound cost of the batch job, same convention as routes/signal_intelligence.py::_aggregate

# signal_type -> (financial engine kpi field, percentile used as the contextual threshold)
BASELINE_METRIC_MAP: Dict[str, Tuple[str, int]] = {
    "financial.margin_strong":       ("ebitda_margin", 75),
    "financial.margin_weak":         ("ebitda_margin", 25),
    "operational.productivity_high": ("revenue_per_employee", 75),
    "operational.productivity_low":  ("revenue_per_employee", 25),
    "growth.revenue_surge":          ("revenue_growth_yoy", 75),
}

SIZE_BANDS = (
    ("micro", 0, 2_000_000),
    ("small", 2_000_000, 10_000_000),
    ("medium", 10_000_000, 50_000_000),
    ("large", 50_000_000, float("inf")),
)

_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    await db.sector_size_baselines.create_index(
        [("sector", 1), ("size_band", 1), ("metric", 1), ("baselines_version", 1)], unique=True)
    for stype, (metric, pct) in BASELINE_METRIC_MAP.items():
        await TH.set_contextual(stype, metric, pct)
    _INDEXED = True


def size_band_for(revenue: Optional[float]) -> Optional[str]:
    if revenue is None:
        return None
    for band, lo, hi in SIZE_BANDS:
        if lo <= revenue < hi:
            return band
    return None


def _percentiles(values: List[float]) -> Optional[Dict[str, float]]:
    if len(values) < MIN_SAMPLE_SIZE:
        return None
    q = statistics.quantiles(sorted(values), n=4, method="inclusive")  # [p25, p50, p75]
    return {"p25": round(q[0], 4), "p50": round(q[1], 4), "p75": round(q[2], 4)}


async def compute_sector_size_baselines(limit_sectors: int = 50) -> Dict:
    """Batch job (admin-triggered): recompute sector x size_band x metric percentiles
    from companies already analyzed by the Financial Intelligence Engine. Reuses
    `fin_engine.analyze()` — does not duplicate its math."""
    await ensure_indexes()
    sectors = await db.master_companies.distinct(
        "classification.cnae_section", {"classification.cnae_section": {"$ne": None},
                                         "financials.latest.revenue": {"$ne": None}})
    sectors = sectors[:limit_sectors]
    now = datetime.now(timezone.utc).isoformat()
    buckets_written = 0
    companies_sampled = 0

    for sector in sectors:
        companies = await db.master_companies.find(
            {"classification.cnae_section": sector, "financials.latest.revenue": {"$ne": None}},
            {"_id": 0, "master_id": 1, "financials.latest.revenue": 1},
        ).to_list(MAX_COMPANIES_PER_BUCKET)

        by_band: Dict[str, List[str]] = {}
        for c in companies:
            band = size_band_for(((c.get("financials") or {}).get("latest") or {}).get("revenue"))
            if band:
                by_band.setdefault(band, []).append(c["master_id"])

        for band, master_ids in by_band.items():
            metric_values: Dict[str, List[float]] = {m: [] for m, _ in BASELINE_METRIC_MAP.values()}
            for mid in master_ids:
                fin = await fin_engine.analyze(mid)
                companies_sampled += 1
                if not fin:
                    continue
                kpis = fin.get("kpis") or {}
                for metric in metric_values:
                    v = kpis.get(metric)
                    if v is not None:
                        metric_values[metric].append(float(v))

            for metric, values in metric_values.items():
                pct = _percentiles(values)
                if not pct:
                    continue
                await db.sector_size_baselines.update_one(
                    {"sector": sector, "size_band": band, "metric": metric,
                     "baselines_version": BASELINES_VERSION},
                    {"$set": {**pct, "sample_size": len(values), "computed_at": now}},
                    upsert=True,
                )
                buckets_written += 1

    return {"sectors_processed": len(sectors), "companies_sampled": companies_sampled,
            "buckets_written": buckets_written, "min_sample_size": MIN_SAMPLE_SIZE,
            "baselines_version": BASELINES_VERSION}


async def context_map(master: Dict) -> Dict[str, Tuple[float, int]]:
    """Per-company lookup used by `engine.py::_evaluate()`. Returns, for each signal
    type that has a usable sector baseline, `(value, sample_size)` — absent entries
    mean "fall back to the thr-v1 default" (either no baseline computed yet, or the
    bucket had fewer than MIN_SAMPLE_SIZE companies)."""
    sector = (master.get("classification") or {}).get("cnae_section")
    revenue = ((master.get("financials") or {}).get("latest") or {}).get("revenue")
    band = size_band_for(revenue) if revenue is not None else None
    if not sector or not band:
        return {}

    out: Dict[str, Tuple[float, int]] = {}
    for stype, (metric, pct) in BASELINE_METRIC_MAP.items():
        doc = await db.sector_size_baselines.find_one(
            {"sector": sector, "size_band": band, "metric": metric,
             "baselines_version": BASELINES_VERSION},
            {"_id": 0, f"p{pct}": 1, "sample_size": 1},
        )
        if not doc or (doc.get("sample_size") or 0) < MIN_SAMPLE_SIZE:
            continue
        value = doc.get(f"p{pct}")
        if value is not None:
            out[stype] = (float(value), int(doc["sample_size"]))
    return out
