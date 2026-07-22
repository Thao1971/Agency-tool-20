"""Watchlist API (Q7 — Transaction Intelligence: seguimiento + alertas in-app).

JWT auth (same convention as Buyer Mandates, E1) — a user follows specific companies
and gets in-app alerts when the Signal Engine's real, persisted signals (Q1) fire for
them. No email/push channel exists in this codebase today (verified — see
`services/watchlist.py` docstring); this is in-app only.
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth_utils import get_current_user
from database import db
from services import watchlist as W

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


async def _attach_company_names(rows: List[Dict]) -> List[Dict]:
    """Frontend convenience only: watchlist/alerts docs store master_id, never a name
    (see services/watchlist.py) — resolve it here in the route layer so the UI doesn't
    show raw IDs, without touching the service module's persisted shape."""
    master_ids = list({r["master_id"] for r in rows if r.get("master_id")})
    if not master_ids:
        return rows
    names = {}
    async for m in db.master_companies.find(
        {"master_id": {"$in": master_ids}}, {"_id": 0, "master_id": 1, "identity.legal_name": 1}):
        names[m["master_id"]] = (m.get("identity") or {}).get("legal_name")
    return [{**r, "company_name": names.get(r.get("master_id"))} for r in rows]


class WatchCreate(BaseModel):
    master_id: str
    notes: Optional[str] = None


@router.post("")
async def add_watch(req: WatchCreate, user=Depends(get_current_user)):
    doc = await W.add_watch(user["id"], req.master_id, req.notes)
    # Immediate feedback: surface any already-active signals for this company right away,
    # instead of making the user wait for the next scheduler sweep.
    await W.sync_alerts_for_user(user["id"])
    return doc


@router.get("")
async def list_watches(user=Depends(get_current_user)):
    rows = await W.list_watches(user["id"])
    rows = await _attach_company_names(rows)
    return {"count": len(rows), "watches": rows}


@router.delete("/{master_id}")
async def remove_watch(master_id: str, user=Depends(get_current_user)):
    removed = await W.remove_watch(user["id"], master_id)
    if not removed:
        raise HTTPException(404, "not watching this company")
    return {"status": "removed", "master_id": master_id}


@router.get("/alerts")
async def list_alerts(unread_only: bool = False, limit: int = 50, user=Depends(get_current_user)):
    rows = await W.list_alerts(user["id"], unread_only=unread_only, limit=limit)
    rows = await _attach_company_names(rows)
    return {"count": len(rows), "alerts": rows}


@router.get("/alerts/unread-count")
async def unread_count(user=Depends(get_current_user)):
    return {"unread_count": await W.unread_count(user["id"])}


@router.post("/alerts/{alert_id}/mark-read")
async def mark_alert_read(alert_id: str, user=Depends(get_current_user)):
    ok = await W.mark_alert_read(user["id"], alert_id)
    if not ok:
        raise HTTPException(404, "alert not found")
    return {"status": "read", "alert_id": alert_id}


@router.post("/sync")
async def manual_sync(user=Depends(get_current_user)):
    """Manual trigger (also runs automatically via `watchlist_scheduler.py`)."""
    return await W.sync_alerts_for_user(user["id"])
