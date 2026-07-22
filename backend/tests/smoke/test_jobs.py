"""Smoke tests — P0.2 generic job infrastructure (data_layer_jobs).

Worker is paused for this module so the runner is driven deterministically in-process.
Covers: enqueue, atomic claim, completion+checkpoint, cancellation, stale recovery,
requeue-then-fail, ingest handler via the generic runner, and checkpoint resume.
The live separate-worker e2e (API enqueue → worker completes) is validated separately.
"""
import os
import asyncio
import subprocess
import requests
import pytest
from smoke_loop import run_async as _run

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"
JOBS = "/api/v1/data-layer/jobs"


@pytest.fixture(scope="module", autouse=True)
def _pause_worker():
    subprocess.run(["sudo", "supervisorctl", "stop", "data_layer_worker"], capture_output=True)
    # register in-test handlers + the real ones
    from services.jobs import registry
    import services.jobs.handlers  # noqa: F401  (registers ingest_iberinform)

    async def _ok(ctx):
        await ctx.heartbeat(progress={"processed": 1}, checkpoint={"step": "done"})
        return {"ok": True, "echo": ctx.params.get("x")}

    async def _raise(ctx):
        raise RuntimeError("boom")

    registry.register("test_ok", _ok)
    registry.register("test_raise", _raise)
    yield
    subprocess.run(["sudo", "supervisorctl", "start", "data_layer_worker"], capture_output=True)


@pytest.fixture(autouse=True)
def _clean_queue(_pause_worker):
    async def _c():
        from database import db
        await db.data_layer_jobs.delete_many({})
    _run(_c())
    yield


def test_enqueue_and_get():
    from services.jobs import queue

    async def go():
        jid = await queue.enqueue("test_ok", {"x": 7})
        doc = await queue.get(jid)
        return doc

    doc = _run(go())
    assert doc["status"] == "queued" and doc["params"]["x"] == 7
    assert doc["attempts"] == 0 and doc["max_attempts"] >= 1


def test_claim_is_atomic():
    from services.jobs import queue

    async def go():
        jid = await queue.enqueue("test_ok", {}, priority=100)
        a = await queue.claim_next("w1")
        b = await queue.claim_next("w2")  # must NOT get the same job
        return jid, a, b

    jid, a, b = _run(go())
    assert a is not None and a["job_id"] == jid and a["status"] == "running"
    assert (b is None) or (b["job_id"] != jid)


def test_process_one_completes_with_checkpoint():
    from services.jobs import queue
    from services.jobs.runner import JobRunner

    async def go():
        jid = await queue.enqueue("test_ok", {"x": 42})
        await JobRunner("wA").process_one()
        return await queue.get(jid)

    doc = _run(go())
    assert doc["status"] == "completed"
    assert doc["result"]["echo"] == 42
    assert doc["checkpoint"] == {"step": "done"}


def test_cancellation_before_run():
    from services.jobs import queue
    from services.jobs.runner import JobRunner

    async def go():
        jid = await queue.enqueue("test_ok", {})
        await queue.request_cancel(jid)
        await JobRunner("wB").process_one()
        return await queue.get(jid)

    doc = _run(go())
    assert doc["status"] == "cancelled"


def test_stale_recovery():
    from services.jobs import queue
    from models import now_iso

    async def go():
        jid = await queue.enqueue("test_ok", {})
        await queue.claim_next("dead-worker")          # -> running
        # force an old heartbeat
        from database import db
        await db.data_layer_jobs.update_one(
            {"job_id": jid}, {"$set": {"heartbeat_at": "2000-01-01T00:00:00+00:00"}})
        rec = await queue.recover_stale(stale_seconds=1)
        return jid, rec, await queue.get(jid)

    jid, rec, doc = _run(go())
    assert rec["requeued"] >= 1
    assert doc["status"] == "queued" and doc["worker_id"] is None


def test_requeue_then_fail():
    from services.jobs import queue
    from services.jobs.runner import JobRunner

    async def go():
        jid = await queue.enqueue("test_raise", {})
        runner = JobRunner("wC")
        statuses = []
        for _ in range(3):
            await runner.process_one()
            d = await queue.get(jid)
            statuses.append(d["status"])
            if d["status"] == "queued":
                continue
        return jid, statuses, await queue.get(jid)

    jid, statuses, doc = _run(go())
    assert statuses[0] == "queued"          # first failure requeues
    assert doc["status"] == "failed"        # exhausts max_attempts
    assert "boom" in (doc["error"] or "")


def test_ingest_handler_via_runner():
    if not os.path.isdir(SAMPLE_DIR):
        pytest.skip("sample fixture missing")
    from services.jobs import queue
    from services.jobs.runner import JobRunner
    from database import db

    async def go():
        for c in ["norm_company", "norm_financials", "norm_ownership", "norm_officers"]:
            await db[c].delete_many({})
        jid = await queue.enqueue("ingest_iberinform",
                                  {"directory": SAMPLE_DIR, "source_version": "20260519"})
        await JobRunner("wD").process_one()
        doc = await queue.get(jid)
        comp = await db.norm_company.count_documents({})
        return doc, comp

    doc, comp = _run(go())
    assert doc["status"] == "completed"
    assert doc["result"]["files_total"] == 8 and doc["result"]["files_done"] == 8
    assert comp >= 900


def test_ingest_resume_skips_completed_files():
    if not os.path.isdir(SAMPLE_DIR):
        pytest.skip("sample fixture missing")
    from services.jobs import queue
    from services.jobs.runner import JobRunner
    from services.data_layer.ingestion.iberinform_ingest import list_ingestable
    from database import db

    async def go():
        await db.norm_company.delete_many({})
        all_files = list_ingestable(SAMPLE_DIR)
        jid = await queue.enqueue("ingest_iberinform",
                                  {"directory": SAMPLE_DIR, "source_version": "20260519"})
        # simulate a prior run that already finished every file
        await db.data_layer_jobs.update_one(
            {"job_id": jid}, {"$set": {"checkpoint": {"completed_files": all_files, "results": []}}})
        await JobRunner("wE").process_one()
        doc = await queue.get(jid)
        comp = await db.norm_company.count_documents({})
        return doc, comp, len(all_files)

    doc, comp, n = _run(go())
    assert doc["status"] == "completed"
    assert doc["result"]["files_done"] == n
    assert comp == 0   # all files were skipped → nothing re-ingested


# ── API contract (enqueue/query/cancel only; no execution here) ──
def test_jobs_endpoint_requires_auth(base_url):
    r = requests.post(f"{base_url}{JOBS}", json={"job_type": "test_ok"}, timeout=20)
    assert r.status_code in (401, 403)


def test_create_query_cancel_via_api(base_url, auth_token):
    h = {"Authorization": f"Bearer {auth_token}"}
    r = requests.post(f"{base_url}{JOBS}", headers=h,
                      json={"job_type": "test_ok", "params": {"x": 1}}, timeout=20)
    assert r.status_code == 200
    jid = r.json()["job_id"]
    assert r.json()["status"] == "queued"

    g = requests.get(f"{base_url}{JOBS}/{jid}", headers=h, timeout=20)
    assert g.status_code == 200 and g.json()["job_id"] == jid

    c = requests.post(f"{base_url}{JOBS}/{jid}/cancel", headers=h, timeout=20)
    assert c.status_code == 200 and c.json()["cancel_requested"] is True

    nf = requests.get(f"{base_url}{JOBS}/does-not-exist", headers=h, timeout=20)
    assert nf.status_code == 404
