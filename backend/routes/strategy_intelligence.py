"""Strategy Intelligence Engine API — own public contract (strategy-intelligence-v1).

Consumer of all prior engines. Produces canonical, persisted Strategic Thesis entities
(DT15). Decoupled, UI-agnostic, service-key auth. Reuses by reference; never recreates.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.engines.strategy import engine as strat_engine
from services.engines.strategy import dimensions as D
from services.engines.strategy import memory as MEM
from services.engines.signal import actions as sig_actions
from services.service_auth import require_service_key
from routes import engine_schemas as S

router = APIRouter(prefix="/api/v1/strategy-intelligence", tags=["strategy_intelligence"])


def _ok(model):
    return {200: {"model": model, "description": "Successful Response"}}


class ThesisRequest(BaseModel):
    identifier: str
    thesis_type: Optional[str] = None
    opportunity_id: Optional[str] = None
    owner: str = "system"


class ScenarioRequest(BaseModel):
    identifier: str
    scenario_types: Optional[List[str]] = None


class DecisionRequest(BaseModel):
    identifier: str
    type_a: str
    type_b: str


class LifecycleRequest(BaseModel):
    thesis_id: str
    state: str
    result: Optional[str] = None
    learning: Optional[str] = None


class ConvertRequest(BaseModel):
    thesis_id: str
    target: str


class MemoryRequest(BaseModel):
    company_master_id: Optional[str] = None
    thesis_id: Optional[str] = None
    state: Optional[str] = None
    thesis_type: Optional[str] = None


async def _req(result):
    if result is None:
        raise HTTPException(404, "company not found in Master Layer")
    return result


@router.post("/thesis", responses=_ok(S.StrategyThesisResponse))
async def thesis(req: ThesisRequest, _key=Depends(require_service_key)):
    return await _req(await strat_engine.thesis(req.identifier, req.thesis_type,
                                                req.opportunity_id, req.owner))


@router.post("/scenarios", responses=_ok(S.StrategyScenariosResponse))
async def scenarios(req: ScenarioRequest, _key=Depends(require_service_key)):
    return await _req(await strat_engine.scenarios(req.identifier, req.scenario_types))


async def _typed(identifier: str, ttype: str):
    return await _req(await strat_engine.by_type(identifier, ttype))


@router.post("/growth", responses=_ok(S.StrategyThesisResponse))
async def growth(req: ThesisRequest, _key=Depends(require_service_key)):
    return await _typed(req.identifier, "growth")


@router.post("/acquisition", responses=_ok(S.StrategyThesisResponse))
async def acquisition(req: ThesisRequest, _key=Depends(require_service_key)):
    return await _typed(req.identifier, "acquisition")


@router.post("/divestment", responses=_ok(S.StrategyThesisResponse))
async def divestment(req: ThesisRequest, _key=Depends(require_service_key)):
    return await _typed(req.identifier, "divestment")


@router.post("/partnership", responses=_ok(S.StrategyThesisResponse))
async def partnership(req: ThesisRequest, _key=Depends(require_service_key)):
    return await _typed(req.identifier, "partnership")


@router.post("/capital", responses=_ok(S.StrategyThesisResponse))
async def capital(req: ThesisRequest, _key=Depends(require_service_key)):
    return await _typed(req.identifier, "capital_raising")


@router.post("/risk", responses=_ok(S.StrategyThesisResponse))
async def risk(req: ThesisRequest, _key=Depends(require_service_key)):
    return await _typed(req.identifier, "risk")


@router.post("/decision", responses=_ok(S.StrategyDecisionResponse))
async def decision(req: DecisionRequest, _key=Depends(require_service_key)):
    return await _req(await strat_engine.decision(req.identifier, req.type_a, req.type_b))


@router.post("/lifecycle", responses=_ok(S.StrategyThesisResponse))
async def lifecycle(req: LifecycleRequest, _key=Depends(require_service_key)):
    try:
        r = await MEM.update_lifecycle(req.thesis_id, req.state, req.result, req.learning)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if r is None:
        raise HTTPException(404, "thesis not found")
    return r


@router.post("/convert", responses=_ok(S.StrategyConvertResponse))
async def convert(req: ConvertRequest, _key=Depends(require_service_key)):
    try:
        r = await MEM.convert(req.thesis_id, req.target)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if r is None:
        raise HTTPException(404, "thesis not found")
    return r


@router.post("/memory", responses=_ok(S.StrategyMemoryResponse))
async def memory(req: MemoryRequest, _key=Depends(require_service_key)):
    return {"theses": await MEM.query(req.company_master_id, req.thesis_id,
                                      req.state, req.thesis_type)}


@router.get("/catalog", responses=_ok(S.StrategyCatalogResponse))
async def catalog(_key=Depends(require_service_key)):
    return {"engine_version": strat_engine.ENGINE_VERSION,
            "strategy_method": D.SCORE_METHOD, "weights": D.WEIGHTS,
            "thesis_types": strat_engine.THESIS_TYPES,
            "strategic_dimensions": D.DIMENSION_NAMES,
            "default_scenarios": ["conservative", "base", "aggressive"],
            "lifecycle_states": MEM.LIFECYCLE_STATES, "convert_targets": MEM.CONVERT_TARGETS,
            "canonical_actions": sig_actions.CANONICAL_ACTIONS,
            "evidence_version": strat_engine.EVIDENCE_VERSION,
            "canonical_entity": "strategic_theses (DT15)"}
