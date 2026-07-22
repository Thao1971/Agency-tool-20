"""Golden Contract Tests — Data Layer admin endpoints (/api/v1/data-layer/*).

Consumer: Platform Console (JWT). Surface affected by M1 (rebuild-signals depends on the
legacy signal engine). Freezes auth gates + the rebuild-signals + jobs contracts.
"""
import requests
from conftest import (base, assert_json_200, assert_status, require_keys)

D = "/api/v1/data-layer"


# ── Auth gates (cheap; do NOT trigger heavy rebuilds without auth) ──
def test_rebuild_master_requires_auth():
    r = requests.post(f"{base()}{D}/rebuild-master", timeout=30)
    assert r.status_code in (401, 403)


def test_rebuild_embeddings_requires_auth():
    r = requests.post(f"{base()}{D}/rebuild-embeddings", timeout=30)
    assert r.status_code in (401, 403)


def test_rebuild_signals_requires_auth():
    r = requests.post(f"{base()}{D}/rebuild-signals", timeout=30)
    assert r.status_code in (401, 403)


def test_rebuild_graph_requires_auth():
    r = requests.post(f"{base()}{D}/rebuild-graph", timeout=30)
    assert r.status_code in (401, 403)


def test_jobs_list_requires_auth():
    r = requests.get(f"{base()}{D}/jobs", timeout=30)
    assert r.status_code in (401, 403)


# ── M1 SURFACE: POST /rebuild-signals (legacy signal engine) ──
def test_rebuild_signals_contract(auth_headers):
    """Frozen contract: {status:'ok', generated_at, duration_ms, total:int, with_signals:int}.

    This is the exact behavior that M1 must preserve byte-for-byte.
    """
    r = requests.post(f"{base()}{D}/rebuild-signals", headers=auth_headers, timeout=300)
    body = assert_json_200(r)
    require_keys(body, ["status", "generated_at", "duration_ms", "total", "with_signals"])
    assert body["status"] == "ok"
    assert isinstance(body["total"], int) and body["total"] >= 0
    assert isinstance(body["with_signals"], int) and 0 <= body["with_signals"] <= body["total"]


# ── Jobs (light) ──
def test_jobs_list_contract(auth_headers):
    r = requests.get(f"{base()}{D}/jobs?limit=5", headers=auth_headers, timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["jobs"])
    assert isinstance(body["jobs"], list)


def test_job_get_404(auth_headers):
    r = requests.get(f"{base()}{D}/jobs/job_doesnotexist", headers=auth_headers, timeout=30)
    assert_status(r, 404)


def test_job_cancel_unknown_409(auth_headers):
    r = requests.post(f"{base()}{D}/jobs/job_doesnotexist/cancel", headers=auth_headers, timeout=30)
    assert_status(r, 409)
