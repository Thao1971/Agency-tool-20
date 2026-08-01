"""Fase 2 — voz/personalización: verbosidad por rol, autonomía→CIM, truncado sin fabricar."""

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
from services.copilot import voice as VOICE
from services.copilot import memory as MEMORY
from services.copilot import orchestrate

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def test_resolve_role_and_autonomy():
    assert VOICE.resolve("analista", 1)["verbosity"] == "detailed"
    assert VOICE.resolve("partner", 1)["verbosity"] == "executive"
    assert VOICE.resolve(None, 1)["verbosity"] == "balanced"          # default
    assert VOICE.resolve("analista", 0)["max_proactive_state"] == "conversation"
    assert VOICE.resolve("analista", 1)["max_proactive_state"] == "informer"
    assert VOICE.resolve("analista", 3)["max_proactive_state"] == "director"


def test_truncate_never_fabricates():
    long = ("Primera frase con contexto suficiente. Segunda frase con más detalle sobre el asunto. "
            "Tercera frase que ya sobra para un ejecutivo y debería quedar fuera del recorte final.")
    ex = VOICE._truncate(long, 120)
    assert len(ex) <= 121 and ex in long                              # subcadena: nada inventado
    # detailed no recorta un texto corto
    short = "Cuerpo breve."
    assert VOICE._truncate(short, 800) == short


def test_orchestrate_exposes_voice_and_role():
    user = {"tenant_id": "tv", "user_id": "uv", "role": "partner"}
    r = _run(orchestrate({"question": "¿cuánto vale y qué riesgos tiene?", "company_id": "ACME",
                          "opportunity_id": "ACME",
                          "inputs": {"identity": {"name": "ACME", "cnae_section": "C"},
                                     "kpis": {"ebitda": 1e7, "revenue": 5e7, "ebitda_margin": 0.18,
                                              "revenue_cagr": 0.09, "solvency": 0.55},
                                     "valuation": {"enterprise_value": 6e7,
                                                   "range": {"low": 5e7, "high": 7e7}},
                                     "comparables": {}, "assessment": {}, "sector_intelligence": {},
                                     "documents": {}, "fragmentation": {"hhi": 1300},
                                     "evolution": {"points": [{"year": 2024, "ebitda": 1e7}]},
                                     "financials": {}},
                          "user": user}))
    assert r["voice"]["verbosity"] == "executive"
    assert r["personalization_applied"]["role"] == "partner"
    assert r["personalization_applied"]["max_proactive_state"] == "informer"   # autonomía default 1
    d = r["answer"].get("detail")
    assert d is None or len(d) <= r["voice"]["detail_limit"] + 1


def test_role_from_memory_when_not_in_request():
    _run(MEMORY.set_user_memory("tm", "um", {"role": "analista"}))
    r = _run(orchestrate({"question": "¿cuál es el EBITDA?", "company_id": "ACME",
                          "opportunity_id": "ACME",
                          "inputs": {"identity": {"name": "ACME"}, "kpis": {"ebitda": 1e7},
                                     "evolution": {"points": []}, "financials": {},
                                     "valuation": {}, "comparables": {}, "assessment": {},
                                     "sector_intelligence": {}, "documents": {}, "fragmentation": {}},
                          "user": {"tenant_id": "tm", "user_id": "um"}}))
    assert r["personalization_applied"]["role"] == "analista"
    assert r["voice"]["verbosity"] == "detailed"


if __name__ == "__main__":
    for fn in (test_resolve_role_and_autonomy, test_truncate_never_fabricates,
               test_orchestrate_exposes_voice_and_role, test_role_from_memory_when_not_in_request):
        fn(); print("OK", fn.__name__)
