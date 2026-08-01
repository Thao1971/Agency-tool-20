"""Voz — Natural Executive Conversation: prosa natural, fact-lock, sin frases mecánicas."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "copilot_test")
# aseguramos que el pulido IA está apagado en el test (comportamiento determinista)
os.environ.pop("COPILOT_VOICE_PROVIDER", None)
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["copilot_test"]
except Exception:
    pass

import asyncio
from services.copilot import narrator as N
from services.copilot import orchestrate

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def test_risk_without_evidence_is_natural():
    out = {"level": "L2", "opinions": [{"recommendation": "abstain", "risks": [], "strengths": [],
                                        "conditions": [], "evidence": []}],
           "targets": ["risk"], "answer": {}}
    nat = _run(N.narrate(out, {"name": "ACME", "profile": "private_equity", "verbosity": "executive"}))
    m = nat["message"]
    assert "todavía no veo evidencia suficiente" in m
    assert "due diligence" in m and "concentración de clientes" in m
    assert "—" not in nat["headline"] or "ACME — risk" not in m       # nada mecánico


def test_fact_is_conversational_and_not_fabricated():
    out = {"level": "L0", "fact": {"label": "EBITDA", "value": "10.000.000 €", "available": True},
           "answer": {}}
    nat = _run(N.narrate(out, {"name": "ACME", "profile": "private_equity", "verbosity": "executive"}))
    assert "El EBITDA de ACME es de 10.000.000 €." == nat["message"]   # solo el dato dado
    # dato ausente: lo dice con naturalidad, sin inventar
    out2 = {"level": "L0", "fact": {"label": "Deuda financiera neta", "value": None,
                                    "available": False}, "answer": {}}
    nat2 = _run(N.narrate(out2, {"name": "ACME", "verbosity": "executive"}))
    assert "Aún no tengo cargado" in nat2["message"] and "€" not in nat2["message"]


def test_decision_weaves_evolution():
    out = {"level": "L3", "decision": {"recommendation": "PROCEED", "investment_score": 94,
                                       "confidence": 0.84, "strengths": [{"text": "márgenes sólidos"}],
                                       "risks": [], "conditions_to_proceed": []}, "answer": {}}
    ctx = {"name": "ACME", "profile": "private_equity", "verbosity": "executive",
           "entity_history": {"delta": {"first": False, "direction": "improved", "band_from": "PROCEED",
                                        "band_to": "PROCEED", "score_from": 77, "score_to": 94}}}
    nat = _run(N.narrate(out, ctx))
    m = nat["message"]
    assert "Yo avanzaría con esta operación" in m and "convicción alta" in m
    assert "ha mejorado" in m
    assert "PROCEED" not in m and "94" not in m and "/100" not in m   # sin jerga ni números en la voz
    # la banda/score quedan en 'disclosure' para "ver deliberación"
    assert nat["disclosure"]["band"] == "PROCEED" and nat["disclosure"]["score"] == 94
    assert nat["disclosure"]["conviction"] == "Convicción alta"


def test_orchestrate_produces_natural_message_not_mechanical():
    r = _run(orchestrate({"question": "¿y qué riesgos tiene?", "company_id": "ACME",
                          "opportunity_id": "ACME",
                          "inputs": {"identity": {"name": "ACME"}, "kpis": {}, "evolution": {"points": []},
                                     "financials": {}, "valuation": {}, "comparables": {},
                                     "assessment": {}, "sector_intelligence": {}, "documents": {},
                                     "fragmentation": {}},
                          "user": {"tenant_id": "tn", "user_id": "un", "role": "partner"}}))
    msg = r["answer"]["message"]
    assert "Sin lectura concluyente con el dato disponible" not in msg   # ya no mecánico
    assert "ACME — " not in msg
    assert len(msg) > 60                                                 # tiene cuerpo, no telegráfico


def test_specialist_attribution_cites_area():
    out = {"level": "L1", "targets": ["risk"], "answer": {},
           "opinions": [{"recommendation": "abstain", "risks": [], "strengths": [], "conditions": [],
                         "evidence": []}]}
    nat = _run(N.narrate(out, {"name": "ACME", "profile": "private_equity", "verbosity": "detailed"}))
    assert "área de Riesgo" in nat["message"]
    assert nat["attribution"] == [{"name": "risk", "label": "Riesgo"}]


def test_decision_attribution_lists_contributing_areas():
    out = {"level": "L3", "answer": {},
           "decision": {"recommendation": "PROCEED", "investment_score": 80, "confidence": 0.8,
                        "strengths": [], "risks": [], "conditions_to_proceed": [],
                        "committee": [{"specialist": "cfo", "recommendation": "proceed"},
                                      {"specialist": "valuation", "recommendation": "proceed"},
                                      {"specialist": "risk", "recommendation": "abstain"}]}}
    nat = _run(N.narrate(out, {"name": "ACME", "verbosity": "executive"}))
    assert "áreas de" in nat["message"] and "Finanzas (CFO)" in nat["message"]
    names = [a["name"] for a in nat["attribution"]]
    assert "cfo" in names and "valuation" in names and "risk" not in names   # abstención excluida


def test_multientity_compare_without_data_names_them():
    out = {"level": "L4", "capability": "compare", "answer": {"data": {"ranking": []}}}
    nat = _run(N.narrate(out, {"name": "la compañía", "entities": ["ACME", "BETACO"]}))
    assert "ACME" in nat["message"] and "BETACO" in nat["message"]


def test_fact_has_no_attribution():
    out = {"level": "L0", "fact": {"label": "EBITDA", "value": "10 M€", "available": True}, "answer": {}}
    nat = _run(N.narrate(out, {"name": "ACME", "verbosity": "executive"}))
    assert "attribution" not in nat and "área de" not in nat["message"]


def test_fact_lock_guard_pure():
    allowed = "El EBITDA de ACME es de 10.000.000 €. {\"ebitda_margin\": 0.18}"
    assert N._introduces_new_numbers("El margen es del 15%", allowed) is True     # 15 no estaba
    assert N._introduces_new_numbers("Ronda los 10 millones, con 18% de margen", allowed) is False


def test_ai_polish_rejected_if_hallucinates_number():
    import docstudio.model_provider as MP
    orig = MP.generate_copilot_message
    os.environ["COPILOT_VOICE_PROVIDER"] = "claude"
    out = {"level": "L0", "fact": {"label": "EBITDA", "value": "10.000.000 €", "available": True},
           "answer": {}}
    ctx = {"name": "ACME", "verbosity": "executive"}
    try:
        async def _hallucinate(context, provider="claude", document_id=None):
            return {"message": "El EBITDA de ACME es de 10.000.000 €, con un margen del 15%."}
        MP.generate_copilot_message = _hallucinate
        nat = _run(N.narrate(out, ctx))
        assert "15%" not in nat["message"]                     # rechazado → determinista

        async def _faithful(context, provider="claude", document_id=None):
            return {"message": "El EBITDA de ACME ronda los 10.000.000 €."}
        MP.generate_copilot_message = _faithful
        nat2 = _run(N.narrate(out, ctx))
        assert "ronda" in nat2["message"]                      # aceptado (sin cifras nuevas)
    finally:
        MP.generate_copilot_message = orig
        os.environ.pop("COPILOT_VOICE_PROVIDER", None)


if __name__ == "__main__":
    for fn in (test_risk_without_evidence_is_natural, test_fact_is_conversational_and_not_fabricated,
               test_decision_weaves_evolution, test_orchestrate_produces_natural_message_not_mechanical,
               test_specialist_attribution_cites_area, test_decision_attribution_lists_contributing_areas,
               test_multientity_compare_without_data_names_them, test_fact_has_no_attribution,
               test_fact_lock_guard_pure, test_ai_polish_rejected_if_hallucinates_number):
        fn(); print("OK", fn.__name__)
