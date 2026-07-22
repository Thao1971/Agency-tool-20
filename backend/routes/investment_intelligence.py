"""Investment Intelligence API (E7 — Índice de fragmentación sectorial / roll-up trigger).

Service-key auth, same convention as the other engine routers (financial-intelligence,
signal-intelligence).
"""

from fastapi import APIRouter, Depends, HTTPException
from auth_utils import get_current_user
from services.service_auth import require_service_key
from services.engines.investment import fragmentation as F
from services.engines.investment import rollup_thesis as RT

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


@router.get("/rollup-thesis")
async def rollup_thesis(cnae_field: str = "cnae_code", cnae_value: str = "",
                         limit_companies: int = 300, _key=Depends(require_service_key)):
    """E6 — roll-up/platform thesis for a real CNAE sector: consumes E7's fragmentation
    index (viability) and T3's sector consolidation map (real ownership + competitor
    edges) to identify an existing platform candidate (or flag that an external one is
    needed) and rank real standalone companies as add-on targets."""
    if not cnae_value:
        raise HTTPException(400, "cnae_value is required")
    try:
        return await RT.compute_rollup_thesis(cnae_field, cnae_value, limit_companies=limit_companies)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── JWT-friendly variants for the app's own frontend (same convention as
# routes/valuations.py wrapping category_valuations.py: the /fragmentation and
# /rollup-thesis endpoints above use X-API-Key for external/service consumers, which a
# browser can never safely hold — these call the exact same functions, just gated by
# the logged-in user's session instead). ──

@router.get("/fragmentation/view")
async def fragmentation_view(cnae_field: str = "cnae_code", cnae_value: str = "",
                              limit_companies: int = 500, user=Depends(get_current_user)):
    """Same as GET /fragmentation, JWT-gated for the app's own frontend."""
    if not cnae_value:
        raise HTTPException(400, "cnae_value is required")
    try:
        return await F.compute_fragmentation(cnae_field, cnae_value, limit_companies=limit_companies)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/rollup-thesis/view")
async def rollup_thesis_view(cnae_field: str = "cnae_code", cnae_value: str = "",
                              limit_companies: int = 300, user=Depends(get_current_user)):
    """Same as GET /rollup-thesis, JWT-gated for the app's own frontend."""
    if not cnae_value:
        raise HTTPException(400, "cnae_value is required")
    try:
        return await RT.compute_rollup_thesis(cnae_field, cnae_value, limit_companies=limit_companies)
    except ValueError as e:
        raise HTTPException(400, str(e))
