"""Golden/Guard Tests — Entity Bridge quality tool (M3-phase-2).

Verify the job is read-only over legacy, idempotent, reversible, and produces the required
quality metrics. It must NEVER modify companies_master nor activate the canonical engine.
"""
from smoke_loop import run_async
from database import db
from services.data_layer.master import entity_bridge as EB

METRIC_KEYS = {"processed", "linked", "coverage_pct", "conflicts", "ambiguous", "orphans",
               "potential_duplicate_groups", "potential_duplicate_records", "pending_manual_review"}


def _bridge_xref_count():
    return run_async(db.entity_xref.count_documents({"origin": EB.ORIGIN}))


def test_dry_run_reports_without_writing():
    runs_before = run_async(db.er_bridge_runs.count_documents({}))
    xref_before = _bridge_xref_count()
    rep = run_async(EB.run_bridge(limit=200, dry_run=True))
    assert rep["dry_run"] is True
    assert METRIC_KEYS.issubset(set(rep["metrics"].keys()))
    m = rep["metrics"]
    # classification is exhaustive
    assert m["linked"] + m["conflicts"] + m["ambiguous"] + m["orphans"] == m["processed"]
    assert 0 <= m["coverage_pct"] <= 100
    # no writes
    assert run_async(db.er_bridge_runs.count_documents({})) == runs_before
    assert _bridge_xref_count() == xref_before


def test_run_persists_and_is_idempotent():
    rep1 = run_async(EB.run_bridge(limit=300))
    rid1 = rep1["run_id"]
    assert run_async(db.er_bridge_runs.find_one({"run_id": rid1})) is not None
    xref_after_1 = _bridge_xref_count()
    # re-run: bridge xref rows must NOT duplicate (upsert by external_id)
    rep2 = run_async(EB.run_bridge(limit=300))
    xref_after_2 = _bridge_xref_count()
    assert xref_after_2 == xref_after_1, "bridge must be idempotent (no duplicate xref rows)"
    # cleanup both runs
    run_async(EB.rollback_run(rid1))
    run_async(EB.rollback_run(rep2["run_id"]))


def test_rollback_removes_only_job_rows():
    rep = run_async(EB.run_bridge(limit=300))
    rid = rep["run_id"]
    res_before = run_async(db.er_bridge_results.count_documents({"run_id": rid}))
    assert res_before > 0
    rb = run_async(EB.rollback_run(rid))
    assert rb["status"] == "rolled_back"
    assert run_async(db.er_bridge_results.count_documents({"run_id": rid})) == 0
    assert run_async(db.entity_xref.count_documents({"origin": EB.ORIGIN, "bridge_run_id": rid})) == 0
    run_doc = run_async(db.er_bridge_runs.find_one({"run_id": rid}, {"_id": 0}))
    assert run_doc["status"] == "rolled_back"


def test_never_mutates_legacy():
    legacy_before = run_async(db.companies_master.find_one({}, {"_id": 0}))
    mcid = legacy_before["master_company_id"]
    rep = run_async(EB.run_bridge(limit=300))
    legacy_after = run_async(db.companies_master.find_one({"master_company_id": mcid}, {"_id": 0}))
    assert legacy_after == legacy_before, "entity bridge must NEVER modify legacy records"
    run_async(EB.rollback_run(rep["run_id"]))


def test_historical_runs_listed():
    rep = run_async(EB.run_bridge(limit=100))
    runs = run_async(EB.list_runs(10))
    assert any(r["run_id"] == rep["run_id"] for r in runs)
    detail = run_async(EB.get_run(rep["run_id"]))
    assert "samples" in detail and set(detail["samples"].keys()) == {"conflict", "ambiguous", "orphan"}
    run_async(EB.rollback_run(rep["run_id"]))
