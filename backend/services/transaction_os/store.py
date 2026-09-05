"""Transaction OS store — entities, event log, state machine runtime, approvals,
data room, memory and Universal Timeline. Event Driven First (DTX13): every mutation
emits an audited event. The OS owns all transactional state (DTX1)."""

import hashlib
from typing import Dict, List, Optional

from database import db
from models import now_iso
from services.transaction_os import workflows as W

OS_VERSION = "transaction-os-v1"
_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    await db.tx_transactions.create_index("transaction_id", unique=True)
    await db.tx_transactions.create_index([("organization_id", 1), ("state", 1)])
    await db.tx_events.create_index([("transaction_id", 1), ("at", 1)])
    await db.tx_events.create_index("event_id", unique=True)
    await db.tx_tasks.create_index("transaction_id")
    await db.tx_approvals.create_index("transaction_id")
    await db.tx_documents.create_index([("transaction_id", 1), ("doc_key", 1)])
    _INDEXED = True


def _tid(thesis_id: str, target: str, wf_version: str) -> str:
    return "txn_" + hashlib.sha256(f"{thesis_id}|{target}|{wf_version}".encode()).hexdigest()[:12]


async def emit(transaction_id: str, etype: str, actor: str, payload: Optional[Dict] = None) -> Dict:
    """Append-only audited event (DTX13). Source of truth for state & timeline."""
    now = now_iso()
    ev = {"event_id": f"evt_{hashlib.sha256(f'{transaction_id}{etype}{now}{actor}'.encode()).hexdigest()[:12]}",
          "transaction_id": transaction_id, "type": etype, "actor": actor,
          "payload": payload or {}, "at": now}
    await db.tx_events.insert_one(dict(ev))
    return ev


# ── Transaction lifecycle ──
async def create_transaction(thesis_id: str, target_master_id: str, workflow_name: str,
                             organization_id: str, parties: List[Dict], actor: str = "platform",
                             visibility: str = "organization") -> Dict:
    await ensure_indexes()
    tmpl = W.template(workflow_name)
    if not tmpl:
        raise ValueError(f"unknown workflow template: {workflow_name}")
    tid = _tid(thesis_id, target_master_id, tmpl["version"])
    existing = await db.tx_transactions.find_one({"transaction_id": tid}, {"_id": 0})
    if existing:
        return existing
    now = now_iso()
    stages = [{"stage": s, "state": ("active" if i == 0 else "pending"),
               "milestones": [], "entered_at": now if i == 0 else None}
              for i, s in enumerate(tmpl["stages"])]
    doc = {
        "transaction_id": tid, "organization_id": organization_id, "visibility": visibility,
        "from_thesis": thesis_id, "target_master_id": target_master_id,
        "parties": parties, "workflow_version": tmpl["version"],
        "state_machine_version": W.STATE_MACHINE_VERSION, "os_version": OS_VERSION,
        "state": "draft", "current_stage": tmpl["stages"][0], "stages": stages,
        "created_at": now, "updated_at": now,
    }
    await db.tx_transactions.insert_one(dict(doc))
    await emit(tid, "transaction_created", actor, {"from_thesis": thesis_id, "workflow": tmpl["version"]})
    # auto: thesis instantiated → sourcing
    await apply_event(tid, "thesis_instantiated", actor)
    return await get_transaction(tid)


async def get_transaction(transaction_id: str) -> Optional[Dict]:
    return await db.tx_transactions.find_one({"transaction_id": transaction_id}, {"_id": 0})


async def find_active_transaction_for_target(target_master_id: str,
                                              organization_id: Optional[str] = None) -> Optional[Dict]:
    """Company (+org) -> most relevant transaction, for the ficha's deal aside
    (columna derecha, "próxima acción"). Prefers the most recently updated
    NON-terminal transaction (an open deal); falls back to the most recent
    terminal one so a closed deal still explains itself instead of the UI
    just going blank. Returns None when the company has no transaction at all
    (by far the common case today — most companies have none)."""
    q: Dict = {"target_master_id": target_master_id}
    if organization_id:
        q["organization_id"] = organization_id
    txns = await db.tx_transactions.find(q, {"_id": 0}).sort("updated_at", -1).to_list(20)
    if not txns:
        return None
    active = [t for t in txns if t["state"] not in W.TERMINAL_STATES]
    return active[0] if active else txns[0]


def party_role(txn: Dict, user_id: Optional[str]) -> Optional[str]:
    """Best-effort: this user's role among the transaction's `parties`.

    NOTE (flag for Intel): `parties` has no fixed shape anywhere in this
    codebase today — it is never asserted on in any test, and every existing
    caller only ever writes it through verbatim (`create_transaction`,
    `create_from_thesis(..., parties, ...)`). This assumes entries shaped
    like `{"user_id": ..., "role": ...}`, with `role` one of the values
    already used in `TRANSITIONS[*]["authorized"]` (buyer/seller/advisor/
    investor/platform). Confirm this against however parties actually get
    populated in production before relying on it — if the real shape differs
    (e.g. `org_id` instead of `user_id`, or roles nested under membership),
    only this function needs to change; nothing else in this module assumes
    a specific shape.
    """
    if not user_id:
        return None
    for p in txn.get("parties") or []:
        if p.get("user_id") == user_id:
            return p.get("role")
    return None


# ── State machine runtime (DTX3) ──
async def _guard_ok(txn: Dict, guard: str) -> bool:
    if guard == "has_thesis":
        return bool(txn.get("from_thesis"))
    if guard == "screening_complete":
        return any(s["stage"] == "screening" and s["state"] == "completed" for s in txn["stages"])
    if guard == "nda_signed":
        return await db.tx_documents.count_documents(
            {"transaction_id": txn["transaction_id"], "doc_type": "nda", "state": "signed"}) > 0
    if guard == "data_room_open":
        return await db.tx_documents.count_documents(
            {"transaction_id": txn["transaction_id"], "doc_type": "data_room"}) > 0
    if guard.startswith("approval:"):
        action = guard.split(":", 1)[1]
        return await db.tx_approvals.count_documents(
            {"transaction_id": txn["transaction_id"], "action": action, "decision": "approved"}) > 0
    return True


async def apply_event(transaction_id: str, event: str, actor: str,
                      actor_role: str = "platform") -> Dict:
    """Validate against the declarative state machine, then transition (DTX3/DTX13)."""
    txn = await get_transaction(transaction_id)
    if not txn:
        raise ValueError("transaction not found")
    tr = W.find_transition(txn["state"], event)
    if not tr:
        return {"applied": False, "reason": f"no transition for '{event}' from '{txn['state']}'",
                "state": txn["state"]}
    if tr["authorized"] and actor_role not in tr["authorized"] and actor != "platform":
        return {"applied": False, "reason": f"role '{actor_role}' not authorized", "state": txn["state"]}
    unmet = [g for g in tr["guards"] if not await _guard_ok(txn, g)]
    if unmet:
        return {"applied": False, "reason": "guards_unmet", "unmet_guards": unmet, "state": txn["state"]}
    await db.tx_transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"state": tr["to"], "updated_at": now_iso()}})
    await emit(transaction_id, event, actor, {"from": tr["from"], "to": tr["to"], "effects": tr["effects"]})
    return {"applied": True, "from": txn["state"], "to": tr["to"], "effects": tr["effects"]}


async def advance_stage(transaction_id: str, stage: str, actor: str = "platform") -> Dict:
    txn = await get_transaction(transaction_id)
    if not txn:
        raise ValueError("transaction not found")
    idx = next((i for i, s in enumerate(txn["stages"]) if s["stage"] == stage), None)
    if idx is None:
        raise ValueError("stage not in workflow")
    stages = txn["stages"]
    stages[idx]["state"] = "completed"
    if idx + 1 < len(stages):
        stages[idx + 1]["state"] = "active"
        stages[idx + 1]["entered_at"] = now_iso()
        new_current = stages[idx + 1]["stage"]
    else:
        new_current = stage
    await db.tx_transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"stages": stages, "current_stage": new_current, "updated_at": now_iso()}})
    await emit(transaction_id, "stage_completed", actor, {"stage": stage, "next": new_current})
    return await get_transaction(transaction_id)


# ── Tasks ──
async def add_task(transaction_id: str, title: str, stage: str, assignee: Optional[str],
                   actor: str = "platform") -> Dict:
    now = now_iso()
    task = {"task_id": f"tsk_{hashlib.sha256(f'{transaction_id}{title}{now}'.encode()).hexdigest()[:12]}",
            "transaction_id": transaction_id, "title": title, "stage": stage,
            "assignee": assignee, "state": "open", "created_at": now}
    await db.tx_tasks.insert_one(dict(task))
    await emit(transaction_id, "task_created", actor, {"task_id": task["task_id"], "title": title})
    return task


async def complete_task(task_id: str, actor: str = "platform") -> Optional[Dict]:
    t = await db.tx_tasks.find_one({"task_id": task_id}, {"_id": 0})
    if not t:
        return None
    await db.tx_tasks.update_one({"task_id": task_id}, {"$set": {"state": "completed", "completed_at": now_iso()}})
    await emit(t["transaction_id"], "task_completed", actor, {"task_id": task_id})
    return await db.tx_tasks.find_one({"task_id": task_id}, {"_id": 0})


async def list_tasks(transaction_id: str) -> List[Dict]:
    return await db.tx_tasks.find({"transaction_id": transaction_id}, {"_id": 0}).to_list(500)


# ── Approvals (DTX5) ──
async def request_approval(transaction_id: str, action: str, requested_by: str) -> Dict:
    now = now_iso()
    ap = {"approval_id": f"apr_{hashlib.sha256(f'{transaction_id}{action}{now}'.encode()).hexdigest()[:12]}",
          "transaction_id": transaction_id, "action": action, "requested_by": requested_by,
          "decision": "pending", "high_risk": action in W.HIGH_RISK_ACTIONS, "created_at": now}
    await db.tx_approvals.insert_one(dict(ap))
    await emit(transaction_id, "approval_requested", requested_by, {"action": action})
    return ap


async def decide_approval(approval_id: str, decision: str, actor: str, actor_role: str,
                          artifact_version: Optional[str] = None,
                          evidence_reviewed: Optional[List[str]] = None) -> Optional[Dict]:
    ap = await db.tx_approvals.find_one({"approval_id": approval_id}, {"_id": 0})
    if not ap:
        return None
    now = now_iso()
    await db.tx_approvals.update_one(
        {"approval_id": approval_id},
        {"$set": {"decision": decision, "actor": actor, "role": actor_role,
                  "artifact_version": artifact_version, "evidence_reviewed": evidence_reviewed or [],
                  "decided_at": now}})
    await emit(ap["transaction_id"], "approval_decided", actor,
               {"action": ap["action"], "decision": decision, "role": actor_role})
    return await db.tx_approvals.find_one({"approval_id": approval_id}, {"_id": 0})


async def list_approvals(transaction_id: str) -> List[Dict]:
    return await db.tx_approvals.find({"transaction_id": transaction_id}, {"_id": 0}).to_list(500)


# ── Data Room & documents (DTX6) ──
async def add_document(transaction_id: str, doc_key: str, doc_type: str, content_hash: str,
                       permissions: List[str], actor: str = "platform",
                       state: str = "drafted") -> Dict:
    prev = await db.tx_documents.find({"transaction_id": transaction_id, "doc_key": doc_key},
                                      {"_id": 0, "version": 1}).sort("version", -1).to_list(1)
    version = (prev[0]["version"] + 1) if prev else 1
    now = now_iso()
    doc = {"document_id": f"doc_{hashlib.sha256(f'{transaction_id}{doc_key}{version}'.encode()).hexdigest()[:12]}",
           "transaction_id": transaction_id, "doc_key": doc_key, "doc_type": doc_type,
           "version": version, "content_hash": content_hash, "permissions": permissions,
           "state": state, "created_at": now}
    await db.tx_documents.insert_one(dict(doc))
    await emit(transaction_id, "document_added", actor,
               {"doc_key": doc_key, "doc_type": doc_type, "version": version})
    return doc


async def set_document_state(document_id: str, state: str, actor: str = "platform") -> Optional[Dict]:
    d = await db.tx_documents.find_one({"document_id": document_id}, {"_id": 0})
    if not d:
        return None
    await db.tx_documents.update_one({"document_id": document_id}, {"$set": {"state": state}})
    await emit(d["transaction_id"], "document_state_changed", actor,
               {"document_id": document_id, "state": state})
    return await db.tx_documents.find_one({"document_id": document_id}, {"_id": 0})


async def record_access(transaction_id: str, document_id: str, actor: str, role: str) -> Dict:
    return await emit(transaction_id, "document_accessed", actor,
                      {"document_id": document_id, "role": role})


async def list_documents(transaction_id: str) -> List[Dict]:
    return await db.tx_documents.find({"transaction_id": transaction_id}, {"_id": 0}).to_list(1000)


# ── Universal Timeline (DTX11) + Transaction Memory ──
async def timeline(transaction_id: str) -> List[Dict]:
    return await db.tx_events.find({"transaction_id": transaction_id}, {"_id": 0}).sort("at", 1).to_list(5000)


async def memory(transaction_id: str) -> Dict:
    evs = await timeline(transaction_id)
    return {"transaction_id": transaction_id,
            "decisions": [e for e in evs if e["type"] in ("approval_decided", "stage_completed")],
            "documents": await list_documents(transaction_id),
            "tasks": await list_tasks(transaction_id),
            "approvals": await list_approvals(transaction_id),
            "domain_events": [e for e in evs if e["type"] in W.DOMAIN_EVENTS],
            "event_count": len(evs)}
