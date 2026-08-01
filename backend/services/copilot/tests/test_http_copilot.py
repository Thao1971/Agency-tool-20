"""Prueba HTTP real del Copilot: app FastAPI con solo el router + override de auth. Valida enrutado,
Pydantic, forma de respuesta y AISLAMIENTO por usuario, sin depender del server completo."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "copilot_http")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["copilot_http"]
except Exception:
    pass

from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.service_auth import require_service_key
from routes.copilot import router

app = FastAPI()
app.include_router(router)
app.dependency_overrides[require_service_key] = lambda: {"service": "test"}
client = TestClient(app)

INPUTS = {"identity": {"name": "HTTPCO", "cnae_section": "C"},
          "kpis": {"ebitda_margin": 0.18, "revenue_cagr": 0.09, "solvency": 0.55, "ebitda": 1e7,
                   "revenue": 5e7},
          "valuation": {"enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
          "evolution": {"points": [{"year": 2024, "ebitda": 1e7}]}, "financials": {},
          "comparables": {}, "assessment": {}, "sector_intelligence": {}, "documents": {},
          "fragmentation": {"hhi": 1300}}


def test_health_and_capabilities():
    r = client.get("/api/v1/copilot/health")
    assert r.status_code == 200 and set(r.json()["levels"]) == {"L0", "L1", "L2", "L3", "L4"}
    c = client.get("/api/v1/copilot/capabilities")
    assert c.status_code == 200 and len(c.json()["committee"]) == 10


def test_ask_returns_natural_message_and_actions():
    r = client.post("/api/v1/copilot/ask", json={
        "question": "¿Cuál es el EBITDA?", "company_id": "HTTPCO",
        "user": {"tenant_id": "t1", "user_id": "u1"}, "inputs": INPUTS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"]["message"] and body["session_id"]
    assert any(a["kind"] == "navigate" for a in body.get("actions", []))


def test_memory_set_get_and_isolation():
    s = client.post("/api/v1/copilot/memory/set",
                    json={"tenant_id": "t1", "user_id": "u1",
                          "patch": {"buyer_profile": "private_equity", "role": "partner"}})
    assert s.status_code == 200 and s.json()["memory"]["buyer_profile"] == "private_equity"
    g = client.post("/api/v1/copilot/memory/get", json={"tenant_id": "t1", "user_id": "u1"})
    assert g.json()["memory"]["role"] == "partner"
    # aislamiento: otro usuario del mismo tenant no ve la memoria de u1
    other = client.post("/api/v1/copilot/memory/get", json={"tenant_id": "t1", "user_id": "u2"})
    assert other.json()["memory"]["buyer_profile"] is None


def test_governance_whats_known_and_forget():
    client.post("/api/v1/copilot/memory/set",
                json={"tenant_id": "tg", "user_id": "ug", "patch": {"buyer_profile": "family_office"}})
    k = client.post("/api/v1/copilot/governance/whats-known",
                    json={"tenant_id": "tg", "user_id": "ug"})
    assert k.json()["user_memory"]["buyer_profile"] == "family_office"
    f = client.post("/api/v1/copilot/governance/forget",
                    json={"tenant_id": "tg", "user_id": "ug", "scope": "all", "confirm": True})
    assert f.json()["forgotten"] is True
    k2 = client.post("/api/v1/copilot/governance/whats-known",
                     json={"tenant_id": "tg", "user_id": "ug"})
    assert k2.json()["user_memory"]["buyer_profile"] is None


if __name__ == "__main__":
    for fn in (test_health_and_capabilities, test_ask_returns_natural_message_and_actions,
               test_memory_set_get_and_isolation, test_governance_whats_known_and_forget):
        fn(); print("OK", fn.__name__)
