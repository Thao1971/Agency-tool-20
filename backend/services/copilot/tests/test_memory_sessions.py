"""Fase 1 — memoria de usuario + sesiones + continuidad de referencias (determinista, mongomock)."""

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
from services.copilot import orchestrate
from services.copilot import memory as MEMORY
from services.copilot import session as SESSION

INPUTS = {
    "identity": {"name": "ACME", "cnae_section": "C"},
    "kpis": {"ebitda_margin": 0.18, "revenue_cagr": 0.09, "solvency": 0.55, "ebitda": 1e7,
             "revenue": 5e7, "revenue_per_employee": 300000},
    "valuation": {"method": "ev_ebitda", "multiple_basis": "inferred_reference",
                  "enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
    "evolution": {"points": [{"year": 2024, "ebitda": 1e7, "net_financial_position": 4e6}]},
    "financials": {"x": 1}, "comparables": {"subject_ebitda_margin_percentile": 0.7},
    "assessment": {"strengths": ["A", "B"]}, "sector_intelligence": {"s": 1},
    "documents": {"d": 1}, "fragmentation": {"hhi": 1300, "standalone_targets_count": 40},
}

_loop = asyncio.get_event_loop()


def _run(coro):
    return _loop.run_until_complete(coro)


def test_user_memory_defaults_and_set():
    m = _run(MEMORY.get_user_memory("t1", "u1"))
    assert m["autonomy_level"] == 1 and m["buyer_profile"] is None      # default 1 · Informa
    m2 = _run(MEMORY.set_user_memory("t1", "u1",
              {"buyer_profile": "private_equity", "autonomy_level": 2, "secret": "x"}))
    assert m2["buyer_profile"] == "private_equity" and m2["autonomy_level"] == 2
    assert "secret" not in m2                                            # whitelist
    # aislamiento por usuario
    assert _run(MEMORY.get_user_memory("t1", "u2"))["buyer_profile"] is None


def test_session_create_resume_close():
    s = _run(SESSION.get_or_create(None, "t1", "u1", {"type": "strategic"}))
    sid = s["session_id"]
    assert sid.startswith("cs_") and s["status"] == "active"
    _run(SESSION.update(sid, context_patch={"active_entity": {"id": "ACME", "name": "ACME"}}))
    again = _run(SESSION.get_or_create(sid, "t1", "u1", {"type": "strategic"}))
    assert again["session_id"] == sid                                   # reanuda
    assert again["working_context"]["active_entity"]["id"] == "ACME"
    _run(SESSION.close(sid))
    fresh = _run(SESSION.get_or_create(sid, "t1", "u1", {"type": "strategic"}))
    assert fresh["session_id"] != sid                                   # cerrada → nueva


def test_reference_continuity_and_personalization():
    user = {"tenant_id": "t9", "user_id": "u9"}
    r1 = orchestrate({"question": "¿cuál es el EBITDA?", "company_id": "ACME",
                      "opportunity_id": "ACME", "inputs": INPUTS,
                      "buyer_profile": {"type": "private_equity"}, "user": user})
    r1 = _run(r1) if asyncio.iscoroutine(r1) else r1
    sid = r1["session_id"]
    assert r1["level"] == "L0" and r1["personalization_applied"]["autonomy_level"] == 1
    assert r1["personalization_applied"]["buyer_profile_source"] == "request"
    # 2º turno SIN compañía: debe reutilizar la entidad activa de la sesión
    r2 = _run(orchestrate({"question": "¿y sus riesgos?", "session_id": sid,
                           "inputs": INPUTS, "user": user}))
    assert r2["session_id"] == sid
    assert r2["level"] in ("L1", "L2")
    assert r2["personalization_applied"]["reference_resolved"] is True


def test_profile_from_user_memory():
    _run(MEMORY.set_user_memory("t5", "u5", {"buyer_profile": "family_office"}))
    r = _run(orchestrate({"question": "¿cuál es el EBITDA?", "company_id": "ACME",
                          "opportunity_id": "ACME", "inputs": INPUTS,
                          "user": {"tenant_id": "t5", "user_id": "u5"}}))
    assert r["personalization_applied"]["buyer_profile"] == "family_office"
    assert r["personalization_applied"]["buyer_profile_source"] == "user_memory"


def test_conversation_context_accumulates():
    from services.copilot import session as SESSION
    user = {"tenant_id": "tc", "user_id": "uc"}
    r1 = _run(orchestrate({"question": "¿cuál es el EBITDA?", "company_id": "ACME",
                           "opportunity_id": "ACME", "inputs": INPUTS, "user": user}))
    assert r1["personalization_applied"]["context_turns"] == 0     # primer turno, sin historia
    sid = r1["session_id"]
    r2 = _run(orchestrate({"question": "¿y sus riesgos?", "session_id": sid,
                           "inputs": INPUTS, "user": user}))
    assert r2["personalization_applied"]["context_turns"] >= 1     # ya hay contexto previo
    # el turno guardado se enriquece con entidad + resumen
    doc = _run(SESSION.get_or_create(sid))
    turns = doc["turns"]
    assert turns and turns[0].get("entity", {}).get("id") == "ACME" and turns[0].get("summary")


if __name__ == "__main__":
    for fn in (test_user_memory_defaults_and_set, test_session_create_resume_close,
               test_reference_continuity_and_personalization, test_profile_from_user_memory,
               test_conversation_context_accumulates):
        fn(); print("OK", fn.__name__)
