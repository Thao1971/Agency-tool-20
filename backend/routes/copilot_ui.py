"""ARROBA Copilot — API interna (JWT) para la pantalla de chat DENTRO del agency tool.

La API externa `/api/v1/copilot` usa service-key (la consume ARROBA). Esta capa fina expone lo mismo
pero autenticada con el JWT del usuario del agency tool (`get_current_user`), derivando tenant/usuario
de la sesión. Reutiliza `services.copilot.orchestrate` (no recrea nada). Aditivo.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth_utils import get_current_user
from services.copilot import orchestrate, ORCHESTRATOR_VERSION
from services.copilot import session as SESSION
from services.engines.investment_decision.committee import capabilities as CAP

router = APIRouter(prefix="/api/v1/copilot-ui", tags=["copilot-ui"])


def _uctx(user: Dict) -> Dict:
    return {"tenant_id": user.get("tenant_id") or user.get("org_id") or "agency-tool",
            "user_id": user.get("id") or user.get("email"), "role": user.get("role")}


class AskIn(BaseModel):
    question: Optional[str] = None
    company_id: Optional[str] = None
    cif: Optional[str] = None
    session_id: Optional[str] = None
    buyer_profile: Optional[Dict[str, Any]] = None
    inputs: Optional[Dict[str, Any]] = None
    opportunities: Optional[List[Dict[str, Any]]] = None
    universe: Optional[List[Dict[str, Any]]] = None


class SessionCloseIn(BaseModel):
    session_id: str


@router.get("/health")
async def health(user=Depends(get_current_user)):
    return {"orchestrator_version": ORCHESTRATOR_VERSION, "status": "ok", "auth": "jwt"}


@router.get("/capabilities")
async def capabilities(user=Depends(get_current_user)):
    return {"committee": CAP.all_capabilities()}


@router.post("/ask")
async def ask(req: AskIn, user=Depends(get_current_user)):
    r = {"question": req.question, "company_id": req.company_id, "cif": req.cif,
         "opportunity_id": req.company_id or req.cif, "session_id": req.session_id,
         "buyer_profile": req.buyer_profile, "inputs": req.inputs,
         "opportunities": req.opportunities, "universe": req.universe, "user": _uctx(user)}
    return await orchestrate(r)


@router.post("/session/close")
async def session_close(req: SessionCloseIn, user=Depends(get_current_user)):
    return await SESSION.close(req.session_id)
