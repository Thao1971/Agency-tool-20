"""Golden Contract Test — arroba.com public integration contract freeze.

Guarantees the live filtered OpenAPI (`/api/v1/openapi/arroba.v1.json`) stays byte-identical
(canonically) to the frozen snapshot `contracts/arroba.v1.json`. Any drift = the public
contract changed → it MUST be a deliberate v2 (new snapshot), never a silent break of v1.

Read-only: does not touch canonical collections.
"""
import json
import hashlib
import pathlib

import requests
from conftest import base

SNAPSHOT = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "arroba.v1.json"
ARROBA_PREFIXES = (
    "/api/v1/financial-intelligence",
    "/api/v1/signal-intelligence",
    "/api/v1/semantic-intelligence",
    "/api/v1/recommendation-intelligence",
    "/api/v1/strategy-intelligence",
    "/api/v1/transaction-intelligence",
)


def _canon(spec: dict) -> str:
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_arroba_snapshot_exists_and_is_v1():
    assert SNAPSHOT.exists(), f"frozen snapshot missing: {SNAPSHOT}"
    snap = json.loads(SNAPSHOT.read_text())
    assert snap["info"]["version"] == "arroba-integration-contract-v1"
    assert len(snap["paths"]) == 53


def test_live_endpoint_matches_frozen_snapshot():
    snap = json.loads(SNAPSHOT.read_text())
    r = requests.get(f"{base()}/api/v1/openapi/arroba.v1.json", timeout=30)
    assert r.status_code == 200
    live = r.json()
    assert _canon(live) == _canon(snap), (
        "arroba public contract drifted from frozen v1 snapshot. "
        "Any change to the 6 engines' public surface must be a deliberate v2 "
        "(regenerate contracts/arroba.v1.json only when intentionally bumping version)."
    )


def test_arroba_contract_exposes_only_the_six_engines():
    snap = json.loads(SNAPSHOT.read_text())
    leaked = [p for p in snap["paths"] if not any(p.startswith(x) for x in ARROBA_PREFIXES)]
    assert leaked == [], f"non-engine routes leaked into arroba contract: {leaked}"


def test_arroba_contract_matches_code_offline():
    """CI gate: build the arroba spec in-process from the app (no HTTP, no DB) and compare
    its canonical hash to the frozen snapshot. Detects CODE drift of the public surface.
    Runs without a live server or MongoDB (Motor connection is lazy)."""
    import server
    snap = json.loads(SNAPSHOT.read_text())
    built = server._build_arroba_openapi()
    assert _canon(built) == _canon(snap), (
        "arroba public contract drifted from frozen v1 snapshot (code changed the public "
        "surface of the 6 engines). This must be a deliberate v2: regenerate "
        "contracts/arroba.v1.json ONLY when intentionally bumping the version."
    )
