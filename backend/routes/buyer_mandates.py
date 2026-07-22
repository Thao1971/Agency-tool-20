"""Buyer Mandates API (E1 — G1: Buyer Intelligence por mandato).

User-facing (JWT auth, like data_layer's admin endpoints) — a buyer/advisor creates a
mandate once, then queries matching targets repeatedly as the universe changes (new
BORME succession signals, new companies ingested, etc.), instead of the old one-shot
"who's similar to this single target" affinity matching in recommendation-intelligence.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from auth_utils import get_current_user
from models import BuyerMandateCreate, BuyerMandateUpdate
from services.engines.recommendation import mandates as M

router = APIRouter(prefix="/api/v1/buyer-mandates", tags=["buyer_mandates"])


@router.post("")
async def create_mandate(req: BuyerMandateCreate, user=Depends(get_current_user)):
    if req.mandate_type not in M.MANDATE_TYPES:
        raise HTTPException(400, f"mandate_type must be one of {M.MANDATE_TYPES}")
    if req.ownership_preference not in M.OWNERSHIP_PREFERENCES:
        raise HTTPException(400, f"ownership_preference must be one of {M.OWNERSHIP_PREFERENCES}")
    doc = await M.create_mandate(req.dict(), created_by=user.get("id"))
    return doc


@router.get("")
async def list_mandates(status: Optional[str] = None, mine_only: bool = False,
                        user=Depends(get_current_user)):
    created_by = user.get("id") if mine_only else None
    rows = await M.list_mandates(status=status, created_by=created_by)
    return {"count": len(rows), "mandates": rows}


@router.get("/{mandate_id}")
async def get_mandate(mandate_id: str, user=Depends(get_current_user)):
    doc = await M.get_mandate(mandate_id)
    if not doc:
        raise HTTPException(404, "mandate not found")
    return doc


@router.patch("/{mandate_id}")
async def update_mandate(mandate_id: str, req: BuyerMandateUpdate, user=Depends(get_current_user)):
    if req.status and req.status not in ("active", "paused", "closed"):
        raise HTTPException(400, "status must be one of active|paused|closed")
    if req.ownership_preference and req.ownership_preference not in M.OWNERSHIP_PREFERENCES:
        raise HTTPException(400, f"ownership_preference must be one of {M.OWNERSHIP_PREFERENCES}")
    doc = await M.update_mandate(mandate_id, req.dict(exclude_unset=True))
    if not doc:
        raise HTTPException(404, "mandate not found")
    return doc


@router.get("/{mandate_id}/targets")
async def targets_for_mandate(mandate_id: str, limit: int = 20, user=Depends(get_current_user)):
    """The mandate -> universe direction: rank real companies against this mandate."""
    result = await M.find_targets_for_mandate(mandate_id, limit=limit)
    if result is None:
        raise HTTPException(404, "mandate not found")
    return result


@router.get("/for-target/{master_id}")
async def mandates_for_target(master_id: str, limit: int = 10, user=Depends(get_current_user)):
    """The reverse direction: given one company (e.g. one Q1 just flagged with a
    succession signal, or one appearing in the Q4 feed), which active mandates want it."""
    result = await M.find_mandates_for_target(master_id, limit=limit)
    if result is None:
        raise HTTPException(404, "company not found in Master Layer")
    return result
