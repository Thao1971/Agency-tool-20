"""Investment Decision Engine API (investment-decision-engine-v1).

Consumer engine, contrato propio, auth service-key (patrón Recommendation). Thin layer:
delega en services.engines.investment_decision. Sin UI/PDF aquí."""

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.service_auth import require_service_key
from services.engines.investment_decision import ENGINE_VERSION
from services.engines.investment_decision import engine as IDE
from services.engines.investment_decision import store
from services.engines.investment_decision.scoring import COMMITTEE_WEIGHTS, RECOMMENDATION_BANDS
from services.engines.investment_decision.schemas import AnalysisRequestIn, BuyerProfileIn
from services.engines.investment_decision.capabilities import (
    compare as cap_compare, portfolio as cap_portfolio,
    recommend as cap_recommend, copilot as cap_copilot, export as cap_export,
)


class MultiRequestIn(BaseModel):
    opportunities: List[Dict[str, Any]] = []
    buyer_profile: BuyerProfileIn = BuyerProfileIn()


class RecommendRequestIn(BaseModel):
    buyer_profile: BuyerProfileIn = BuyerProfileIn()
    universe: List[Dict[str, Any]] = []


class AskRequestIn(BaseModel):
    question: str

router = APIRouter(prefix="/api/v1/investment-decision", tags=["investment_decision"])


def _meta(t0):
    return {"contract_version": "1.0", "engine_version": ENGINE_VERSION,
            "response_time_ms": round((time.time() - t0) * 1000, 1)}


@router.get("/health")
async def health(_key=Depends(require_service_key)):
    return {"engine_version": ENGINE_VERSION, "status": "ok",
            "committee": list(COMMITTEE_WEIGHTS.keys()),
            "weights": COMMITTEE_WEIGHTS, "bands": RECOMMENDATION_BANDS}


@router.post("/analyze")
async def analyze(req: AnalysisRequestIn, _key=Depends(require_service_key)):
    t0 = time.time()
    result = await IDE.analyze(req.to_engine())
    return {**_meta(t0), **result}


@router.post("/committee")
async def committee(req: AnalysisRequestIn, _key=Depends(require_service_key)):
    t0 = time.time()
    return {**_meta(t0), "committee": await IDE.committee_only(req.to_engine())}


@router.get("/decision/{decision_id}")
async def get_decision(decision_id: str, _key=Depends(require_service_key)):
    rec = await store.get(decision_id)
    if not rec:
        raise HTTPException(status_code=404, detail="decision_not_found")
    return rec


# ── Capacidades (DESIGN §11) ──
@router.post("/compare")
async def compare(req: MultiRequestIn, _key=Depends(require_service_key)):
    t0 = time.time()
    return {**_meta(t0), **await cap_compare.compare(req.opportunities, req.buyer_profile.dict())}


@router.post("/portfolio")
async def portfolio(req: MultiRequestIn, _key=Depends(require_service_key)):
    t0 = time.time()
    return {**_meta(t0), **await cap_portfolio.portfolio(req.opportunities, req.buyer_profile.dict())}


@router.post("/recommendations")
async def recommendations(req: RecommendRequestIn, _key=Depends(require_service_key)):
    t0 = time.time()
    return {**_meta(t0), **await cap_recommend.recommend(req.buyer_profile.dict(), req.universe)}


@router.post("/decision/{decision_id}/ask")
async def ask(decision_id: str, req: AskRequestIn, _key=Depends(require_service_key)):
    t0 = time.time()
    return {**_meta(t0), **await cap_copilot.ask(decision_id, req.question)}


@router.get("/decision/{decision_id}/export-payload")
async def export_payload(decision_id: str, format: str = "pdf", _key=Depends(require_service_key)):
    t0 = time.time()
    return {**_meta(t0), **await cap_export.export_payload(decision_id, format)}
