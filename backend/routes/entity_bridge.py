"""Entity Bridge admin routes — Master Record quality tool (M3-phase-2).

Read-only over legacy; builds the canonical bridge + historical quality metrics. JWT admin.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from auth_utils import get_current_user
from services.data_layer.master import entity_bridge as EB

router = APIRouter(prefix="/api/v1/master/bridge", tags=["entity_bridge"])


class RunRequest(BaseModel):
    scope: str = "full"
    limit: Optional[int] = None
    dry_run: bool = False


@router.post("/run")
async def run(req: RunRequest, user=Depends(get_current_user)):
    return await EB.run_bridge(scope=req.scope, limit=req.limit, dry_run=req.dry_run)


@router.get("/runs")
async def runs(limit: int = Query(20, le=100), user=Depends(get_current_user)):
    return {"runs": await EB.list_runs(limit)}


@router.get("/runs/{run_id}")
async def run_detail(run_id: str, user=Depends(get_current_user)):
    r = await EB.get_run(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


@router.post("/runs/{run_id}/rollback")
async def rollback(run_id: str, user=Depends(get_current_user)):
    return await EB.rollback_run(run_id)
