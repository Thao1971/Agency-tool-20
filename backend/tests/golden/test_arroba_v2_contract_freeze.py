"""Golden Contract Test — arroba.com public integration contract freeze (v2).

Freezes the TYPED v2 contract (`/api/v1/openapi/arroba.v2.json`): the six Intelligence
Engines with explicit response DTOs (V2-01) + the public Company/Identity capability (V2-02).

v2 is a superset of v1 and does NOT change runtime behaviour (DTOs document, never filter).
v1 stays byte-identical and is protected by test_arroba_contract_freeze.py.
"""
import json
import hashlib
import pathlib

import requests
from conftest import base

SNAPSHOT = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "arroba.v2.json"
V2_PREFIXES = (
    "/api/v1/financial-intelligence",
    "/api/v1/signal-intelligence",
    "/api/v1/semantic-intelligence",
    "/api/v1/recommendation-intelligence",
    "/api/v1/strategy-intelligence",
    "/api/v1/transaction-intelligence",
    "/api/v2/company-intelligence",
)


def _canon(spec: dict) -> str:
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_v2_snapshot_exists_and_is_v2():
    assert SNAPSHOT.exists(), f"frozen v2 snapshot missing: {SNAPSHOT}"
    snap = json.loads(SNAPSHOT.read_text())
    assert snap["info"]["version"] == "arroba-integration-contract-v2"
    # 53 v1 engine paths + company/identity + company/resolve
    assert len(snap["paths"]) == 55


def test_v2_live_endpoint_matches_frozen_snapshot():
    snap = json.loads(SNAPSHOT.read_text())
    r = requests.get(f"{base()}/api/v1/openapi/arroba.v2.json", timeout=30)
    assert r.status_code == 200
    assert _canon(r.json()) == _canon(snap), (
        "arroba v2 contract drifted from frozen v2 snapshot. Regenerate contracts/arroba.v2.json "
        "ONLY when intentionally evolving the typed public surface."
    )


def test_v2_contract_matches_code_offline():
    import server
    snap = json.loads(SNAPSHOT.read_text())
    built = server._build_arroba_v2_openapi()
    assert _canon(built) == _canon(snap), "arroba v2 contract drifted from frozen snapshot (code changed)."


def test_v2_exposes_only_engines_plus_company():
    snap = json.loads(SNAPSHOT.read_text())
    leaked = [p for p in snap["paths"] if not any(p.startswith(x) for x in V2_PREFIXES)]
    assert leaked == [], f"non-public routes leaked into arroba v2 contract: {leaked}"


def test_v2_all_200_responses_are_typed():
    """V2-01 acceptance: every 200 response references a named component schema (no `{}`)."""
    snap = json.loads(SNAPSHOT.read_text())
    untyped = []
    for path, item in snap["paths"].items():
        for method, op in item.items():
            content = (op.get("responses", {}).get("200", {}).get("content") or {})
            schema = (content.get("application/json", {}) or {}).get("schema")
            if not schema or not schema.get("$ref"):
                untyped.append(f"{method.upper()} {path}")
    assert untyped == [], f"untyped 200 responses in v2 contract: {untyped}"


def test_v2_company_identity_present_and_typed():
    snap = json.loads(SNAPSHOT.read_text())
    op = snap["paths"].get("/api/v2/company-intelligence/identity", {}).get("post")
    assert op, "company/identity endpoint missing from v2 contract"
    ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("CompanyIdentityResponse")
