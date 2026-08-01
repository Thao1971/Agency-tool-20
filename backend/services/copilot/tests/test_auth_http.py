"""Seguridad multi-tenant: scoping por allowed_tenants + confirm en acciones sensibles."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "copilot_auth")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["copilot_auth"]
except Exception:
    pass

from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.service_auth import require_service_key
from routes.copilot import router

# Clave de servicio restringida a los tenants ["t1"]
app = FastAPI()
app.include_router(router)
app.dependency_overrides[require_service_key] = lambda: {"service": "arroba", "allowed_tenants": ["t1"]}
client = TestClient(app)


def test_tenant_scoping_allows_own_and_blocks_others():
    ok = client.post("/api/v1/copilot/memory/get", json={"tenant_id": "t1", "user_id": "u"})
    assert ok.status_code == 200
    blocked = client.post("/api/v1/copilot/memory/get", json={"tenant_id": "t2", "user_id": "u"})
    assert blocked.status_code == 403


def test_missing_tenant_is_rejected():
    r = client.post("/api/v1/copilot/memory/get", json={"tenant_id": "", "user_id": "u"})
    assert r.status_code == 400


def test_sensitive_actions_require_confirm():
    no_conf = client.post("/api/v1/copilot/governance/forget",
                          json={"tenant_id": "t1", "user_id": "u", "scope": "all"})
    assert no_conf.status_code == 400
    conf = client.post("/api/v1/copilot/governance/forget",
                       json={"tenant_id": "t1", "user_id": "u", "scope": "all", "confirm": True})
    assert conf.status_code == 200 and conf.json()["forgotten"] is True
    exp_no = client.post("/api/v1/copilot/governance/export",
                         json={"tenant_id": "t1", "user_id": "u"})
    assert exp_no.status_code == 400


if __name__ == "__main__":
    for fn in (test_tenant_scoping_allows_own_and_blocks_others, test_missing_tenant_is_rejected,
               test_sensitive_actions_require_confirm):
        fn(); print("OK", fn.__name__)
