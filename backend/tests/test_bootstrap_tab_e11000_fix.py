"""
Regression tests for the E11000 duplicate key fix in Iberinform .tab bootstrap.

Fix: services/data_layer/master/entity_resolution.py:resolve()
For a NEW company whose CIF matches no existing master, it now returns a fresh
master_id directly and does NOT fall through to the domain / name+province
fallback (which previously caused two distinct real companies sharing a domain
to collide onto the same master_id and trigger E11000 on cif_normalized upsert).

Run against local backend (public preview URL 502s on requests > ~100s).
"""
import os
import sys
import time
import asyncio
import pytest
import requests
from pymongo import MongoClient

# Use localhost - public preview 502s on long requests
BASE_URL = "http://localhost:8001"
ADMIN_EMAIL = "daniel@wearebudadvisors.com"
ADMIN_PASS = "Thao1971@"
TAB_DIR = "/app/data/muestra_25000"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "arroba_agency_tool")

# Ensure backend imports resolve if we run resolver unit test
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no token in login response: {r.json()}"
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def _run_bootstrap_and_poll(auth_headers, max_wait=600, poll_interval=15):
    """Kick off bootstrap-tab and poll until terminal state."""
    r = requests.post(
        f"{BASE_URL}/api/v1/data-layer/bootstrap-tab",
        json={"directory": TAB_DIR, "rebuild_intelligence": False},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, f"bootstrap-tab start failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    run_id = body.get("run_id")
    assert run_id, f"no run_id: {body}"
    print(f"[bootstrap-tab] run_id={run_id}")

    deadline = time.time() + max_wait
    final = None
    while time.time() < deadline:
        pr = requests.get(
            f"{BASE_URL}/api/v1/data-layer/bootstrap/{run_id}",
            headers=auth_headers,
            timeout=30,
        )
        assert pr.status_code == 200, f"poll failed: {pr.status_code} {pr.text[:200]}"
        data = pr.json()
        status = data.get("status")
        steps = data.get("steps", [])
        step_summary = ", ".join(f"{s.get('step')}:{s.get('status')}" for s in steps)
        print(f"[poll] status={status} steps=[{step_summary}]")
        if status in ("completed", "completed_with_warnings", "failed", "error"):
            final = data
            break
        time.sleep(poll_interval)
    assert final is not None, f"bootstrap did not finish within {max_wait}s"
    return final


class TestBootstrapTabE11000Fix:
    """Primary regression: bootstrap-tab completes with NO E11000."""

    def test_bootstrap_tab_completes_without_e11000(self, auth_headers):
        final = _run_bootstrap_and_poll(auth_headers, max_wait=600, poll_interval=15)

        status = final.get("status")
        steps = final.get("steps", [])
        # Dump for debugging visibility
        for s in steps:
            print(f"  step={s.get('step')} status={s.get('status')} details={str(s)[:400]}")

        assert status in ("completed", "completed_with_warnings"), (
            f"bootstrap-tab did not complete: status={status} steps={steps}"
        )

        # master_builder must be ok (this is where E11000 previously fired)
        master_step = next((s for s in steps if s.get("step") == "master_builder"), None)
        assert master_step is not None, f"master_builder step missing: {steps}"
        assert master_step.get("status") == "ok", (
            f"master_builder step failed (regression!): {master_step}"
        )

        # No step must have status=error, and no step result must contain E11000.
        # NOTE: the run doc may retain a stale top-level `error` field from a prior
        # failed run because _set() uses $set without $unset. That's a minor bug
        # (reported separately) but does NOT reflect the current run's outcome.
        for s in steps:
            assert s.get("status") == "ok", f"step {s.get('step')} not ok: {s}"
            step_str = str(s).lower()
            assert "e11000" not in step_str, f"E11000 inside step result: {s}"
            assert "duplicate key" not in step_str, f"duplicate key in step: {s}"


class TestDataIntegrity:
    def test_master_companies_count(self, mongo_db):
        n = mongo_db.master_companies.count_documents({})
        print(f"master_companies count = {n}")
        assert n >= 25000, f"expected ~25000+ master_companies, got {n}"

    def test_master_id_is_unique(self, mongo_db):
        pipeline = [
            {"$group": {"_id": "$master_id", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
            {"$limit": 5},
        ]
        dups = list(mongo_db.master_companies.aggregate(pipeline))
        assert dups == [], f"duplicate master_id values found: {dups}"

    def test_cif_normalized_is_unique(self, mongo_db):
        pipeline = [
            {"$match": {"cif_normalized": {"$ne": None}}},
            {"$group": {"_id": "$cif_normalized", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
            {"$limit": 5},
        ]
        dups = list(mongo_db.master_companies.aggregate(pipeline))
        assert dups == [], f"duplicate cif_normalized values found: {dups}"

    def test_unique_indexes_exist(self, mongo_db):
        idx = mongo_db.master_companies.index_information()
        # master_id unique
        assert "master_id_1" in idx, f"master_id_1 index missing: {list(idx.keys())}"
        assert idx["master_id_1"].get("unique") is True, f"master_id_1 not unique: {idx['master_id_1']}"
        # cif_normalized unique (may be partial)
        cif_idx = next((k for k in idx if k.startswith("cif_normalized")), None)
        assert cif_idx is not None, f"cif_normalized index missing: {list(idx.keys())}"
        assert idx[cif_idx].get("unique") is True, f"{cif_idx} not unique: {idx[cif_idx]}"


class TestResolverBehavior:
    """Unit test the resolve() fix: CIF-carrying entities never fall through to domain/name."""

    def test_resolver_behavior_combined(self):
        """Combined into one asyncio.run() because motor's db is loop-bound."""
        from services.data_layer.master import entity_resolution as er

        async def _run_all():
            # Case 1: CIF is set, domain and name match existing rows -> must return "new", NOT domain/name match
            fake_cif = "ZZTEST99999999"
            entity_with_cif = {
                "cif_normalized": fake_cif,
                "domain": "oblanca.es",  # a domain we know exists in DB
                "name_key": "cantabrica de piensos",  # existing name_key
                "provincia": "LEON",
            }
            r1 = await er.resolve(entity_with_cif, source="test")

            # Case 2: no CIF at all -> fallback path still reachable, returns "new" for unknown data
            entity_no_cif = {
                "cif_normalized": None,
                "domain": "definitely-not-a-real-domain-xyz-12345.example",
                "name_key": "no_such_entity_xyz_12345",
                "provincia": "MADRID_UNKNOWN_ZONE",
            }
            r2 = await er.resolve(entity_no_cif, source="test")
            return r1, r2

        (mid1, rule1, conf1, created1), (mid2, rule2, conf2, created2) = asyncio.run(_run_all())

        print(f"[with-cif] master_id={mid1}, rule={rule1}, created={created1}")
        print(f"[no-cif]   master_id={mid2}, rule={rule2}, created={created2}")

        # Case 1 assertions: CIF short-circuit MUST fire (regression check for v9 fix)
        assert rule1 == "new", (
            f"REGRESSION: entity with new CIF fell through to '{rule1}' fallback "
            f"(would cause E11000). Expected rule='new'."
        )
        assert conf1 == 1.0
        assert created1 is True
        assert mid1.startswith("mc_")

        # Case 2 assertions: no-CIF path still works (didn't accidentally break fallback)
        assert rule2 == "new"
        assert created2 is True


class TestIdempotency:
    def test_second_bootstrap_no_e11000_and_stable_count(self, auth_headers, mongo_db):
        before = mongo_db.master_companies.count_documents({})
        print(f"master_companies before 2nd bootstrap: {before}")

        final = _run_bootstrap_and_poll(auth_headers, max_wait=600, poll_interval=15)
        status = final.get("status")
        assert status in ("completed", "completed_with_warnings"), f"2nd bootstrap failed: {status}"

        # Verify no E11000 in any step result (stale top-level error field ignored - see note above)
        for s in final.get("steps", []):
            assert s.get("status") == "ok", f"step {s.get('step')} not ok on rerun: {s}"
            step_str = str(s).lower()
            assert "e11000" not in step_str, f"E11000 in step on rerun: {s}"

        after = mongo_db.master_companies.count_documents({})
        print(f"master_companies after 2nd bootstrap: {after}")
        # Should be same or very close (upserts, not inserts)
        assert abs(after - before) <= 5, f"master_companies count changed unexpectedly: {before} -> {after}"
