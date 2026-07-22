"""Investment Intelligence API (E7 — Índice de fragmentación sectorial / roll-up trigger).

Service-key auth, same convention as the other engine routers (financial-intelligence,
signal-intelligence).
"""

from fastapi import APIRouter, Depends, HTTPException
from services.service_auth import require_service_key
from services.engines.investment import fragmentation as F

router = APIRouter(prefix="/api/v1/investment-intelligence", tags=["investment_intelligence"])


@router.get("/fragmentation")
async def fragmentation(cnae_field: str = "cnae_code", cnae_value: str = "",
                         limit_companies: int = 500, _key=Depends(require_service_key)):
    """E7 — fragmentation/roll-up score for a real CNAE sector: HHI concentration
    (grouped by Q2's real ownership.group_id, not per-company), count of real
    standalone add-on targets, and multiple dispersion when Q6 has real market data
    for the sector (agencies only today)."""
    if not cnae_value:
        raise HTTPException(400, "cnae_value is required")
    try:
        return await F.compute_fragmentation(cnae_field, cnae_value, limit_companies=limit_companies)
    except ValueError as e:
        raise HTTPException(400, str(e))
