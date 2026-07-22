"""Transaction Intelligence Engine — orchestrator (transaction-intelligence-v1).

Owns orchestration / next-best-action / blocker detection / explanation / prioritization
/ artifact preparation (DTX1). Does NOT duplicate transactional state (delegates to the
Transaction OS). Reuses all Intelligence Engines by reference. Copilot is an orchestrator,
not a chat; AI never mutates state or approves (DTX4). Explainability First.
"""
from typing import Dict, List, Optional

from models import now_iso
from services.transaction_os import store as OS
from services.transaction_os import workflows as W
from services.engines.strategy import memory as strat_mem
from services.engines.financial import engine as fin_engine
from services.engines.signal import engine as sig_engine

ENGINE_VERSION = "transaction-intelligence-v1"
EVIDENCE_VERSION = {"master": "master-v1", "financial": "financial-intelligence-v1",
                    "signal": "signal-intelligence-v1", "semantic": "semantic-intelligence-v1",
                    "recommendation": "recommendation-intelligence-v1",
                    "strategy": "strategy-intelligence-v1", "transaction_os": OS.OS_VERSION}

# stage → suggested high-risk action + supporting intelligence
_STAGE_PLAYBOOK = {
    "origination": ("qualify_target", ["strategy-intelligence-v1"]),
    "qualification": ("screen_candidates", ["semantic-intelligence-v1", "financial-intelligence-v1"]),
    "screening": ("initiate_outreach", ["recommendation-intelligence-v1"]),
    "outreach": ("send_nda", ["recommendation-intelligence-v1"]),
    "nda": ("open_data_room", ["signal-intelligence-v1"]),
    "data_room": ("perform_valuation", ["financial-intelligence-v1"]),
    "valuation": ("advance_to_due_diligence", ["financial-intelligence-v1", "strategy-intelligence-v1"]),
    "due_diligence_initial": ("complete_initial_dd", ["financial-intelligence-v1", "signal-intelligence-v1"]),
}


def _clamp(x):
    try:
        return round(max(0.0, min(1.0, float(x))), 4)
    except Exception:
        return 0.0


async def create_from_thesis(thesis_id: str, workflow_name: str, organization_id: str,
                             parties: Optional[List[Dict]] = None, actor: str = "platform") -> Optional[Dict]:
    theses = await strat_mem.query(thesis_id=thesis_id)
    if not theses:
        return None
    th = theses[0]
    txn = await OS.create_transaction(thesis_id, th["company_master_id"], workflow_name,
                                      organization_id, parties or [], actor)
    return {"transaction": txn, "from_thesis": thesis_id,
            "engine_version": ENGINE_VERSION, "generated_at": now_iso()}


async def _blockers(txn: Dict) -> List[Dict]:
    out = []
    open_tasks = [t for t in await OS.list_tasks(txn["transaction_id"]) if t["state"] == "open"]
    if open_tasks:
        out.append({"type": "open_tasks", "count": len(open_tasks)})
    pending = [a for a in await OS.list_approvals(txn["transaction_id"]) if a["decision"] == "pending"]
    if pending:
        out.append({"type": "pending_approvals", "actions": [a["action"] for a in pending]})
    return out


async def next_action(transaction_id: str) -> Optional[Dict]:
    txn = await OS.get_transaction(transaction_id)
    if not txn:
        return None
    stage = txn["current_stage"]
    action, support = _STAGE_PLAYBOOK.get(stage, ("review", ["strategy-intelligence-v1"]))
    high_risk = action in W.HIGH_RISK_ACTIONS
    blockers = await _blockers(txn)

    # supporting intelligence (reused by reference)
    evidence_refs = {"thesis_id": txn["from_thesis"]}
    risks_avoided, why = [], f"En la fase '{stage}', la acción óptima es '{action}'."
    if stage in ("valuation",):
        fin = await fin_engine.analyze(txn["target_master_id"])
        if fin and fin.get("valuation"):
            evidence_refs["valuation"] = fin["valuation"].get("method")
            why += " Soportada por la valoración del Financial Engine."
    if stage in ("data_room", "due_diligence_initial"):
        try:
            sig = await sig_engine.analyze(txn["target_master_id"], persist=False)
            risk_sigs = [s["signal_type"] for s in (sig or {}).get("signals", []) if s.get("polarity") == "negative"]
            evidence_refs["signal_ids"] = [s["signal_id"] for s in (sig or {}).get("signals", [])][:5]
            risks_avoided = risk_sigs[:3]
        except Exception:
            pass

    # multifactor confidence (DTX7)
    docs = await OS.list_documents(transaction_id)
    approvals = await OS.list_approvals(transaction_id)
    factors = {
        "evidence_quality": _clamp(0.7 if evidence_refs.get("valuation") or evidence_refs.get("signal_ids") else 0.5),
        "document_completeness": _clamp(min(1.0, len(docs) / 3)),
        "approvals_state": _clamp(1.0 if not [a for a in approvals if a["decision"] == "pending"] else 0.5),
        "risk": _clamp(1 - 0.2 * len(risks_avoided)),
        "urgency": _clamp(0.6),
        "critical_dependency": _clamp(0.4 if blockers else 0.9),
        "thesis_consistency": _clamp(0.8),
    }
    confidence = {"value": round(sum(factors.values()) / len(factors), 4), "factors": factors}

    return {
        "action_id": f"act_{transaction_id[-8:]}_{stage}",
        "transaction_id": transaction_id, "stage": stage,
        "action_type": "blocker" if blockers else "next_action",
        "title": action.replace("_", " ").title(),
        "description": f"Acción recomendada en {stage}: {action}.",
        "high_risk": high_risk, "requires_approval": high_risk,
        "blockers": blockers,
        "explainability": {
            "why_proposed": why,
            "intelligence_support": support,
            "risks_avoided": risks_avoided,
            "if_not_executed": "La operación queda bloqueada en esta fase y pierde momentum/timing.",
            "dependencies": [f"stage:{stage}"] + ([f"approval:{action}"] if high_risk else []),
        },
        "evidence_refs": evidence_refs,
        "recommended_actions": ["analyze", "request_due_diligence"] if stage.startswith("due") else ["analyze", "contact"],
        "confidence": confidence,
        "transaction_version": ENGINE_VERSION, "workflow_version": txn["workflow_version"],
        "engines_used": list(EVIDENCE_VERSION.keys()), "evidence_version": EVIDENCE_VERSION,
        "generated_at": now_iso(),
    }


async def risk(transaction_id: str) -> Optional[Dict]:
    txn = await OS.get_transaction(transaction_id)
    if not txn:
        return None
    risks = []
    try:
        sig = await sig_engine.analyze(txn["target_master_id"], persist=False)
        for s in (sig or {}).get("signals", []):
            if s.get("polarity") == "negative":
                risks.append({"signal_id": s["signal_id"], "signal_type": s["signal_type"],
                              "severity": s.get("severity"), "explanation": s.get("explanation")})
    except Exception:
        pass
    blockers = await _blockers(txn)
    return {"transaction_id": transaction_id, "stage": txn["current_stage"],
            "risks": risks[:10], "blockers": blockers,
            "engine_version": ENGINE_VERSION, "evidence_version": EVIDENCE_VERSION,
            "generated_at": now_iso()}


async def prepare_document(transaction_id: str, doc_type: str, actor: str = "platform") -> Optional[Dict]:
    """Copilot prepares a DRAFT artifact (DTX4: AI may draft; never signs/approves)."""
    txn = await OS.get_transaction(transaction_id)
    if not txn:
        return None
    content_hash = "sha256:draft-placeholder"
    permissions = ["advisor", "buyer", "seller"]
    doc = await OS.add_document(transaction_id, doc_type, doc_type, content_hash, permissions,
                                actor=actor, state="drafted")
    return {"prepared": True, "document": doc, "note": "draft only; requires human approval/signature",
            "engine_version": ENGINE_VERSION}


async def workspace(transaction_id: str) -> Optional[Dict]:
    """Transaction Workspace domain model (DTX12) + Universal Timeline (DTX11)."""
    txn = await OS.get_transaction(transaction_id)
    if not txn:
        return None
    return {
        "transaction": txn,
        "stages": txn["stages"], "current_stage": txn["current_stage"],
        "tasks": await OS.list_tasks(transaction_id),
        "approvals": await OS.list_approvals(transaction_id),
        "documents": await OS.list_documents(transaction_id),
        "participants": txn.get("parties", []),
        "timeline": await OS.timeline(transaction_id),
        "next_action": await next_action(transaction_id),
        "engine_version": ENGINE_VERSION, "os_version": OS.OS_VERSION, "generated_at": now_iso(),
    }
