"""Signal Intelligence Engine API — the engine's own public contract (signal-intelligence-v1).

Decoupled, UI-agnostic (D8). Any consumer (arroba, Copilot, Recommendation/Strategy/
Transaction engines, external APIs) obtains ALL signal intelligence here, never from
master_companies directly. Protected with the service API key (X-API-Key).
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db
from auth_utils import get_current_user
from services.engines.signal import engine as sig_engine
from services.engines.signal import taxonomy, thresholds, actions, composites
from services.engines.signal import persistence as P
from services.engines.signal import borme_bridge as BB
from services.engines.signal import baselines as BL
from services.engines.signal import succession_intelligence as SI
from services.service_auth import require_service_key
from routes import engine_schemas as S

router = APIRouter(prefix="/api/v1/signal-intelligence", tags=["signal_intelligence"])


def _ok(model):
    return {200: {"model": model, "description": "Successful Response"}}


class AnalyzeRequest(BaseModel):
    identifier: str
    windows: Optional[List[str]] = None


class SectorRequest(BaseModel):
    cnae_section: Optional[str] = None
    cnae_code: Optional[str] = None
    limit: int = 25


class TerritoryRequest(BaseModel):
    provincia: Optional[str] = None
    municipio: Optional[str] = None
    limit: int = 25


class OpportunitiesRequest(BaseModel):
    cnae_section: Optional[str] = None
    provincia: Optional[str] = None
    signal_types: Optional[List[str]] = None
    sort_by_dimension: str = "impact"
    new_since_days: Optional[int] = None  # Q4 — only signals first detected in the last N days
    trend: Optional[str] = None           # Q4 — "improving" | "worsening" | "stable"
    limit: int = 20


class HistoryRequest(BaseModel):
    identifier: str
    signal_type: Optional[str] = None


class BormeLinkBackfillRequest(BaseModel):
    limit_companies: int = 500


class BaselinesComputeRequest(BaseModel):
    limit_sectors: int = 50


@router.post("/analyze", responses=_ok(S.SignalAnalyzeResponse))
async def analyze(req: AnalyzeRequest, _key=Depends(require_service_key)):
    result = await sig_engine.analyze(req.identifier, windows=req.windows)
    if result is None:
        raise HTTPException(404, "company not found in Master Layer")
    return result


async def _aggregate(query: dict, limit: int):
    counts: dict = {}
    type_counts: dict = {}
    top: list = []
    n = 0
    async for m in db.master_companies.find(query, {"_id": 0, "master_id": 1}).limit(limit):
        prof = await sig_engine.analyze(m["master_id"])
        if not prof:
            continue
        n += 1
        for cat, c in prof["counts_by_category"].items():
            counts[cat] = counts.get(cat, 0) + c
        for s in prof["signals"]:
            type_counts[s["signal_type"]] = type_counts.get(s["signal_type"], 0) + 1
            if s["category"] == "opportunity":
                top.append({"master_id": prof["master_id"], "name": prof["identity"]["name"],
                            "signal_type": s["signal_type"], "dimensions": s["dimensions"]})
    top.sort(key=lambda x: x["dimensions"]["impact"], reverse=True)
    return {"companies_analyzed": n, "counts_by_category": counts,
            "counts_by_type": type_counts, "top_opportunities": top[:10]}


@router.post("/sector", responses=_ok(S.SignalAggregateResponse))
async def by_sector(req: SectorRequest, _key=Depends(require_service_key)):
    if not req.cnae_section and not req.cnae_code:
        raise HTTPException(400, "cnae_section or cnae_code required")
    q = {"financials.latest.revenue": {"$ne": None}}
    if req.cnae_code:
        q["classification.cnae_code"] = req.cnae_code
    else:
        q["classification.cnae_section"] = req.cnae_section
    agg = await _aggregate(q, req.limit)
    return {"criteria": {"cnae_section": req.cnae_section, "cnae_code": req.cnae_code}, **agg,
            "engine_version": sig_engine.ENGINE_VERSION}


@router.post("/territory", responses=_ok(S.SignalAggregateResponse))
async def by_territory(req: TerritoryRequest, _key=Depends(require_service_key)):
    if not req.provincia and not req.municipio:
        raise HTTPException(400, "provincia or municipio required")
    q = {"financials.latest.revenue": {"$ne": None}}
    if req.municipio:
        q["location.municipio"] = req.municipio
    else:
        q["location.provincia"] = req.provincia
    agg = await _aggregate(q, req.limit)
    return {"criteria": {"provincia": req.provincia, "municipio": req.municipio}, **agg,
            "engine_version": sig_engine.ENGINE_VERSION}


async def _list_opportunities(cnae_section: Optional[str], provincia: Optional[str],
                               signal_types: Optional[List[str]], sort_by_dimension: str,
                               new_since_days: Optional[int], trend: Optional[str], limit: int) -> Dict:
    """Shared query logic behind POST /opportunities (X-API-Key) and GET /opportunities/view
    (JWT, for the app's own frontend) — same convention as
    routes/investment_intelligence.py's fragmentation/rollup-thesis /view endpoints."""
    q = {"category": "opportunity", "status": "active"}
    if signal_types:
        q["signal_type"] = {"$in": signal_types}
    if trend:
        q["trend"] = trend
    if new_since_days is not None:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=new_since_days)).isoformat()
        q["first_detected_at"] = {"$gte": cutoff}
    dim = sort_by_dimension if sort_by_dimension in ("impact", "confidence", "urgency", "persistence") else "impact"
    rows = []
    async for s in db.signals.find(q, {"_id": 0}).sort(f"dimensions.{dim}", -1).limit(limit * 3):
        m = await db.master_companies.find_one({"master_id": s["master_id"]},
                                               {"_id": 0, "identity.legal_name": 1,
                                                "classification.cnae_section": 1, "location.provincia": 1})
        if not m:
            continue
        if cnae_section and (m.get("classification") or {}).get("cnae_section") != cnae_section:
            continue
        if provincia and (m.get("location") or {}).get("provincia") != provincia:
            continue
        rows.append({"master_id": s["master_id"], "name": (m.get("identity") or {}).get("legal_name"),
                     "signal_type": s["signal_type"], "dimensions": s["dimensions"],
                     "recommended_actions": s.get("recommended_actions"),
                     "explanation": s.get("explanation"), "is_composite": s.get("is_composite", False),
                     "first_detected_at": s.get("first_detected_at"), "last_seen_at": s.get("last_seen_at"),
                     "trend": s.get("trend"), "occurrences": s.get("occurrences")})
        if len(rows) >= limit:
            break
    return {"sorted_by": dim, "count": len(rows), "opportunities": rows,
            "engine_version": sig_engine.ENGINE_VERSION}


async def _opportunities_feed(days: int, limit: int, cnae_section: Optional[str],
                               provincia: Optional[str]) -> Dict:
    """Shared query logic behind GET /opportunities/feed (X-API-Key) and
    GET /opportunities/feed/view (JWT)."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = {"category": "opportunity", "status": "active", "first_detected_at": {"$gte": cutoff}}
    rows = []
    async for s in db.signals.find(q, {"_id": 0}).sort("first_detected_at", -1).limit(limit * 3):
        m = await db.master_companies.find_one({"master_id": s["master_id"]},
                                               {"_id": 0, "identity.legal_name": 1,
                                                "classification.cnae_section": 1, "location.provincia": 1})
        if not m:
            continue
        if cnae_section and (m.get("classification") or {}).get("cnae_section") != cnae_section:
            continue
        if provincia and (m.get("location") or {}).get("provincia") != provincia:
            continue
        rows.append({"master_id": s["master_id"], "name": (m.get("identity") or {}).get("legal_name"),
                     "signal_type": s["signal_type"], "dimensions": s["dimensions"],
                     "explanation": s.get("explanation"), "is_composite": s.get("is_composite", False),
                     "first_detected_at": s.get("first_detected_at"), "trend": s.get("trend")})
        if len(rows) >= limit:
            break
    return {"window_days": days, "since": cutoff, "count": len(rows), "opportunities": rows,
            "engine_version": sig_engine.ENGINE_VERSION}


@router.post("/opportunities", responses=_ok(S.SignalOpportunitiesResponse))
async def opportunities(req: OpportunitiesRequest, _key=Depends(require_service_key)):
    """Q4 — Ranking of opportunities from persisted signals (populated at scale by
    `bootstrap.py::build_signals_canonical()`; run /bootstrap or /analyze/​/sector first).
    `new_since_days`/`trend` use the lifecycle fields `persistence.py::persist()` already
    tracks (`first_detected_at`, `trend`) — no new data, just exposing what was write-only."""
    return await _list_opportunities(req.cnae_section, req.provincia, req.signal_types,
                                     req.sort_by_dimension, req.new_since_days, req.trend, req.limit)


@router.get("/opportunities/feed")
async def opportunities_feed(days: int = 7, limit: int = 50, cnae_section: Optional[str] = None,
                              provincia: Optional[str] = None, _key=Depends(require_service_key)):
    """Q4 — chronological feed: opportunities FIRST DETECTED in the last N days, newest
    first. Complements /opportunities (ranked snapshot by impact) with the "what's new
    since I last checked" view the roadmap names — same underlying data, different sort."""
    return await _opportunities_feed(days, limit, cnae_section, provincia)


# ── JWT-friendly variants for the app's own frontend (same convention as
# routes/investment_intelligence.py wrapping fragmentation/rollup-thesis: the endpoints
# above use X-API-Key for external/service consumers, which a browser can never safely
# hold — these call the exact same query logic, just gated by the logged-in user's
# session instead). ──

@router.get("/opportunities/view", responses=_ok(S.SignalOpportunitiesResponse))
async def opportunities_view(cnae_section: Optional[str] = None, provincia: Optional[str] = None,
                              signal_types: Optional[str] = None, sort_by_dimension: str = "impact",
                              new_since_days: Optional[int] = None, trend: Optional[str] = None,
                              limit: int = 20, user=Depends(get_current_user)):
    """Same as POST /opportunities, JWT-gated for the app's own frontend.
    signal_types is a comma-separated string here (query params can't carry a list cleanly)."""
    types = [t.strip() for t in signal_types.split(",") if t.strip()] if signal_types else None
    return await _list_opportunities(cnae_section, provincia, types, sort_by_dimension,
                                     new_since_days, trend, limit)


@router.get("/opportunities/feed/view")
async def opportunities_feed_view(days: int = 7, limit: int = 50, cnae_section: Optional[str] = None,
                                   provincia: Optional[str] = None, user=Depends(get_current_user)):
    """Same as GET /opportunities/feed, JWT-gated for the app's own frontend."""
    return await _opportunities_feed(days, limit, cnae_section, provincia)


@router.get("/catalog/view", responses=_ok(S.SignalCatalogResponse))
async def catalog_view(user=Depends(get_current_user)):
    """Same as GET /catalog, JWT-gated — lets the frontend show human-readable signal
    type labels/categories/actions for the Opportunities screen's filters."""
    return await catalog()


@router.get("/catalog", responses=_ok(S.SignalCatalogResponse))
async def catalog(_key=Depends(require_service_key)):
    return {"taxonomy_version": taxonomy.TAXONOMY_VERSION,
            "thresholds_version": thresholds.THRESHOLDS_VERSION,
            "actions_version": actions.ACTIONS_VERSION,
            "composites_version": composites.COMPOSITES_VERSION,
            "categories": taxonomy.CATEGORIES,
            "signal_types": taxonomy.catalog(),
            "canonical_actions": actions.CANONICAL_ACTIONS,
            "composites": [{"signal_type": k, **{kk: vv for kk, vv in v.items() if kk != "description"},
                            "description": v["description"]} for k, v in composites.COMPOSITES.items()]}


@router.get("/signal/{signal_id}", responses=_ok(S.SignalRecord))
async def get_signal(signal_id: str, _key=Depends(require_service_key)):
    s = await P.get_signal(signal_id)
    if not s:
        raise HTTPException(404, "signal not found")
    return s


@router.post("/history", responses=_ok(S.SignalHistoryResponse))
async def history(req: HistoryRequest, _key=Depends(require_service_key)):
    master = await db.master_companies.find_one(
        {"$or": [{"master_id": req.identifier}, {"cif_normalized": req.identifier}]},
        {"_id": 0, "master_id": 1})
    if not master:
        raise HTTPException(404, "company not found in Master Layer")
    return {"master_id": master["master_id"],
            "signals": await P.get_history(master["master_id"], req.signal_type)}


@router.post("/borme-link-backfill")
async def borme_link_backfill(req: BormeLinkBackfillRequest, _key=Depends(require_service_key)):
    """Q1 admin trigger: batch-link BORME events to master_companies (idempotent,
    watermarked by `borme_link_checked_at`). Run repeatedly until `companies_remaining` is 0."""
    return await BB.link_events_to_master(limit_companies=req.limit_companies)


@router.post("/baselines/compute")
async def compute_baselines(req: BaselinesComputeRequest, _key=Depends(require_service_key)):
    """Q3 admin trigger: recompute sector x size_band percentile baselines from
    companies already analyzed by the Financial Intelligence Engine. Re-run periodically
    (e.g. monthly) as more companies/financials get ingested."""
    return await BL.compute_sector_size_baselines(limit_sectors=req.limit_sectors)


@router.get("/baselines/status")
async def baselines_status(_key=Depends(require_service_key)):
    """Coverage check: how many (sector, size_band, metric) buckets have a usable
    baseline (>= MIN_SAMPLE_SIZE), broken down by metric."""
    buckets = await db.sector_size_baselines.find(
        {"baselines_version": BL.BASELINES_VERSION}, {"_id": 0}).to_list(5000)
    by_metric: dict = {}
    for b in buckets:
        m = b["metric"]
        by_metric.setdefault(m, {"buckets": 0, "companies_covered": 0})
        by_metric[m]["buckets"] += 1
        by_metric[m]["companies_covered"] += b.get("sample_size", 0)
    return {"total_buckets": len(buckets), "min_sample_size": BL.MIN_SAMPLE_SIZE,
            "by_metric": by_metric, "baselines_version": BL.BASELINES_VERSION}


@router.get("/succession-profile/{identifier}")
async def succession_profile(identifier: str, _key=Depends(require_service_key)):
    """E2 — full Succession Intelligence profile for one company (master_id or CIF).
    Richer than the `opportunity.succession_signal` pass/fail: exposes admin_count,
    family-surname overlap (proxy, not confirmed kinship), a possible successor already
    appointed, company age (when a BORME constitution event is linked), and whether
    financial-stagnation signals are active — plus the 0-100 succession_risk_score and
    the human-readable reasons behind it. Returns null profile (not 404) when there's an
    administrator record but E2 has nothing further to add beyond Q1's own signal."""
    master = await db.master_companies.find_one(
        {"$or": [{"master_id": identifier}, {"cif_normalized": identifier}]}, {"_id": 0})
    if not master:
        raise HTTPException(404, "company not found in Master Layer")
    profile = await SI.build_profile(master)
    return {"master_id": master["master_id"], "profile": profile}
