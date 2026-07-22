"""F0.2 integration tests: public /resolve + agnostic /identity + financial /analyze.

All via X-API-Key (no JWT, no /master/*, no Mongo).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://data-factory-hub.preview.emergentagent.com").rstrip("/")
API_KEY = "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk"
CIF = "A87803862"
HEADERS = {"Content-Type": "application/json", "X-API-Key": API_KEY}


# ---------- Resolve public endpoint ----------
class TestResolvePublic:
    def test_resolve_by_cif(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/resolve",
                          headers=HEADERS, json={"cif": CIF}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 1
        assert data["capability_version"] == "company-intelligence-v2"
        m = data["matches"][0]
        assert m["master_id"].startswith("mc_"), m
        assert m["cif"] == CIF
        assert m["legal_name"]
        assert m["match_type"] == "cif_exact"
        assert m["score"] == 1.0

    def test_resolve_by_name(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/resolve",
                          headers=HEADERS, json={"name": "Totalenergies", "limit": 5}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] >= 1
        for m in data["matches"]:
            assert m["master_id"].startswith("mc_")
            assert m["match_type"] in {"name_exact", "name_partial"}

    def test_resolve_missing_apikey(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/resolve",
                          headers={"Content-Type": "application/json"}, json={"cif": CIF}, timeout=30)
        assert r.status_code == 401, r.status_code

    def test_resolve_empty_body(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/resolve",
                          headers=HEADERS, json={}, timeout=30)
        assert r.status_code == 422, r.status_code


# ---------- Identity canonical (agnostic CIF or master_id) ----------
class TestIdentityCanonical:
    @pytest.fixture(scope="class")
    def master_id(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/resolve",
                          headers=HEADERS, json={"cif": CIF}, timeout=30)
        assert r.status_code == 200
        return r.json()["matches"][0]["master_id"]

    def _validate_identity(self, data):
        assert data.get("legal_name")
        assert "capital_social" in data and data["capital_social"] is not None
        cnae = data.get("cnae_primary") or {}
        assert cnae.get("code"), cnae
        assert isinstance(data.get("data_coverage"), dict)

    def test_identity_by_cif(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/identity",
                          headers=HEADERS, json={"identifier": CIF}, timeout=60)
        assert r.status_code == 200, r.text
        self._validate_identity(r.json())

    def test_identity_by_master_id(self, master_id):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/identity",
                          headers=HEADERS, json={"identifier": master_id}, timeout=60)
        assert r.status_code == 200, r.text
        self._validate_identity(r.json())


# ---------- Financial analyze ----------
class TestFinancialAnalyze:
    def test_analyze_by_cif(self):
        r = requests.post(f"{BASE_URL}/api/v1/financial-intelligence/analyze",
                          headers=HEADERS, json={"identifier": CIF}, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("has_financials") is True, data
        kpis = data.get("kpis") or {}
        assert (kpis.get("revenue") or 0) > 0, kpis
        assert "ebitda" in kpis
        assert "net_income" in kpis
        evo = data.get("evolution") or {}
        assert (evo.get("years") or 0) >= 2, evo
        pts = evo.get("points") or []
        assert len(pts) >= 2
        for p in pts:
            assert "year" in p
            assert p.get("revenue") is not None
        expl = data.get("explainability") or {}
        assert expl.get("data_source"), expl


# ---------- Contract freeze regression ----------
class TestContractFreeze:
    def test_openapi_v1(self):
        r = requests.get(f"{BASE_URL}/api/v1/openapi/arroba.v1.json", timeout=30)
        assert r.status_code == 200
        spec = r.json()
        assert len(spec.get("paths", {})) == 53

    def test_openapi_v2(self):
        r = requests.get(f"{BASE_URL}/api/v1/openapi/arroba.v2.json", timeout=30)
        assert r.status_code == 200
        spec = r.json()
        assert len(spec.get("paths", {})) == 55
        assert "/api/v2/company-intelligence/resolve" in spec["paths"]
