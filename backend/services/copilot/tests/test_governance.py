"""Fase 5 — gobernanza: panel 'lo que sé de ti', export, borrado (olvido), auditoría."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "copilot_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["copilot_test"]
except Exception:
    pass

import asyncio
from services.copilot import governance as GOV
from services.copilot import memory as MEMORY
from services.copilot import feedback as FB
from services.copilot import orchestrate

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


_INPUTS = {"identity": {"name": "ACME", "cnae_section": "retail"},
           "kpis": {"ebitda": 1e7, "revenue": 5e7, "ebitda_margin": 0.18, "revenue_cagr": 0.09,
                    "solvency": 0.55, "revenue_per_employee": 3e5},
           "valuation": {"enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
           "comparables": {"subject_ebitda_margin_percentile": 0.7}, "assessment": {"strengths": ["A"]},
           "sector_intelligence": {"s": 1}, "documents": {"d": 1}, "fragmentation": {"hhi": 1300},
           "evolution": {"points": [{"year": 2024, "ebitda": 1e7}]}, "financials": {}}


def _seed(t, u):
    _run(MEMORY.set_user_memory(t, u, {"buyer_profile": "private_equity", "role": "partner"}))
    _run(FB.record(t, u, "dismiss", dimensions={"sector": "retail"}))
    _run(orchestrate({"question": "¿deberíamos comprarla?", "company_id": "ACME",
                      "opportunity_id": "ACME", "inputs": _INPUTS, "user": {"tenant_id": t, "user_id": u}}))


def test_whats_known_summarizes():
    t, u = "tg", "ug"
    _seed(t, u)
    k = _run(GOV.whats_known(t, u))
    assert k["user_memory"]["buyer_profile"] == "private_equity"
    assert k["user_memory"]["role"] == "partner"
    assert k["entities"] and k["entities"][0]["company_id"] == "ACME"
    assert k["feedback_events"] >= 1 and k["sessions"]


def test_export_contains_all_collections():
    t, u = "tx", "ux"
    _seed(t, u)
    exp = _run(GOV.export_user(t, u))["data"]
    for c in ("copilot_user_memory", "copilot_sessions", "copilot_entity_memory", "copilot_feedback"):
        assert c in exp
    assert exp["copilot_user_memory"]                     # no vacío


def test_forget_scope_and_all():
    t, u = "tz", "uz"
    _seed(t, u)
    # borrar solo feedback
    r1 = _run(GOV.forget_user(t, u, "feedback"))
    assert r1["forgotten"] and _run(GOV.whats_known(t, u))["feedback_events"] == 0
    # el resto sigue
    assert _run(GOV.whats_known(t, u))["user_memory"]["buyer_profile"] == "private_equity"
    # borrado total → defaults y sin entidades
    _run(GOV.forget_user(t, u, "all"))
    k = _run(GOV.whats_known(t, u))
    assert k["user_memory"]["buyer_profile"] is None and not k["entities"]


def test_audit_records_actions():
    t, u = "ta", "ua"
    _run(MEMORY.set_user_memory(t, u, {"role": "analista"}))
    _run(FB.record(t, u, "accept", dimensions={"sector": "pharma"}))
    _run(GOV.export_user(t, u))
    log = _run(GOV.read_audit(t, u))
    actions = {row["action"] for row in log}
    assert {"memory_set", "feedback", "export"} <= actions


if __name__ == "__main__":
    for fn in (test_whats_known_summarizes, test_export_contains_all_collections,
               test_forget_scope_and_all, test_audit_records_actions):
        fn(); print("OK", fn.__name__)
