"""Prueba HTTP real (Fase 9). Levanta una app FastAPI con SOLO el router del motor y el
override de auth (service-key), y ejerce los endpoints con TestClient — valida enrutado,
parseo Pydantic y forma de respuesta sin depender del server completo."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ide_http")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["ide_http"]
except Exception:
    pass

from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.service_auth import require_service_key
from routes.investment_decision import router

app = FastAPI()
app.include_router(router)
app.dependency_overrides[require_service_key] = lambda: {"service": "test"}
client = TestClient(app)

INPUTS = {
    "identity": {"name": "HTTP CO", "cnae_section": "C"},
    "kpis": {"ebitda_margin": 0.18, "revenue_cagr": 0.09, "solvency": 0.55, "ebitda": 1e7},
    "valuation": {"method": "ev_ebitda", "multiple_basis": "inferred_reference",
                  "enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
    "evolution": {"points": [{"year": 2024, "ebitda": 1e7, "net_financial_position": 4e6}]},
    "financials": {"x": 1}, "comparables": {"subject_ebitda_margin_percentile": 0.7},
    "assessment": {"strengths": ["A", "B"]}, "sector_intelligence": {"s": 1},
    "documents": {"d": 1}, "fragmentation": {"hhi": 1300, "standalone_targets_count": 40},
}


def test_health():
    r = client.get("/api/v1/investment-decision/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine_version"].startswith("investment-decision")
    assert len(body["committee"]) == 10


def test_analyze_and_capabilities_http():
    r = client.post("/api/v1/investment-decision/analyze",
                    json={"opportunity_id": "H1", "buyer_profile": {"type": "strategic"}, "inputs": INPUTS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommendation"] in ("PROCEED", "PROCEED_WITH_CONDITIONS", "EXPLORE", "PASS", "REJECT")
    did = body["meta"]["decision_id"]

    # export-payload de la decisión recién creada
    r2 = client.get(f"/api/v1/investment-decision/decision/{did}/export-payload")
    assert r2.status_code == 200, r2.text
    assert len(r2.json()["sections"]) >= 6

    # copilot Q&A sobre la decisión
    r3 = client.post(f"/api/v1/investment-decision/decision/{did}/ask",
                     json={"question": "¿Cuál es la recomendación?"})
    assert r3.status_code == 200 and r3.json()["unsupported"] is False

    # compare con dos oportunidades
    r4 = client.post("/api/v1/investment-decision/compare",
                     json={"opportunities": [{"opportunity_id": "A", "inputs": INPUTS},
                                             {"opportunity_id": "B", "inputs": INPUTS}],
                           "buyer_profile": {"type": "private_equity"}})
    assert r4.status_code == 200 and len(r4.json()["ranking"]) == 2


if __name__ == "__main__":
    for fn in (test_health, test_analyze_and_capabilities_http):
        fn(); print("OK", fn.__name__)
