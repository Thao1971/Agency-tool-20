"""Smoke/contrato del Investment Decision Engine (Fase 1). Determinista, sin BBDD real:
se inyecta la evidencia vía `inputs` (el motor funciona con información parcial) y se usa
mongomock para la persistencia opcional (patrón de los smokes del repo)."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ide_test")
try:  # persistencia en memoria para no bloquear contra un Mongo inexistente
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["ide_test"]
except Exception:
    pass

import asyncio
from services.engines.investment_decision import analyze, models as M
from services.engines.investment_decision import scoring as S


def _run(req):
    return asyncio.get_event_loop().run_until_complete(analyze(req))


BASE_INPUTS = {
    "identity": {"name": "TEST CO"},
    "kpis": {"ebitda_margin": 0.18, "revenue_cagr": 0.09, "solvency": 0.55, "ebitda": 10_000_000},
    "valuation": {"method": "ev_ebitda", "multiple_basis": "inferred_reference",
                  "enterprise_value": 60_000_000, "range": {"low": 50e6, "high": 70e6}},
    "evolution": {"points": [{"year": 2023, "ebitda": 9e6, "net_financial_position": 5e6},
                             {"year": 2024, "ebitda": 10e6, "net_financial_position": 4e6}]},
    "signals": [], "financials": {"x": 1}, "comparables": {"c": 1},
    "assessment": {"a": 1}, "sector_intelligence": {"s": 1}, "documents": {"d": 1},
}


def _req(profile="strategic", inputs=None):
    return {"opportunity_id": "op-1", "buyer_profile": {"type": profile},
            "inputs": inputs if inputs is not None else dict(BASE_INPUTS)}


def test_contract_shape():
    r = _run(_req())
    for k in ("recommendation", "investment_score", "confidence", "executive_summary",
              "committee", "reasoning", "meta"):
        assert k in r, f"falta {k}"
    assert r["recommendation"] in (M.BAND_PROCEED, M.BAND_CONDITIONS, M.BAND_EXPLORE, M.BAND_PASS, M.BAND_REJECT)
    assert len(r["committee"]) == 10                      # comité completo
    assert 0 <= r["investment_score"] <= 100
    # Explainability: toda opinión activa con score lleva evidencia
    for o in r["committee"]:
        if o["recommendation"] != M.REC_ABSTAIN:
            assert o["evidence"], f"{o['specialist']} sin evidencia"


def test_determinism():
    a, b = _run(_req()), _run(_req())
    assert a["investment_score"] == b["investment_score"]
    assert a["recommendation"] == b["recommendation"]
    assert a["meta"]["decision_id"] == b["meta"]["decision_id"]


def test_partial_input_lowers_and_explore():
    r = _run(_req(inputs={"identity": {"name": "X"}, "kpis": {"ebitda_margin": 0.2}}))
    assert r["reasoning"]["coverage"] < S.MIN_COVERAGE
    assert r["recommendation"] == M.BAND_EXPLORE       # cobertura insuficiente ⇒ EXPLORE
    assert r["meta"]["status"] == "insufficient_data"


def test_risk_existential_veto_forces_reject():
    inp = dict(BASE_INPUTS); inp["kpis"] = {**BASE_INPUTS["kpis"], "solvency": -0.1}
    r = _run(_req(inputs=inp))
    assert r["recommendation"] == M.BAND_REJECT
    assert any(v["veto_kind"] == M.VETO_EXISTENTIAL for v in r["reasoning"]["vetoes"])


def test_buyer_profile_reweights():
    strat = S.apply_buyer_profile(S.COMMITTEE_WEIGHTS, "strategic")
    pe = S.apply_buyer_profile(S.COMMITTEE_WEIGHTS, "private_equity")
    assert pe["valuation"] > strat["valuation"]        # PE pondera más el precio
    assert strat["strategy"] > pe["strategy"]          # estratégico pondera más el encaje
    assert abs(sum(pe.values()) - 1.0) < 1e-6          # renormalizado


if __name__ == "__main__":
    for fn in [test_contract_shape, test_determinism, test_partial_input_lowers_and_explore,
               test_risk_existential_veto_forces_reject, test_buyer_profile_reweights]:
        fn(); print("OK", fn.__name__)
