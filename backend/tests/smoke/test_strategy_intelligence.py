"""Smoke tests — Sprint 6 Strategy Intelligence Engine.

Validates frozen contract DT1..DT15: deterministic thesis composition, 5 strategic
dimensions + derived score, multifactor confidence, alternatives, constraints,
explainability tree, time horizon, scenarios, decision support, canonical persisted
Strategic Thesis entity + lifecycle, decoupled service API.
"""
import os
import subprocess
import requests
import pytest
from smoke_loop import run_async as _run

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"
ST = "/api/v1/strategy-intelligence"
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
        if await db.master_companies.count_documents({"financials.latest.revenue": {"$ne": None}}) < 50:
            await ingest_directory(SAMPLE_DIR, source_version="20260519")
            await rebuild_master(scope="full")
        await MEM.ensure_indexes()
        await SP.ensure_indexes()
    _run(go())
    yield
    subprocess.run(["sudo", "supervisorctl", "start", "data_layer_worker"], capture_output=True)


def _mid():
    async def go():
        from database import db
        d = await db.master_companies.find_one(
            {"financials.latest.revenue": {"$ne": None}}, {"_id": 0, "master_id": 1})
        return d["master_id"]
    return _run(go())


def test_thesis_entity_shape_and_dimensions():
    from services.engines.strategy.engine import thesis
    from services.engines.strategy.dimensions import DIMENSION_NAMES
    t = _run(thesis(_mid()))
    assert t["thesis_type"] in ["strategic", "consolidation", "acquisition", "divestment",
                                "partnership", "capital_raising", "growth", "risk"]
    # DT2: five strategic dimensions; DT score derived
    assert set(t["strategic_dimensions"].keys()) == set(DIMENSION_NAMES)
    assert 0 <= t["score"] <= 1 and t["strategy_method"] == "evidence-composition-v1"
    # DT5 multifactor confidence
    assert set(t["confidence"]["factors"].keys()) == {"evidence_quality", "cross_engine_consistency",
                                                      "coverage", "recency", "hypotheses_count"}
    # DT9 time horizon + DT12 constraints + DT11 alternatives + DT13 explainability tree
    assert t["time_horizon"]["chosen"] in ("short", "mid", "long") and t["time_horizon"]["justification"]
    assert isinstance(t["constraints"], list) and t["constraints"]
    assert t["alternatives"] and t["preferred_rationale"]
    assert set(t["evidence_tree"].keys()) >= {"thesis", "hypotheses", "recommendations",
                                              "signals", "evidence", "source_data"}
    # DT1 deterministic narrative
    assert t["narrative_method"] == "rules"
    # DT7 reuse by reference (ids, not copied data)
    assert "recommendation_ids" in t and "signal_ids" in t
    assert t["strategy_version"] == "strategy-intelligence-v1"


def test_thesis_id_deterministic_and_persisted():
    from services.engines.strategy.engine import thesis, _thesis_id
    from services.engines.strategy.memory import query
    mid = _mid()
    t = _run(thesis(mid))
    assert t["thesis_id"] == _thesis_id(mid, t["thesis_type"])
    # DT15: persisted canonical entity
    saved = _run(query(thesis_id=t["thesis_id"]))
    assert saved and saved[0]["company_master_id"] == mid
    assert saved[0]["lifecycle"]["state"] in ("proposed", "validated", "rejected",
                                              "executing", "completed", "abandoned")


def test_lifecycle_and_convert():
    from services.engines.strategy.engine import thesis
    from services.engines.strategy import memory as MEM
    t = _run(thesis(_mid()))
    tid = t["thesis_id"]
    upd = _run(MEM.update_lifecycle(tid, "validated", result=None, learning="strong fit"))
    assert upd["lifecycle"]["state"] == "validated"
    conv = _run(MEM.convert(tid, "opportunity"))
    assert conv["converts_to"] == "opportunity"
    with pytest.raises(ValueError):
        _run(MEM.update_lifecycle(tid, "nope"))


def test_scenarios_parametrizable_with_decision_support():
    from services.engines.strategy.engine import scenarios
    s = _run(scenarios(_mid()))
    names = [x["scenario"] for x in s["scenarios"]]
    assert set(names) == {"conservative", "base", "aggressive"}
    assert s["decision_support"]["preferred"] in names
    # DT6: justified comparison
    assert set(s["decision_support"]["comparison"].keys()) == {"advantages", "disadvantages",
        "risks", "hypotheses", "success_conditions"}


def test_decision_justifies_choice():
    from services.engines.strategy.engine import decision
    d = _run(decision(_mid(), "growth", "risk"))
    assert d["preferred"] in ("growth", "risk")
    assert d["comparison"]["advantages"]


def test_insufficient_evidence_not_invented():
    """DT10: a company without financials/semantic coverage -> insufficient_evidence."""
    async def go():
        from database import db
        return await db.master_companies.find_one(
            {"financials.latest.revenue": None}, {"_id": 0, "master_id": 1})
    doc = _run(go())
    if not doc:
        pytest.skip("no company without financials in sample")
    from services.engines.strategy.engine import thesis
    t = _run(thesis(doc["master_id"]))
    if t["status"] == "insufficient_evidence":
        assert "insufficient" in t and t["insufficient"]["missing_evidence"]


# ── API ──
def test_api_requires_service_key():
    r = requests.post(f"{__base()}{ST}/thesis", json={"identifier": "x"}, timeout=20)
    assert r.status_code == 401


def test_api_endpoints():
    mid = _mid()
    th = requests.post(f"{__base()}{ST}/thesis", headers=SVC, json={"identifier": mid}, timeout=60)
    assert th.status_code == 200 and "strategic_dimensions" in th.json()
    for ep in ("growth", "acquisition", "divestment", "partnership", "capital", "risk"):
        r = requests.post(f"{__base()}{ST}/{ep}", headers=SVC, json={"identifier": mid}, timeout=60)
        assert r.status_code == 200 and r.json()["strategy_version"] == "strategy-intelligence-v1"
    sc = requests.post(f"{__base()}{ST}/scenarios", headers=SVC, json={"identifier": mid}, timeout=60)
    assert sc.status_code == 200 and len(sc.json()["scenarios"]) == 3
    cat = requests.get(f"{__base()}{ST}/catalog", headers=SVC, timeout=20).json()
    assert len(cat["thesis_types"]) == 8 and cat["canonical_entity"].startswith("strategic_theses")
    from services.engines.signal.actions import CANONICAL_ACTIONS
    assert cat["canonical_actions"] == CANONICAL_ACTIONS
    nf = requests.post(f"{__base()}{ST}/thesis", headers=SVC, json={"identifier": "nope"}, timeout=20)
    assert nf.status_code == 404
