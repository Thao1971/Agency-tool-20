"""Recommendation Intelligence Engine API — own public contract (recommendation-intelligence-v1).

First CONSUMER engine. Decoupled, UI-agnostic, service-key auth. Reuses producers;
never recreates intelligence. Investors/advisors → unavailable (source_not_available, DR1).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.engines.recommendation import engine as rec_engine
from services.engines.recommendation import scoring as S
from services.engines.recommendation import memory as MEM
from services.engines.signal import actions as sig_actions
from services.service_auth import require_service_key
from routes import engine_schemas as S

router = APIRouter(prefix="/api/v1/recommendation-intelligence", tags=["recommendation_intelligence"])


def _ok(model):
    return {200: {"model": model, "description": "Successful Response"}}


class TargetRequest(BaseModel):
    identifier: str
    limit: int = 10


class MatchingRequest(BaseModel):
    a: str
    b: str


class ExplainRequest(BaseModel):
    target: str
    candidate: str
    recommendation_type: str = "comparable"


class FeedbackRequest(BaseModel):
    recommendation_id: str
    event: str
    outcome: Optional[str] = None
    notes: Optional[str] = None


class MemoryRequest(BaseModel):
    target: Optional[str] = None
    recommendation_id: Optional[str] = None
    state: Optional[str] = None


async def _require(result):
    if result is None:
        raise HTTPException(404, "company not found in Master Layer")
    return result


@router.post("/comparables", responses=_ok(S.RecommendationSetResponse))
async def comparables(req: TargetRequest, _key=Depends(require_service_key)):
    return await _require(await rec_engine.comparables(req.identifier, req.limit))


@router.post("/buyers", responses=_ok(S.RecommendationSetResponse))
async def buyers(req: TargetRequest, _key=Depends(require_service_key)):
    return await _require(await rec_engine.buyers(req.identifier, req.limit))


@router.post("/sellers", responses=_ok(S.RecommendationSetResponse))
async def sellers(req: TargetRequest, _key=Depends(require_service_key)):
    return await _require(await rec_engine.sellers(req.identifier, req.limit))


@router.post("/opportunities", responses=_ok(S.RecommendationSetResponse))
async def opportunities(req: TargetRequest, _key=Depends(require_service_key)):
    return await _require(await rec_engine.opportunities(req.identifier, req.limit))


@router.post("/investors", responses=_ok(S.RecommendationUnavailableResponse))
async def investors(req: TargetRequest, _key=Depends(require_service_key)):
    return rec_engine.unavailable("investor")   # DR1: source_not_available


@router.post("/advisors", responses=_ok(S.RecommendationUnavailableResponse))
async def advisors(req: TargetRequest, _key=Depends(require_service_key)):
    return rec_engine.unavailable("advisor")    # DR1: source_not_available


@router.post("/matching", responses=_ok(S.RecommendationMatchingResponse))
async def matching(req: MatchingRequest, _key=Depends(require_service_key)):
    return await _require(await rec_engine.matching(req.a, req.b))


@router.post("/explain", responses=_ok(S.RecommendationExplainResponse))
async def explain(req: ExplainRequest, _key=Depends(require_service_key)):
    target = await rec_engine._load_master(req.target)
    cand = await rec_engine._load_master(req.candidate)
    if not target or not cand:
        raise HTTPException(404, "target or candidate not found in Master Layer")
    ctx = await rec_engine._target_context(req.target)
    from services.engines.semantic import engine as sem_engine
    sim = await sem_engine.similar(req.target, limit=50, same_section=False)
    score = next((r["score"] for r in (sim or {}).get("similar", [])
                  if r["master_id"] == cand["master_id"]), 0.0)
    cand["_semantic_score"] = score
    rec = await rec_engine._build_rec(target, cand, req.recommendation_type, score, None, ctx)
    return rec


@router.post("/feedback", responses=_ok(S.RecommendationFeedbackResponse))
async def feedback(req: FeedbackRequest, _key=Depends(require_service_key)):
    try:
        return await MEM.record_feedback(req.recommendation_id, req.event, req.outcome, req.notes)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/memory", responses=_ok(S.RecommendationMemoryResponse))
async def memory(req: MemoryRequest, _key=Depends(require_service_key)):
    return {"count": 0, "memory": await MEM.query_memory(req.target, req.recommendation_id, req.state)}


@router.get("/catalog", responses=_ok(S.RecommendationCatalogResponse))
async def catalog(_key=Depends(require_service_key)):
    return {"engine_version": rec_engine.ENGINE_VERSION,
            "recommendation_method": S.SCORE_METHOD, "weights": S.WEIGHTS,
            "fit_dimensions": list(S.WEIGHTS.keys()),
            "recommendation_types": ["comparable", "buyer", "seller", "investor",
                                     "advisor", "opportunity", "match"],
            "recommendation_roles": list(rec_engine.ACTIONS_BY_ROLE.keys()),
            "available_types": ["comparable", "buyer", "seller", "matching", "opportunity"],
            "unavailable_types": {"investor": "source_not_available",
                                  "advisor": "source_not_available"},
            "canonical_actions": sig_actions.CANONICAL_ACTIONS,
            "actions_version": sig_actions.ACTIONS_VERSION,
            "evidence_version": rec_engine.EVIDENCE_VERSION,
            "lifecycle_states": MEM.LIFECYCLE_STATES,
            "feedback_events": MEM.FEEDBACK_EVENTS,
            "deferred": ["investors universe", "advisors universe",
                         "materialized Recommendation Graph"]}
