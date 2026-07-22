"""Smoke tests — Sprint 7 Transaction OS & Transaction Intelligence Engine.

Validates frozen contract transaction-intelligence-v1 (DTX1..DTX13):
- Engine owns NO state; all state in the Transaction OS (DTX1).
- Declarative, versioned state machine with guards; no implicit transitions (DTX3).
- Every mutation emits an audited append-only event (Event Driven First, DTX13).
- Universal Timeline (DTX11) + Transaction Workspace aggregate (DTX12).
- Multifactor transactional confidence (DTX7) + mandatory explainability (§7).
- Approvals gate high-risk actions (DTX5). Decoupled service API (§8).
"""
import os
import subprocess
import requests
import pytest
from smoke_loop import run_async as _run

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"
TI = "/api/v1/transaction-intelligence"
SVC = {"X-API-Key": os.environ.get("ARROBA_SERVICE_API_KEY",
                                   "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk")}

pytestmark = pytest.mark.skipif(
    not os.path.isdir(SAMPLE_DIR), reason="Iberinform sample fixture not present")


def __base():
    return os.environ.get("BASE_URL", "http://localhost:8001")


@pytest.fixture(scope="module", autouse=True)
def _setup():
    subprocess.run(["sudo", "supervisorctl", "stop", "data_layer_worker"], capture_output=True)

    async def go():
        from database import db
        from services.data_layer.ingestion.iberinform_ingest import ingest_directory
        from services.data_layer.master.master_builder import rebuild_master
        from services.engines.strategy import memory as MEM
        from services.engines.semantic import persistence as SP
        from services.transaction_os import store as OS
        if await db.master_companies.count_documents({"financials.latest.revenue": {"$ne": None}}) < 50:
            await ingest_directory(SAMPLE_DIR, source_version="20260519")
            await rebuild_master(scope="full")
        await MEM.ensure_indexes()
        await SP.ensure_indexes()
        await OS.ensure_indexes()
        # test isolation: deterministic transaction_id means prior runs would
        # otherwise resurrect closed transactions — clear the OS collections.
        for c in ("tx_transactions", "tx_events", "tx_tasks", "tx_approvals", "tx_documents"):
            await db[c].delete_many({})
    _run(go())
    yield
    subprocess.run(["sudo", "supervisorctl", "start", "data_layer_worker"], capture_output=True)


def _seed_thesis():
    """Seed a canonical Strategic Thesis (DT15) and return its id + target master_id."""
    async def go():
        from database import db
        from services.engines.strategy.engine import thesis
        d = await db.master_companies.find_one(
            {"financials.latest.revenue": {"$ne": None}}, {"_id": 0, "master_id": 1})
        t = await thesis(d["master_id"])
        return t["thesis_id"], t["company_master_id"]
    return _run(go())


# ── Engine ↔ OS boundary (DTX1) ──
def test_engine_owns_no_state():
    """The engine module must not declare any persistence collection (state lives in OS)."""
    import inspect
    from services.engines.transaction import engine as TX
    src = inspect.getsource(TX)
    # engine never writes directly to db; it delegates to the OS store
    assert "db." not in src, "engine must not touch the DB directly (DTX1)"
    assert "OS." in src and "from services.transaction_os import store" in src


def test_create_from_thesis_event_driven():
    tid, _ = _seed_thesis()
    r = requests.post(f"{__base()}{TI}/transaction", headers=SVC,
                      json={"thesis_id": tid, "workflow_name": "buy_side_v1"}, timeout=60)
    assert r.status_code == 200, r.text
    txn = r.json()["transaction"]
    # auto thesis_instantiated transition: draft -> sourcing (DTX3 declarative)
    assert txn["state"] == "sourcing"
    assert txn["workflow_version"] == "buy_side_v1"
    assert txn["state_machine_version"] == "state-machine-v1"
    transaction_id = txn["transaction_id"]
    # DTX13: creation + transition emitted events
    tl = requests.post(f"{__base()}{TI}/timeline", headers=SVC,
                       json={"transaction_id": transaction_id}, timeout=30).json()
    types = [e["type"] for e in tl["events"]]
    assert "transaction_created" in types and "thesis_instantiated" in types
    assert tl["count"] >= 2


def test_transaction_id_deterministic():
    tid, _ = _seed_thesis()
    a = requests.post(f"{__base()}{TI}/transaction", headers=SVC,
                      json={"thesis_id": tid, "workflow_name": "buy_side_v1"}, timeout=60).json()
    b = requests.post(f"{__base()}{TI}/transaction", headers=SVC,
                      json={"thesis_id": tid, "workflow_name": "buy_side_v1"}, timeout=60).json()
    assert a["transaction"]["transaction_id"] == b["transaction"]["transaction_id"]


def _new_txn():
    tid, _ = _seed_thesis()
    r = requests.post(f"{__base()}{TI}/transaction", headers=SVC,
                      json={"thesis_id": tid, "workflow_name": "buy_side_v1"}, timeout=60).json()
    return r["transaction"]["transaction_id"]


def test_next_action_explainability_and_confidence():
    txn = _new_txn()
    r = requests.post(f"{__base()}{TI}/next-action", headers=SVC,
                      json={"transaction_id": txn}, timeout=60)
    assert r.status_code == 200, r.text
    a = r.json()
    # §7 mandatory explainability
    exp = a["explainability"]
    assert set(exp.keys()) >= {"why_proposed", "intelligence_support", "risks_avoided",
                               "if_not_executed", "dependencies"}
    assert exp["intelligence_support"]
    # DTX7 multifactor confidence (7 factors)
    assert set(a["confidence"]["factors"].keys()) == {
        "evidence_quality", "document_completeness", "approvals_state", "risk",
        "urgency", "critical_dependency", "thesis_consistency"}
    assert 0 <= a["confidence"]["value"] <= 1
    assert a["transaction_version"] == "transaction-intelligence-v1"
    assert "transaction_os" in a["evidence_version"]
    # recommended_actions are from the canonical Signal enum (no free text)
    from services.engines.signal.actions import CANONICAL_ACTIONS
    assert all(x in CANONICAL_ACTIONS for x in a["recommended_actions"])


def test_no_implicit_transition_guarded_by_state_machine():
    """DTX3: an event with no valid transition from current state is rejected (no implicit jump)."""
    txn = _new_txn()  # state = sourcing
    r = requests.post(f"{__base()}{TI}/stage", headers=SVC,
                      json={"transaction_id": txn, "event": "advance_to_due_diligence",
                            "actor_role": "advisor"}, timeout=30).json()
    assert r["applied"] is False
    assert r["state"] == "sourcing"


def test_guards_block_then_full_lifecycle_to_closed_won():
    txn = _new_txn()  # sourcing
    base = f"{__base()}{TI}"
    # complete origination → qualification → screening so screening_complete guard passes
    for st in ("origination", "qualification", "screening"):
        requests.post(f"{base}/stage", headers=SVC,
                      json={"transaction_id": txn, "stage": st, "actor": "advisor"}, timeout=30)
    # sourcing -> engaged (guard: screening_complete)
    eng = requests.post(f"{base}/stage", headers=SVC,
                        json={"transaction_id": txn, "event": "buyer_contacted",
                              "actor_role": "advisor"}, timeout=30).json()
    assert eng["applied"] is True and eng["to"] == "engaged"
    # try advance_to_due_diligence before NDA/data_room/approval → guards_unmet
    blocked = requests.post(f"{base}/stage", headers=SVC,
                            json={"transaction_id": txn, "event": "advance_to_due_diligence",
                                  "actor_role": "advisor"}, timeout=30).json()
    assert blocked["applied"] is False and blocked["reason"] == "guards_unmet"
    assert set(["nda_signed", "data_room_open"]).issubset(set(blocked["unmet_guards"])) or \
        "approval:advance_to_due_diligence" in blocked["unmet_guards"]
    # satisfy guards: NDA signed + data room open + approval
    nda = requests.post(f"{base}/documents", headers=SVC,
                        json={"transaction_id": txn, "doc_key": "nda", "doc_type": "nda"}, timeout=30).json()
    requests.post(f"{base}/documents", headers=SVC,
                  json={"transaction_id": txn, "document_id": nda["document_id"], "state": "signed"}, timeout=30)
    requests.post(f"{base}/documents", headers=SVC,
                  json={"transaction_id": txn, "doc_key": "dataroom", "doc_type": "data_room"}, timeout=30)
    ap = requests.post(f"{base}/decision", headers=SVC,
                       json={"transaction_id": txn, "action": "advance_to_due_diligence",
                             "requested_by": "advisor"}, timeout=30).json()
    assert ap["high_risk"] is True and ap["decision"] == "pending"
    requests.post(f"{base}/decision", headers=SVC,
                  json={"approval_id": ap["approval_id"], "decision": "approved",
                        "actor": "partner", "actor_role": "advisor",
                        "evidence_reviewed": ["nda", "valuation"]}, timeout=30)
    # now engaged -> diligence
    dil = requests.post(f"{base}/stage", headers=SVC,
                        json={"transaction_id": txn, "event": "advance_to_due_diligence",
                              "actor_role": "advisor"}, timeout=30).json()
    assert dil["applied"] is True and dil["to"] == "diligence"
    # close
    capr = requests.post(f"{base}/decision", headers=SVC,
                         json={"transaction_id": txn, "action": "close_deal",
                               "requested_by": "advisor"}, timeout=30).json()
    requests.post(f"{base}/decision", headers=SVC,
                  json={"approval_id": capr["approval_id"], "decision": "approved",
                        "actor": "partner", "actor_role": "advisor"}, timeout=30)
    won = requests.post(f"{base}/stage", headers=SVC,
                        json={"transaction_id": txn, "event": "deal_closed",
                              "actor_role": "advisor"}, timeout=30).json()
    assert won["applied"] is True and won["to"] == "closed_won"


def test_tasks_and_memory():
    txn = _new_txn()
    base = f"{__base()}{TI}"
    t = requests.post(f"{base}/task", headers=SVC,
                      json={"transaction_id": txn, "title": "Prepare teaser",
                            "stage": "origination", "assignee": "analyst"}, timeout=30).json()
    assert t["state"] == "open"
    done = requests.post(f"{base}/task", headers=SVC,
                         json={"task_id": t["task_id"], "action": "complete"}, timeout=30).json()
    assert done["state"] == "completed"
    mem = requests.post(f"{base}/memory", headers=SVC,
                        json={"transaction_id": txn}, timeout=30).json()
    assert mem["event_count"] > 0 and any(x["task_id"] == t["task_id"] for x in mem["tasks"])


def test_workspace_aggregate_dtx12():
    txn = _new_txn()
    r = requests.post(f"{__base()}{TI}/workspace", headers=SVC,
                      json={"transaction_id": txn}, timeout=60)
    assert r.status_code == 200, r.text
    ws = r.json()
    for k in ("transaction", "stages", "current_stage", "tasks", "approvals",
              "documents", "participants", "timeline", "next_action"):
        assert k in ws, f"workspace missing {k}"
    assert ws["os_version"] == "transaction-os-v1"


def test_risk_reuses_signal_by_reference():
    txn = _new_txn()
    r = requests.post(f"{__base()}{TI}/risk", headers=SVC,
                      json={"transaction_id": txn}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "risks" in body and "blockers" in body
    assert body["engine_version"] == "transaction-intelligence-v1"


# ── API contract ──
def test_api_requires_service_key():
    r = requests.post(f"{__base()}{TI}/transaction", json={"transaction_id": "x"}, timeout=20)
    assert r.status_code == 401


def test_not_found_404():
    r = requests.post(f"{__base()}{TI}/next-action", headers=SVC,
                      json={"transaction_id": "txn_doesnotexist"}, timeout=20)
    assert r.status_code == 404


def test_catalog():
    cat = requests.get(f"{__base()}{TI}/catalog", headers=SVC, timeout=20).json()
    assert cat["engine_version"] == "transaction-intelligence-v1"
    assert cat["os_version"] == "transaction-os-v1"
    assert set(["buy_side_v1", "sell_side_v1", "capital_raise_v1", "partnership_v1"]).issubset(
        set(cat["workflow_templates"]))
    assert len(cat["stages_v1"]) == 8
    assert "advance_to_due_diligence" in cat["high_risk_actions"]
    assert cat["transitions"]
    from services.engines.signal.actions import CANONICAL_ACTIONS
    assert cat["canonical_actions"] == CANONICAL_ACTIONS
