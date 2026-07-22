"""Tests for V2.0 Sprint: V2-02 endpoint + v1 backward-compat + v1/v2 contracts."""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://data-factory-hub.preview.emergentagent.com").rstrip("/")
API_KEY = "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
MASTER_ID = "mc_457c000acfd3"
CIF = "B59022921"


# ============ V2-02: Company Identity ============
class TestCompanyIdentity:
    def test_identity_by_cif(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/identity",
                          headers=HEADERS, json={"identifier": CIF})
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["master_id", "cif", "legal_name", "capital_social", "cnae_primary", "data_coverage"]:
            assert k in d, f"missing {k}: {d}"
        assert d["capability_version"] == "company-intelligence-v2"

    def test_identity_by_master_id(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/identity",
                          headers=HEADERS, json={"identifier": MASTER_ID})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["master_id"] == MASTER_ID
        assert d["capability_version"] == "company-intelligence-v2"

    def test_identity_no_api_key(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/identity",
                          headers={"Content-Type": "application/json"},
                          json={"identifier": CIF})
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"

    def test_identity_unknown(self):
        r = requests.post(f"{BASE_URL}/api/v2/company-intelligence/identity",
                          headers=HEADERS, json={"identifier": "B00000000"})
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text}"


# ============ V1 backward compat ============
class TestV1BackwardCompat:
    def test_financial_analyze(self):
        r = requests.post(f"{BASE_URL}/api/v1/financial-intelligence/analyze",
                          headers=HEADERS, json={"identifier": MASTER_ID})
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["kpis", "ratios", "valuation", "engine_version"]:
            assert k in d, f"missing {k}"

    def test_signal_analyze(self):
        r = requests.post(f"{BASE_URL}/api/v1/signal-intelligence/analyze",
                          headers=HEADERS, json={"identifier": MASTER_ID})
        assert r.status_code == 200, r.text

    def test_semantic_profile(self):
        r = requests.post(f"{BASE_URL}/api/v1/semantic-intelligence/profile",
                          headers=HEADERS, json={"identifier": MASTER_ID})
        assert r.status_code == 200, r.text

    def test_recommendation_comparables(self):
        r = requests.post(f"{BASE_URL}/api/v1/recommendation-intelligence/comparables",
                          headers=HEADERS, json={"identifier": MASTER_ID})
        assert r.status_code == 200, r.text

    def test_strategy_thesis(self):
        r = requests.post(f"{BASE_URL}/api/v1/strategy-intelligence/thesis",
                          headers=HEADERS, json={"identifier": MASTER_ID})
        assert r.status_code == 200, r.text

    def test_transaction_catalog(self):
        r = requests.get(f"{BASE_URL}/api/v1/transaction-intelligence/catalog",
                         headers=HEADERS)
        assert r.status_code == 200, r.text


# ============ Contracts ============
class TestContracts:
    def test_arroba_v1_contract(self):
        r = requests.get(f"{BASE_URL}/api/v1/openapi/arroba.v1.json")
        assert r.status_code == 200
        spec = r.json()
        assert spec["info"]["version"] == "arroba-integration-contract-v1"
        assert len(spec["paths"]) == 53, f"expected 53, got {len(spec['paths'])}"
        # v1 200 responses must have no schema
        for path, methods in spec["paths"].items():
            for method, op in methods.items():
                if not isinstance(op, dict):
                    continue
                resp200 = op.get("responses", {}).get("200")
                if not resp200:
                    continue
                content = resp200.get("content", {})
                for mime, body in content.items():
                    schema = body.get("schema", {})
                    assert schema == {} or schema is None or not schema, \
                        f"v1 {method} {path} has typed schema: {schema}"

    def test_arroba_v2_contract(self):
        r = requests.get(f"{BASE_URL}/api/v1/openapi/arroba.v2.json")
        assert r.status_code == 200
        spec = r.json()
        assert spec["info"]["version"] == "arroba-integration-contract-v2"
        assert len(spec["paths"]) == 54, f"expected 54, got {len(spec['paths'])}"
        assert "/api/v2/company-intelligence/identity" in spec["paths"]
        # v2 200 responses must reference schema
        untyped = []
        for path, methods in spec["paths"].items():
            for method, op in methods.items():
                if not isinstance(op, dict) or method not in ("get", "post", "put", "delete", "patch"):
                    continue
                resp200 = op.get("responses", {}).get("200")
                if not resp200:
                    continue
                content = resp200.get("content", {})
                if not content:
                    untyped.append(f"{method} {path} (no content)")
                    continue
                for mime, body in content.items():
                    schema = body.get("schema", {})
                    if "$ref" not in schema:
                        untyped.append(f"{method} {path}")
        assert not untyped, f"v2 endpoints without $ref: {untyped}"
        # Verify company identity refs CompanyIdentityResponse
        ci = spec["paths"]["/api/v2/company-intelligence/identity"]["post"]
        ref = ci["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert "CompanyIdentityResponse" in ref, f"unexpected ref: {ref}"
