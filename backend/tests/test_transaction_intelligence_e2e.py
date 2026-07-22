"""Independent E2E backend validation for Sprint 7 — Transaction Intelligence Engine
+ Transaction OS (FROZEN contract transaction-intelligence-v1 / transaction-os-v1).

Covers all features listed in the review request:
  - Service-key auth (401 without X-API-Key, 200 with).
  - GET /catalog completeness (engine_version, os_version, 4 workflows, 8 v1 stages,
    high_risk_actions, transitions, canonical_actions == Signal enum).
  - POST /transaction deterministic id; auto draft -> sourcing transition.
  - POST /next-action mandatory explainability + 7-factor confidence; canonical actions.
  - DTX3 no implicit transition (event rejected with no valid transition).
  - Full lifecycle with guards: sourcing->engaged (screening_complete),
    blocked advance_to_due_diligence (guards_unmet), satisfy NDA + data room +
    explicit approval (DTX5), engaged->diligence, then close_deal approval ->
    deal_closed -> closed_won.
  - DTX13 timeline: append-only events including transaction_created &
    thesis_instantiated.
  - Tasks + memory aggregate (event_count > 0; task reflected).
  - DTX12 workspace aggregate (transaction/stages/current_stage/tasks/approvals/
    documents/participants/timeline/next_action + os_version).
  - /risk reuses Signal engine and reports engine_version.
  - 404 for unknown transaction_id.

Test isolation: cleans tx_* collections once at the start of the module
(deterministic transaction_id makes a fresh slate necessary).
"""
import os
import sys
import pytest
import requests

# Make backend importable from /app/backend (pytest is invoked from there too).
sys.path.insert(0, "/app/backend")
from smoke_loop import run_async as _run  # shared loop for Motor

# Load backend .env so ARROBA_SERVICE_API_KEY is available when running ad-hoc.
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8001").rstrip("/")
TI = "/api/v1/transaction-intelligence"
API_KEY = os.environ.get("ARROBA_SERVICE_API_KEY")
SVC = {"X-API-Key": API_KEY} if API_KEY else {}

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"

pytestmark = pytest.mark.skipif(
    not API_KEY, reason="ARROBA_SERVICE_API_KEY not set"
)


# ── Module setup: clean OS state + seed thesis for a few masters ──
@pytest.fixture(scope="module", autouse=True)
def _clean_and_seed():
    async def go():
        from database import db
        # Ensure masters with financials exist
        if await db.master_companies.count_documents(
                {"financials.latest.revenue": {"$ne": None}}) < 5:
            if os.path.isdir(SAMPLE_DIR):
                from services.data_layer.ingestion.iberinform_ingest import ingest_directory
                from services.data_layer.master.master_builder import rebuild_master
                await ingest_directory(SAMPLE_DIR, source_version="20260519")
                await rebuild_master(scope="full")
        # Clean OS collections so deterministic ids start fresh
        for col in ("tx_transactions", "tx_events", "tx_tasks",
                    "tx_approvals", "tx_documents"):
            await db[col].delete_many({})
        # Ensure indexes
        from services.transaction_os import store as OS
        await OS.ensure_indexes()

    _run(go())
    yield


# Each scenario seeds a thesis on a *different* master so deterministic ids don't
# collide across tests. Workflows also vary to add extra isolation.
def _seed_thesis(skip: int = 0):
    async def go():
        from database import db
        from services.engines.strategy.engine import thesis
        cur = db.master_companies.find(
            {"financials.latest.revenue": {"$ne": None}},
            {"_id": 0, "master_id": 1}
        ).sort("master_id", 1).skip(skip).limit(1)
        docs = [d async for d in cur]
        if not docs:
            pytest.skip(f"No master at skip={skip}")
        t = await thesis(docs[0]["master_id"])
        return t["thesis_id"], t["company_master_id"]
    return _run(go())


def _create_txn(skip: int, workflow: str = "buy_side_v1"):
    tid, _ = _seed_thesis(skip)
    r = requests.post(f"{BASE_URL}{TI}/transaction", headers=SVC,
                      json={"thesis_id": tid, "workflow_name": workflow}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()["transaction"]


# ── 1) Service-key auth ──
def test_auth_required_on_all_endpoints():
    endpoints = [
        ("POST", "/transaction"),
        ("POST", "/next-action"),
        ("POST", "/stage"),
        ("POST", "/task"),
        ("POST", "/decision"),
        ("POST", "/documents"),
        ("POST", "/timeline"),
        ("POST", "/memory"),
        ("POST", "/workspace"),
        ("POST", "/risk"),
    ]
    for method, ep in endpoints:
        r = requests.request(method, f"{BASE_URL}{TI}{ep}", json={}, timeout=15)
        assert r.status_code == 401, f"{ep} expected 401, got {r.status_code}"


def test_auth_works_with_key_on_catalog():
    r = requests.get(f"{BASE_URL}{TI}/catalog", headers=SVC, timeout=15)
    assert r.status_code == 200


# ── 2) GET /catalog ──
def test_catalog_contract():
    cat = requests.get(f"{BASE_URL}{TI}/catalog", headers=SVC, timeout=15).json()
    assert cat["engine_version"] == "transaction-intelligence-v1"
    assert cat["os_version"] == "transaction-os-v1"
    assert set(cat["workflow_templates"]) >= {
        "buy_side_v1", "sell_side_v1", "capital_raise_v1", "partnership_v1"}
    assert len(cat["stages_v1"]) == 8
    assert "advance_to_due_diligence" in cat["high_risk_actions"]
    assert isinstance(cat["transitions"], list) and cat["transitions"]
    from services.engines.signal.actions import CANONICAL_ACTIONS
    assert cat["canonical_actions"] == CANONICAL_ACTIONS


# ── 3) POST /transaction deterministic + auto transition ──
def test_create_transaction_deterministic_and_auto_transition():
    txn = _create_txn(skip=0)
    assert txn["state"] == "sourcing", f"expected sourcing, got {txn['state']}"
    assert txn["workflow_version"] == "buy_side_v1"
    assert txn["state_machine_version"] == "state-machine-v1"
    # Determinism: same thesis + workflow returns same id
    tid_obj = _seed_thesis(0)
    r2 = requests.post(f"{BASE_URL}{TI}/transaction", headers=SVC,
                       json={"thesis_id": tid_obj[0], "workflow_name": "buy_side_v1"},
                       timeout=60).json()
    assert r2["transaction"]["transaction_id"] == txn["transaction_id"]


# ── 4) /next-action explainability + 7-factor confidence ──
def test_next_action_explainability_and_seven_factor_confidence():
    txn = _create_txn(skip=1, workflow="sell_side_v1")
    r = requests.post(f"{BASE_URL}{TI}/next-action", headers=SVC,
                      json={"transaction_id": txn["transaction_id"]}, timeout=60)
    assert r.status_code == 200, r.text
    a = r.json()
    exp_keys = {"why_proposed", "intelligence_support", "risks_avoided",
                "if_not_executed", "dependencies"}
    assert set(a["explainability"].keys()) >= exp_keys
    assert set(a["confidence"]["factors"].keys()) == {
        "evidence_quality", "document_completeness", "approvals_state", "risk",
        "urgency", "critical_dependency", "thesis_consistency"}
    assert 0 <= a["confidence"]["value"] <= 1
    # All recommended_actions belong to the canonical Signal enum
    from services.engines.signal.actions import CANONICAL_ACTIONS
    assert all(x in CANONICAL_ACTIONS for x in a["recommended_actions"])


# ── 5) DTX3 — no implicit transition ──
def test_no_implicit_transition_is_rejected():
    txn = _create_txn(skip=2, workflow="capital_raise_v1")
    r = requests.post(f"{BASE_URL}{TI}/stage", headers=SVC,
                      json={"transaction_id": txn["transaction_id"],
                            "event": "advance_to_due_diligence",
                            "actor_role": "advisor"}, timeout=30).json()
    assert r["applied"] is False
    assert r["state"] == "sourcing"


# ── 5b) Full lifecycle to closed_won with guard enforcement (DTX5) ──
def test_full_lifecycle_with_guards_to_closed_won():
    txn = _create_txn(skip=3, workflow="partnership_v1")
    tid = txn["transaction_id"]
    base = f"{BASE_URL}{TI}"

    # complete origination, qualification, screening
    for st in ("origination", "qualification", "screening"):
        rr = requests.post(f"{base}/stage", headers=SVC,
                           json={"transaction_id": tid, "stage": st,
                                 "actor": "advisor"}, timeout=30)
        assert rr.status_code == 200, rr.text

    # sourcing -> engaged
    eng = requests.post(f"{base}/stage", headers=SVC,
                        json={"transaction_id": tid, "event": "buyer_contacted",
                              "actor_role": "advisor"}, timeout=30).json()
    assert eng["applied"] is True and eng["to"] == "engaged"

    # advance_to_due_diligence blocked
    blocked = requests.post(f"{base}/stage", headers=SVC,
                            json={"transaction_id": tid,
                                  "event": "advance_to_due_diligence",
                                  "actor_role": "advisor"}, timeout=30).json()
    assert blocked["applied"] is False
    assert blocked["reason"] == "guards_unmet"
    unmet = set(blocked["unmet_guards"])
    assert ({"nda_signed", "data_room_open"}.issubset(unmet)
            or "approval:advance_to_due_diligence" in unmet)

    # satisfy guards
    nda = requests.post(f"{base}/documents", headers=SVC,
                        json={"transaction_id": tid, "doc_key": "nda",
                              "doc_type": "nda"}, timeout=30).json()
    requests.post(f"{base}/documents", headers=SVC,
                  json={"transaction_id": tid, "document_id": nda["document_id"],
                        "state": "signed"}, timeout=30)
    requests.post(f"{base}/documents", headers=SVC,
                  json={"transaction_id": tid, "doc_key": "dataroom",
                        "doc_type": "data_room"}, timeout=30)
    ap = requests.post(f"{base}/decision", headers=SVC,
                       json={"transaction_id": tid,
                             "action": "advance_to_due_diligence",
                             "requested_by": "advisor"}, timeout=30).json()
    assert ap["high_risk"] is True and ap["decision"] == "pending"
    requests.post(f"{base}/decision", headers=SVC,
                  json={"approval_id": ap["approval_id"], "decision": "approved",
                        "actor": "partner", "actor_role": "advisor",
                        "evidence_reviewed": ["nda", "valuation"]}, timeout=30)

    dil = requests.post(f"{base}/stage", headers=SVC,
                        json={"transaction_id": tid,
                              "event": "advance_to_due_diligence",
                              "actor_role": "advisor"}, timeout=30).json()
    assert dil["applied"] is True and dil["to"] == "diligence"

    capr = requests.post(f"{base}/decision", headers=SVC,
                         json={"transaction_id": tid, "action": "close_deal",
                               "requested_by": "advisor"}, timeout=30).json()
    requests.post(f"{base}/decision", headers=SVC,
                  json={"approval_id": capr["approval_id"], "decision": "approved",
                        "actor": "partner", "actor_role": "advisor"}, timeout=30)
    won = requests.post(f"{base}/stage", headers=SVC,
                        json={"transaction_id": tid, "event": "deal_closed",
                              "actor_role": "advisor"}, timeout=30).json()
    assert won["applied"] is True and won["to"] == "closed_won"


# ── 6) DTX13 — timeline includes transaction_created & thesis_instantiated ──
def test_timeline_event_driven():
    txn = _create_txn(skip=0)  # already created (buy_side_v1, skip=0)
    tl = requests.post(f"{BASE_URL}{TI}/timeline", headers=SVC,
                       json={"transaction_id": txn["transaction_id"]},
                       timeout=30).json()
    types = [e["type"] for e in tl["events"]]
    assert "transaction_created" in types
    assert "thesis_instantiated" in types
    assert tl["count"] >= 2


# ── 7) Tasks + memory ──
def test_tasks_and_memory_aggregate():
    txn = _create_txn(skip=1, workflow="sell_side_v1")
    tid = txn["transaction_id"]
    t = requests.post(f"{BASE_URL}{TI}/task", headers=SVC,
                      json={"transaction_id": tid, "title": "Prepare teaser",
                            "stage": "origination", "assignee": "analyst"},
                      timeout=30).json()
    assert t["state"] == "open"
    done = requests.post(f"{BASE_URL}{TI}/task", headers=SVC,
                         json={"task_id": t["task_id"], "action": "complete"},
                         timeout=30).json()
    assert done["state"] == "completed"
    mem = requests.post(f"{BASE_URL}{TI}/memory", headers=SVC,
                        json={"transaction_id": tid}, timeout=30).json()
    assert mem["event_count"] > 0
    assert any(x["task_id"] == t["task_id"] for x in mem["tasks"])


# ── 8) DTX12 — workspace aggregate ──
def test_workspace_aggregate():
    txn = _create_txn(skip=0)
    ws = requests.post(f"{BASE_URL}{TI}/workspace", headers=SVC,
                       json={"transaction_id": txn["transaction_id"]},
                       timeout=60).json()
    for k in ("transaction", "stages", "current_stage", "tasks", "approvals",
              "documents", "participants", "timeline", "next_action"):
        assert k in ws, f"workspace missing {k}"
    assert ws["os_version"] == "transaction-os-v1"


# ── 9) /risk reuses Signal engine by reference ──
def test_risk_reuses_signal_engine_by_reference():
    txn = _create_txn(skip=0)
    r = requests.post(f"{BASE_URL}{TI}/risk", headers=SVC,
                      json={"transaction_id": txn["transaction_id"]}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "risks" in body and "blockers" in body
    assert body["engine_version"] == "transaction-intelligence-v1"


# ── 10) 404 — unknown transaction_id ──
def test_404_on_unknown_transaction():
    r = requests.post(f"{BASE_URL}{TI}/next-action", headers=SVC,
                      json={"transaction_id": "txn_doesnotexist"}, timeout=15)
    assert r.status_code == 404
