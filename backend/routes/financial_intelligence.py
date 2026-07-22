"""Financial Intelligence Engine API — the engine's own public contract.

Decoupled service: depends on nothing from arroba/Copilot/UI. Consumers obtain ALL
financial intelligence through this API, never from master_companies directly.
Protected with the existing service API key (X-API-Key).
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.engines.financial import engine as fin_engine
from services.engines.financial import ratios_library
from services.service_auth import require_service_key
from routes import engine_schemas as S

router = APIRouter(prefix="/api/v1/financial-intelligence", tags=["financial_intelligence"])


def _ok(model):
    return {200: {"model": model, "description": "Successful Response"}}


class AnalyzeRequest(BaseModel):
    identifier: str   # master_id or cif_normalized


@router.post("/analyze", responses=_ok(S.FinancialAnalyzeResponse))
async def analyze(req: AnalyzeRequest, _key=Depends(require_service_key)):
    """Full financial intelligence profile (statements, KPIs, ratios, evolution, quality,
    comparables, valuation, assessment, explainability)."""
    result = await fin_engine.analyze(req.identifier)
    if result is None:
        raise HTTPException(404, "company not found in Master Layer")
    return result


@router.post("/valuation", responses=_ok(S.FinancialValuationResponse))
async def valuation(req: AnalyzeRequest, _key=Depends(require_service_key)):
    """Valuation capability only (parity surface with the legacy Value Engine)."""
    profile = await fin_engine.analyze(req.identifier)
    if profile is None:
        raise HTTPException(404, "company not found in Master Layer")
    return {"master_id": profile["master_id"], "cif_normalized": profile["cif_normalized"],
            "valuation": profile["valuation"], "engine_version": profile["engine_version"],
            "generated_at": profile["generated_at"]}


@router.get("/ratios/catalog", responses=_ok(S.RatiosCatalogResponse))
async def ratios_catalog(_key=Depends(require_service_key)):
    """The reusable ratio library: formula + explanation + category for each ratio."""
    return {"ratios": ratios_library.definitions(), "source": ratios_library.SOURCE}
