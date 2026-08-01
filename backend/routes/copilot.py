"""ARROBA Copilot — API de orquestación (copilot-orchestrator-v1). Voz única sobre el Orquestador.
Auth service-key. Thin layer: delega en services.copilot."""

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.service_auth import require_service_key
from services.copilot import ORCHESTRATOR_VERSION, orchestrate
from services.copilot import intent as INTENT
from services.copilot import memory as MEMORY
from services.copilot import session as SESSION
from services.copilot import entity_memory as ENTITY
from services.copilot import feedback as FEEDBACK
from services.copilot import governance as GOV
from services.copilot import metrics as METRICS
from services.copilot import auth as AUTH
from services.copilot import actions as ACTIONS
from services.engines.investment_decision.committee import capabilities as CAP

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class UserIn(BaseModel):
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    role: Optional[str] = None


class AskIn(BaseModel):
    question: Optional[str] = None
    company_id: Optional[str] = None
    cif: Optional[str] = None
    buyer_profile: Optional[Dict[str, Any]] = None
    screen: Optional[str] = None
    session_id: Optional[str] = None
    user: Optional[UserIn] = None
    inputs: Optional[Dict[str, Any]] = None       # evidencia precalculada opcional (si el caller la tiene)
    opportunities: Optional[List[Dict[str, Any]]] = None
    universe: Optional[List[Dict[str, Any]]] = None

    def to_req(self) -> Dict[str, Any]:
        return {"question": self.question, "company_id": self.company_id, "cif": self.cif,
                "opportunity_id": self.company_id or self.cif,
                "buyer_profile": self.buyer_profile, "screen": self.screen,
                "session_id": self.session_id,
                "user": self.user.dict() if self.user else None, "inputs": self.inputs,
                "opportunities": self.opportunities, "universe": self.universe}


class MemoryIn(BaseModel):
    tenant_id: str
    user_id: str
    patch: Optional[Dict[str, Any]] = None


class SessionCloseIn(BaseModel):
    session_id: str


class EntityHistoryIn(BaseModel):
    tenant_id: str
    user_id: str
    company_id: str
    limit: int = 20


class FeedbackIn(BaseModel):
    tenant_id: str
    user_id: str
    event: str
    company_id: Optional[str] = None
    dimensions: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class BiasIn(BaseModel):
    tenant_id: str
    user_id: str


class GovIn(BaseModel):
    tenant_id: str
    user_id: str
    confirm: bool = False       # requerido en acciones sensibles (export)


class MetricsIn(BaseModel):
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None


class ForgetIn(BaseModel):
    tenant_id: str
    user_id: str
    scope: str = "all"
    confirm: bool = False       # derecho al olvido: confirmación explícita


def _meta(t0):
    return {"orchestrator_version": ORCHESTRATOR_VERSION,
            "response_time_ms": round((time.time() - t0) * 1000, 1)}


@router.get("/health")
async def health(_key=Depends(require_service_key)):
    return {"orchestrator_version": ORCHESTRATOR_VERSION, "status": "ok",
            "levels": ["L0", "L1", "L2", "L3", "L4"]}


@router.get("/capabilities")
async def capabilities(_key=Depends(require_service_key)):
    """Manifiesto declarativo del comité: qué cubre cada especialista, motores, KPIs, peso y veto."""
    return {"committee": CAP.all_capabilities()}


@router.get("/actions/contract")
async def actions_contract(_key=Depends(require_service_key)):
    """Contrato de acciones para el front: tipos, params, rutas y qué debe hacer la UI."""
    return ACTIONS.CONTRACT


@router.post("/metrics/summary")
async def metrics_summary(req: MetricsIn, key=Depends(require_service_key)):
    """Observabilidad: volumen, niveles, degradado, latencia (avg/p95), cobertura y tasa de NBA."""
    if req.tenant_id:
        AUTH.assert_tenant(key, req.tenant_id)
    return await METRICS.summary(req.tenant_id, req.user_id)


@router.post("/ask")
async def ask(req: AskIn, key=Depends(require_service_key)):
    t0 = time.time()
    if req.user and req.user.tenant_id:
        AUTH.assert_tenant(key, req.user.tenant_id)
    return {**_meta(t0), **await orchestrate(req.to_req())}


@router.post("/classify")
async def classify(req: AskIn, _key=Depends(require_service_key)):
    """Diagnóstico: a qué nivel/target enrutaría (sin ejecutar)."""
    return {"intent": INTENT.classify(req.question or "", req.screen)}


@router.post("/session/close")
async def session_close(req: SessionCloseIn, _key=Depends(require_service_key)):
    """Cierra la sesión (logout). Una sesión cerrada no se reanuda."""
    return await SESSION.close(req.session_id)


@router.post("/memory/get")
async def memory_get(req: MemoryIn, key=Depends(require_service_key)):
    """Lo que el Copilot 'sabe' del usuario (configurado). Transparencia (§6 canon)."""
    AUTH.assert_tenant(key, req.tenant_id)
    return {"memory_version": MEMORY.MEMORY_VERSION,
            "memory": await MEMORY.get_user_memory(req.tenant_id, req.user_id)}


@router.post("/memory/set")
async def memory_set(req: MemoryIn, key=Depends(require_service_key)):
    """Guarda campos CONFIGURADOS por el usuario (whitelist; no caducan)."""
    AUTH.assert_tenant(key, req.tenant_id)
    return {"memory_version": MEMORY.MEMORY_VERSION,
            "memory": await MEMORY.set_user_memory(req.tenant_id, req.user_id, req.patch or {})}


@router.post("/entity/history")
async def entity_history(req: EntityHistoryIn, key=Depends(require_service_key)):
    """Historia clínica de una compañía para este usuario (más reciente primero). No caduca."""
    AUTH.assert_tenant(key, req.tenant_id)
    return {"entity_memory_version": ENTITY.ENTITY_MEMORY_VERSION,
            "history": await ENTITY.history(req.tenant_id, req.user_id, req.company_id, req.limit)}


@router.post("/feedback")
async def feedback_record(req: FeedbackIn, key=Depends(require_service_key)):
    """Registra feedback (accept/dismiss/ignore/outcome_*). Alimenta el sesgo de ranking (90 días)."""
    AUTH.assert_tenant(key, req.tenant_id)
    return await FEEDBACK.record(req.tenant_id, req.user_id, req.event, req.company_id,
                                 req.dimensions, req.notes)


@router.post("/feedback/bias")
async def feedback_bias(req: BiasIn, key=Depends(require_service_key)):
    """Sesgo de ranking vigente y su porqué (transparencia; tope ±10 %, ventana 90 días)."""
    AUTH.assert_tenant(key, req.tenant_id)
    bias = await FEEDBACK.compute_bias(req.tenant_id, req.user_id)
    return {"feedback_version": FEEDBACK.FEEDBACK_VERSION, "bias": bias,
            "explanations": FEEDBACK.summarize(bias)}


@router.post("/governance/whats-known")
async def gov_whats_known(req: GovIn, key=Depends(require_service_key)):
    """Panel 'lo que sé de ti': resumen legible de la memoria del usuario."""
    AUTH.assert_tenant(key, req.tenant_id)
    return await GOV.whats_known(req.tenant_id, req.user_id)


@router.post("/governance/export")
async def gov_export(req: GovIn, key=Depends(require_service_key)):
    """Volcado completo de la memoria del usuario (portabilidad). Sensible: requiere confirm=true."""
    AUTH.assert_tenant(key, req.tenant_id)
    AUTH.assert_confirm(req.confirm)
    return await GOV.export_user(req.tenant_id, req.user_id)


@router.post("/governance/forget")
async def gov_forget(req: ForgetIn, key=Depends(require_service_key)):
    """Derecho al olvido: borra la memoria del usuario (scope all|memory|sessions|entities|feedback).
    Sensible: requiere confirm=true."""
    AUTH.assert_tenant(key, req.tenant_id)
    AUTH.assert_confirm(req.confirm)
    return await GOV.forget_user(req.tenant_id, req.user_id, req.scope)


@router.post("/governance/audit")
async def gov_audit(req: GovIn, key=Depends(require_service_key)):
    """Registro de escrituras de memoria y acciones de gobernanza (más reciente primero)."""
    AUTH.assert_tenant(key, req.tenant_id)
    return {"governance_version": GOV.GOVERNANCE_VERSION,
            "audit": await GOV.read_audit(req.tenant_id, req.user_id)}
