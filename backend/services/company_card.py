"""Batch company summary cards for search/resolve result tables (NO N+1).

Given a list of master_ids, returns one `summary` per id using exactly:
  • 1 batch query over master_companies (financials/size/location/classification/identity)
  • 1 batch query over signals (active, with dimensions) grouped by master_id
  • ≤1 revenue-array load per DISTINCT CNAE section (cached), for sector percentiles
…and everything else computed in memory. Deterministic, explainable, honest with gaps
(missing blocks lower confidence / return null rather than inventing values).
"""

import time
from bisect import bisect_left
from typing import Dict, List, Optional

from database import db
from services.engines.signal.engine import _score as _signal_score
from services.engines.financial.engine import financial_quality as _fin_quality
from services.skills_valuation import _resolve_multiples

_MASTER_PROJ = {
    "_id": 0, "master_id": 1, "cif_normalized": 1, "updated_at": 1,
    "identity.legal_name": 1,
    "classification.cnae_section": 1, "classification.cnae_description": 1,
    "size.employees_total": 1, "location.municipio": 1,
    "financials.latest": 1, "financials.history": 1,
}

_DIM_KEYS = ("impact", "confidence", "urgency", "persistence")

# ── sector revenue arrays (cached) for percentile position ───────────────────
_SECTOR_REV_CACHE: Dict[str, tuple] = {}
_SECTOR_REV_TTL = 600
_MIN_SECTOR = 5  # honesty threshold (same spirit as FE.ranking)


async def _sector_revenues(section: str) -> List[float]:
    now = time.time()
    ent = _SECTOR_REV_CACHE.get(section)
    if ent and (now - ent[0]) < _SECTOR_REV_TTL:
        return ent[1]
    revs: List[float] = []
    async for d in db.master_companies.find(
            {"classification.cnae_section": section, "financials.latest.revenue": {"$ne": None}},
            {"_id": 0, "financials.latest.revenue": 1}):
        r = ((d.get("financials") or {}).get("latest") or {}).get("revenue")
        if r is not None:
            revs.append(r)
    revs.sort()
    _SECTOR_REV_CACHE[section] = (now, revs)
    return revs


def _signal_badge(types: set) -> str:
    """Precedence (M&A): riesgo > buscando_financiacion > comprando > alto_crecimiento > estable."""
    def has_prefix(*prefixes):
        return any(t and t.startswith(prefixes) for t in types)
    if ({"financial.net_loss", "financial.negative_equity", "financial.quality_low"} & types
            or has_prefix("risk.")):
        return "riesgo"
    if has_prefix("capital."):
        return "buscando_financiacion"
    if "ownership.consolidator" in types:
        return "comprando"
    if has_prefix("growth.") or {"market.outperforms_peers", "financial.margin_strong"} & types:
        return "alto_crecimiento"
    return "estable"


def _growth_pct(history: List[Dict]) -> Optional[float]:
    revs = [(h.get("year"), h.get("revenue")) for h in (history or [])
            if h.get("revenue") is not None and h.get("year") is not None]
    revs.sort(key=lambda x: x[0], reverse=True)
    if len(revs) < 2 or not revs[1][1]:
        return None
    return round((revs[0][1] - revs[1][1]) / abs(revs[1][1]), 4)


def _valuation(section, ebitda, revenue) -> Optional[Dict]:
    mult = _resolve_multiples(section)
    if ebitda and ebitda > 0:
        lo, hi = mult["ev_ebitda"]; base, basis = ebitda, "ev_ebitda"
    elif revenue and revenue > 0:
        lo, hi = mult["ev_revenue"]; base, basis = revenue, "ev_revenue"
    else:
        return None
    low, high = round(lo * base), round(hi * base)
    return {"low": low, "mid": round((low + high) / 2), "high": high,
            "currency": "EUR", "basis": basis}


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _arroba_score(latest, series, growth_pct, market_pct, signal_score) -> Optional[Dict]:
    """Explainable 0-100 composite: financial_quality 40% · growth 20% · market 20% · signals 20%.
    Reweights over available components; partial + lower confidence when blocks are missing;
    null when there is not enough to be reliable."""
    comps: Dict[str, Dict] = {}
    if series and (latest or {}).get("revenue") is not None:
        comps["financial_quality"] = {"value": _fin_quality(series, audited=None)["score"], "weight": 0.40}
    if growth_pct is not None:
        comps["growth"] = {"value": round(_clamp(50 + growth_pct * 100)), "weight": 0.20}
    if market_pct is not None:
        comps["market_position"] = {"value": round(_clamp(market_pct)), "weight": 0.20}
    if signal_score is not None:
        comps["signals"] = {"value": round(_clamp(signal_score)), "weight": 0.20}
    if not comps:
        return None
    wsum = sum(c["weight"] for c in comps.values())
    if wsum < 0.2:
        return None
    value = round(sum(c["value"] * c["weight"] for c in comps.values()) / wsum)
    return {"value": value, "confidence": round(wsum, 2),
            "partial": wsum < 0.999, "components": comps}


async def build_summaries(master_ids: List[str]) -> Dict[str, Optional[Dict]]:
    ids = [i for i in dict.fromkeys(master_ids) if i]
    if not ids:
        return {}

    masters: Dict[str, Dict] = {}
    async for m in db.master_companies.find({"master_id": {"$in": ids}}, _MASTER_PROJ):
        masters[m["master_id"]] = m

    sig_by: Dict[str, List[Dict]] = {}
    async for s in db.signals.find(
            {"master_id": {"$in": ids}, "status": "active"},
            {"_id": 0, "master_id": 1, "signal_type": 1, "dimensions": 1}):
        sig_by.setdefault(s["master_id"], []).append(s)

    sections = {((m.get("classification") or {}).get("cnae_section")) for m in masters.values()}
    sect_rev = {sec: await _sector_revenues(sec) for sec in sections if sec}

    out: Dict[str, Optional[Dict]] = {}
    for mid in ids:
        m = masters.get(mid)
        if not m:
            out[mid] = None
            continue
        cls = m.get("classification") or {}
        fin = m.get("financials") or {}
        latest = fin.get("latest") or {}
        history = fin.get("history") or []
        section = cls.get("cnae_section")
        revenue, ebitda = latest.get("revenue"), latest.get("ebitda")

        sigs = sig_by.get(mid, [])
        scorable = [s for s in sigs if isinstance(s.get("dimensions"), dict)
                    and all(k in s["dimensions"] for k in _DIM_KEYS)]
        signal_score = _signal_score(scorable)["signal_score"] if scorable else None
        badge = _signal_badge({s.get("signal_type") for s in sigs}) if sigs else None

        growth = _growth_pct(history)

        market_pct = None
        revs = sect_rev.get(section)
        if revs and len(revs) >= _MIN_SECTOR and revenue is not None:
            market_pct = round(bisect_left(revs, revenue) / len(revs) * 100)

        series = None
        if revenue is not None:
            series = [latest] + [h for h in history if h.get("year") != latest.get("year")]

        arroba = _arroba_score(latest, series, growth, market_pct, signal_score)

        out[mid] = {
            "revenue": revenue,
            "ebitda": ebitda,
            "ebitda_margin": latest.get("ebitda_margin"),
            "growth_pct": growth,
            "signal_score": signal_score,
            "signal_badge": badge,
            "valuation": _valuation(section, ebitda, revenue),
            "employees": (m.get("size") or {}).get("employees_total"),
            "arroba_score": (arroba or {}).get("value"),
            "arroba_score_detail": arroba,
            "market_position_pct": market_pct,
            "city": (m.get("location") or {}).get("municipio"),
            "activity_label": cls.get("cnae_description"),
            "updated_at": m.get("updated_at"),
        }
    return out
