"""Transaction Intelligence Engine API — public contract (transaction-intelligence-v1).

Top of the Intelligence Layer DAG; orchestrator of the whole system. Owns NO transactional
state: all state lives in the Transaction OS (DTX1). Every mutation is an audited event
(DTX13). UI-agnostic, service-key auth. Exposes the 12 endpoints of the frozen contract §8.
"""
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.transaction_os import store as OS
from services.transaction_os import workflows as W
from services.engines.transaction import engine as TX
from services.engines.signal import actions as sig_actions
from services.service_auth import require_service_key
from routes import engine_schemas as S

router = APIRouter(prefix="/api/v1/transaction-intelligence", tags=["transaction_intelligence"])


def _ok(model):
    return {200: {"model": model, "description": "Successful Response"}}


# ── Request models ──
class TransactionRequest(BaseModel):
    transaction_id: Optional[str] = None         # query mode
    thesis_id: Optional[str] = None              # create mode (from_thesis)
    workflow_name: Optional[str] = None
    organization_id: str = "org_default"
    parties: Optional[List[Dict]] = None
    actor: str = "platform"


class WorkflowRequest(BaseModel):
    transaction_id: Optional[str] = None         # instance (stages) for a transaction
    workflow_name: Optional[str] = None          # template lookup


class StageRequest(BaseModel):
    transaction_id: str
    stage: Optional[str] = None                  # advance_stage
    event: Optional[str] = None                  # apply global state-machine event (guards)
    actor: str = "platform"
    actor_role: str = "platform"


class TaskRequest(BaseModel):
    transaction_id: Optional[str] = None
    title: Optional[str] = None
    stage: Optional[str] = None
    assignee: Optional[str] = None
    task_id: Optional[str] = None                # close mode
    action: Optional[str] = None                 # "complete"
    actor: str = "platform"


class TxRef(BaseModel):
    transaction_id: str


class DealAsideRequest(BaseModel):
    """Beta's ficha (`CompanyFichaLayoutV2`, columna derecha) calls this with the
    company being viewed + the logged-in user, and gets back exactly the shape its
    `DealAsideCard` renders (see `lib/companies/deal-aside.ts` adapter en Beta)."""
    target_master_id: str
    user_id: Optional[str] = None
    organization_id: Optional[str] = None


class DocumentRequest(BaseModel):
    transaction_id: str
    doc_key: Optional[str] = None
    doc_type: Optional[str] = None
    content_hash: Optional[str] = "sha256:placeholder"
    permissions: Optional[List[str]] = None
    document_id: Optional[str] = None            # state change mode
    state: Optional[str] = None
    actor: str = "platform"


class DecisionRequest(BaseModel):
    transaction_id: Optional[str] = None
    action: Optional[str] = None                 # request approval
    requested_by: Optional[str] = None
    approval_id: Optional[str] = None            # decide
    decision: Optional[str] = None               # approved|rejected
    actor: str = "platform"
    actor_role: str = "platform"
    artifact_version: Optional[str] = None
    evidence_reviewed: Optional[List[str]] = None


async def _txn_or_404(transaction_id: str) -> Dict:
    txn = await OS.get_transaction(transaction_id)
    if not txn:
        raise HTTPException(404, "transaction not found")
    return txn


@router.post("/transaction", responses=_ok(S.TransactionEndpointResponse))
async def transaction(req: TransactionRequest, _key=Depends(require_service_key)):
    if req.transaction_id:
        return await _txn_or_404(req.transaction_id)
    if not (req.thesis_id and req.workflow_name):
        raise HTTPException(400, "provide transaction_id (query) or thesis_id+workflow_name (create)")
    res = await TX.create_from_thesis(req.thesis_id, req.workflow_name, req.organization_id,
                                      req.parties, req.actor)
    if res is None:
        raise HTTPException(404, "thesis not found in Strategy Memory")
    return res


@router.post("/workflow", responses=_ok(S.WorkflowResponse))
async def workflow(req: WorkflowRequest, _key=Depends(require_service_key)):
    if req.transaction_id:
        txn = await _txn_or_404(req.transaction_id)
        return {"transaction_id": txn["transaction_id"], "workflow_version": txn["workflow_version"],
                "state_machine_version": txn["state_machine_version"], "stages": txn["stages"],
                "current_stage": txn["current_stage"]}
    tmpl = W.template(req.workflow_name) if req.workflow_name else None
    if not tmpl:
        raise HTTPException(404, "unknown workflow template")
    return tmpl


@router.post("/stage", responses=_ok(S.StageResponse))
async def stage(req: StageRequest, _key=Depends(require_service_key)):
    await _txn_or_404(req.transaction_id)
    if req.event:
        return await OS.apply_event(req.transaction_id, req.event, req.actor, req.actor_role)
    if req.stage:
        try:
            return await OS.advance_stage(req.transaction_id, req.stage, req.actor)
        except ValueError as e:
            raise HTTPException(400, str(e))
    txn = await OS.get_transaction(req.transaction_id)
    return {"current_stage": txn["current_stage"], "stages": txn["stages"], "state": txn["state"]}


@router.post("/task", responses=_ok(S.TaskResponse))
async def task(req: TaskRequest, _key=Depends(require_service_key)):
    if req.action == "complete" and req.task_id:
        t = await OS.complete_task(req.task_id, req.actor)
        if not t:
            raise HTTPException(404, "task not found")
        return t
    if req.transaction_id and req.title:
        await _txn_or_404(req.transaction_id)
        return await OS.add_task(req.transaction_id, req.title, req.stage or "origination",
                                 req.assignee, req.actor)
    if req.transaction_id:
        return {"tasks": await OS.list_tasks(req.transaction_id)}
    raise HTTPException(400, "provide transaction_id (+title to create / alone to list) or task_id+action=complete")


@router.post("/next-action", responses=_ok(S.NextActionResponse))
async def next_action(req: TxRef, _key=Depends(require_service_key)):
    res = await TX.next_action(req.transaction_id)
    if res is None:
        raise HTTPException(404, "transaction not found")
    return res


@router.post("/risk", responses=_ok(S.TransactionRiskResponse))
async def risk(req: TxRef, _key=Depends(require_service_key)):
    res = await TX.risk(req.transaction_id)
    if res is None:
        raise HTTPException(404, "transaction not found")
    return res


@router.post("/documents", responses=_ok(S.DocumentsResponse))
async def documents(req: DocumentRequest, _key=Depends(require_service_key)):
    await _txn_or_404(req.transaction_id)
    if req.document_id and req.state:
        d = await OS.set_document_state(req.document_id, req.state, req.actor)
        if not d:
            raise HTTPException(404, "document not found")
        return d
    if req.doc_key and req.doc_type:
        return await OS.add_document(req.transaction_id, req.doc_key, req.doc_type,
                                     req.content_hash, req.permissions or ["advisor"],
                                     actor=req.actor, state=req.state or "drafted")
    return {"documents": await OS.list_documents(req.transaction_id)}


@router.post("/participants", responses=_ok(S.ParticipantsResponse))
async def participants(req: TxRef, _key=Depends(require_service_key)):
    txn = await _txn_or_404(req.transaction_id)
    return {"transaction_id": req.transaction_id, "participants": txn.get("parties", []),
            "roles": ["buyer", "seller", "advisor", "investor", "lawyer", "auditor",
                      "administrator", "platform"]}


@router.post("/timeline", responses=_ok(S.TimelineResponse))
async def timeline(req: TxRef, _key=Depends(require_service_key)):
    await _txn_or_404(req.transaction_id)
    evs = await OS.timeline(req.transaction_id)
    return {"transaction_id": req.transaction_id, "events": evs, "count": len(evs)}


@router.post("/decision", responses=_ok(S.TransactionDecisionResponse))
async def decision(req: DecisionRequest, _key=Depends(require_service_key)):
    if req.approval_id and req.decision:
        ap = await OS.decide_approval(req.approval_id, req.decision, req.actor, req.actor_role,
                                      req.artifact_version, req.evidence_reviewed)
        if not ap:
            raise HTTPException(404, "approval not found")
        return ap
    if req.transaction_id and req.action and req.requested_by:
        await _txn_or_404(req.transaction_id)
        return await OS.request_approval(req.transaction_id, req.action, req.requested_by)
    if req.transaction_id:
        return {"approvals": await OS.list_approvals(req.transaction_id)}
    raise HTTPException(400, "provide approval_id+decision, or transaction_id(+action+requested_by)")


@router.post("/memory", responses=_ok(S.TransactionMemoryResponse))
async def memory(req: TxRef, _key=Depends(require_service_key)):
    await _txn_or_404(req.transaction_id)
    return await OS.memory(req.transaction_id)


@router.post("/workspace", responses=_ok(S.WorkspaceResponse))
async def workspace(req: TxRef, _key=Depends(require_service_key)):
    """DTX12 Transaction Workspace aggregate (+ DTX11 Universal Timeline)."""
    res = await TX.workspace(req.transaction_id)
    if res is None:
        raise HTTPException(404, "transaction not found")
    return res


@router.post("/deal-aside", responses=_ok(S.DealAsideResponse))
async def deal_aside(req: DealAsideRequest, _key=Depends(require_service_key)):
    return await TX.deal_aside_view(req.target_master_id, req.user_id, req.organization_id)


@router.get("/catalog", responses=_ok(S.TransactionCatalogResponse))
async def catalog(_key=Depends(require_service_key)):
    return {
        "engine_version": TX.ENGINE_VERSION,
        "os_version": OS.OS_VERSION,
        "state_machine_version": W.STATE_MACHINE_VERSION,
        "workflow_templates": list(W.WORKFLOW_TEMPLATES.keys()),
        "stages_v1": W.STAGES_V1,
        "stages_deferred": W.STAGES_DEFERRED,
        "global_states": W.GLOBAL_STATES,
        "terminal_states": W.TERMINAL_STATES,
        "high_risk_actions": W.HIGH_RISK_ACTIONS,
        "domain_events": W.DOMAIN_EVENTS,
        "transitions": W.TRANSITIONS,
        "canonical_actions": sig_actions.CANONICAL_ACTIONS,
        "evidence_version": TX.EVIDENCE_VERSION,
        "action_types": ["next_action", "blocker", "reminder", "prepare_document",
                         "request_info", "risk_warning"],
        "canonical_entities": "tx_transactions / tx_events / tx_tasks / tx_approvals / tx_documents",
    }
