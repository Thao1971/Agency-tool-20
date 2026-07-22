"""Golden Snapshot + Invariant Tests — legacy Signal Engine computation.

Characterizes the DETERMINISTIC calculated output of `compute_signals` and
`signal_similarity` (master-level signals on companies_master: signal_score, signals[]).

Import is location-agnostic (`services.signal_engine`): it must keep working before AND
after M1 (the module is relocated under services/engines/signal with a back-compat shim).
These tests are the parity reference: same inputs ⇒ identical outputs.
"""
import re
import uuid

from services.signal_engine import compute_signals, signal_similarity

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

FIXTURE_DOC = {
    "master_company_id": "mc_snapshot_fixture",
    "confidence_score": 0.8,
    "classification": {"cluster_id": 7, "cluster_tags": ["saas", "b2b"], "sector": "Software"},
    "sources": {"web": {"present": True, "category": "Software"}, "iberinform": {"present": True}},
    "financials": {
        "latest": {"revenue": 1000000, "ebitda": 200000, "employees": 10, "year": 2024},
        "history": [
            {"revenue": 1000000, "ebitda": 200000, "employees": 10, "year": 2024},
            {"revenue": 800000, "ebitda": 150000, "employees": 8, "year": 2023},
        ],
    },
}

# Frozen snapshot (deterministic fields only — excludes signal_id/created_at).
EXPECTED_SIGNALS = [
    ("growth.revenue", "Crecimiento de ingresos +25.0%", "positive", 0.75, 0.8, "inferred"),
    ("growth.ebitda", "Crecimiento de EBITDA +33.3%", "positive", 0.8333, 0.8, "inferred"),
    ("growth.employees", "Crecimiento de empleados +25.0%", "positive", 0.75, 0.8, "inferred"),
    ("profitability.ebitda_margin", "Margen EBITDA 20.0%", "positive", 0.6667, 0.85, "inferred"),
    ("profitability.revenue_per_employee", "Ingresos por empleado 100,000€", "info", 0.3333, 0.7, "inferred"),
    ("profitability.ebitda_per_employee", "EBITDA por empleado 20,000€", "info", 0.3333, 0.7, "inferred"),
    ("size.sector_position", "Posición sectorial alto (P75)", "positive", 0.75, 0.75, "inferred"),
    ("activity.data_sources", "2 fuente(s) de datos integradas", "info", 0.8, 0.8, "normalized"),
    ("similarity.cluster", "Segmento semántico #7", "info", 0.6, 0.7, "ai_generated"),
]
EXPECTED_SCORE = 71


def test_compute_signals_snapshot():
    signals, score = compute_signals(FIXTURE_DOC, rev_pct=0.75)
    assert score == EXPECTED_SCORE, f"signal_score drift: {score} != {EXPECTED_SCORE}"
    assert len(signals) == len(EXPECTED_SIGNALS)
    got = [(s["signal_type"], s["title"], s["severity"], s["score"], s["confidence"],
            s["lineage"]["source"]) for s in signals]
    assert got == EXPECTED_SIGNALS, f"signal snapshot drift:\n{got}"


def test_compute_signals_invariants():
    signals, score = compute_signals(FIXTURE_DOC, rev_pct=0.75)
    # score is an int in 0..100
    assert isinstance(score, int) and 0 <= score <= 100
    for s in signals:
        # each signal has a uuid signal_id, clamped score/confidence, required keys
        assert UUID_RE.match(s["signal_id"])
        assert 0.0 <= s["score"] <= 1.0
        assert 0.0 <= s["confidence"] <= 1.0
        assert set(s.keys()) >= {"signal_id", "signal_type", "title", "description",
                                 "severity", "score", "confidence", "created_at", "lineage"}
        assert s["severity"] in ("positive", "negative", "neutral", "info")


def test_compute_signals_sparse_company_no_crash():
    """Empty/partial company: no financials/history ⇒ still returns a (signals, score)."""
    sparse = {"master_company_id": "mc_sparse", "confidence_score": 0.5}
    signals, score = compute_signals(sparse, rev_pct=None)
    assert isinstance(signals, list)
    assert isinstance(score, int) and 0 <= score <= 100


def test_signal_similarity_snapshot():
    seed = {"classification": {"cluster_id": 7}, "signal_score": 80}
    # same cluster + close score → high affinity
    assert signal_similarity(seed, {"classification": {"cluster_id": 7}, "signal_score": 70}) == 0.95
    # different cluster + distant score → low affinity
    assert signal_similarity(seed, {"classification": {"cluster_id": 9}, "signal_score": 40}) == 0.3
    # missing candidate score → neutral 0.5 proximity (same cluster → 0.75)
    assert signal_similarity(seed, {"classification": {"cluster_id": 7}, "signal_score": None}) == 0.75


def test_signal_similarity_invariants():
    seed = {"classification": {"cluster_id": 1}, "signal_score": 50}
    for cand in ({"classification": {"cluster_id": 1}, "signal_score": 50},
                 {"classification": {"cluster_id": 2}, "signal_score": 0},
                 {"classification": {}, "signal_score": None}):
        v = signal_similarity(seed, cand)
        assert 0.0 <= v <= 1.0


def test_m1_relocation_parity_shim_is_canonical():
    """M1 parity: the legacy import path is a shim that re-exports the SAME objects from
    the canonical location services.engines.signal.master_signals (relocation, not a fork)."""
    import services.signal_engine as legacy
    from services.engines.signal import master_signals as canonical
    assert legacy.compute_signals is canonical.compute_signals
    assert legacy.rebuild_signals is canonical.rebuild_signals
    assert legacy.signal_similarity is canonical.signal_similarity
    # identical computation via both paths
    s_legacy, sc_legacy = legacy.compute_signals(FIXTURE_DOC, rev_pct=0.75)
    s_canon, sc_canon = canonical.compute_signals(FIXTURE_DOC, rev_pct=0.75)
    assert sc_legacy == sc_canon == EXPECTED_SCORE
