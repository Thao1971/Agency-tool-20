"""MongoDB-backed job queue (`data_layer_jobs`).

Atomic claim via find_one_and_update so multiple workers can consume the same queue
safely. Heartbeat + stale recovery + checkpoints + cancellation. Contract is generic.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from pymongo import ReturnDocument

from database import db
from models import now_iso

STALE_SECONDS = int(os.environ.get("JOB_HEARTBEAT_STALE_SECONDS", "120"))
MAX_ATTEMPTS = int(os.environ.get("JOB_MAX_ATTEMPTS", "3"))

TERMINAL = {"completed", "failed", "cancelled"}


async def ensure_indexes() -> None:
    await db.data_layer_jobs.create_index("job_id", unique=True)
    await db.data_layer_jobs.create_index([("status", 1), ("priority", -1), ("created_at", 1)])
    await db.data_layer_jobs.create_index("heartbeat_at")


async def enqueue(job_type: str, params: Optional[Dict] = None,
                  pipeline_version: Optional[str] = None, priority: int = 0) -> str:
    job_id = str(uuid.uuid4())
    now = now_iso()
    await db.data_layer_jobs.insert_one({
        "job_id": job_id, "job_type": job_type, "status": "queued",
        "params": params or {}, "priority": priority,
        "checkpoint": {}, "progress": {"processed": 0, "failed": 0, "total_estimated": None, "message": None},
        "pipeline_version": pipeline_version, "source_hash": None,
        "worker_id": None, "heartbeat_at": None,
        "attempts": 0, "max_attempts": MAX_ATTEMPTS, "cancel_requested": False,
        "error": None, "result": None,
        "created_at": now, "started_at": None, "finished_at": None, "updated_at": now,
    })
    return job_id


async def claim_next(worker_id: str) -> Optional[Dict]:
    """Atomically claim the highest-priority queued job (multi-worker safe)."""
    now = now_iso()
    return await db.data_layer_jobs.find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "running", "worker_id": worker_id,
                  "started_at": now, "heartbeat_at": now, "updated_at": now},
         "$inc": {"attempts": 1}},
        sort=[("priority", -1), ("created_at", 1)],
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )


async def heartbeat(job_id: str, worker_id: str,
                    progress: Optional[Dict] = None, checkpoint: Optional[Dict] = None) -> None:
    upd = {"heartbeat_at": now_iso(), "updated_at": now_iso()}
    if progress is not None:
        upd["progress"] = progress
    if checkpoint is not None:
        upd["checkpoint"] = checkpoint
    await db.data_layer_jobs.update_one({"job_id": job_id, "worker_id": worker_id}, {"$set": upd})


async def complete(job_id: str, result: Optional[Dict] = None) -> None:
    await db.data_layer_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "completed", "result": result, "error": None,
                  "finished_at": now_iso(), "updated_at": now_iso()}})


async def mark_cancelled(job_id: str, result: Optional[Dict] = None) -> None:
    await db.data_layer_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "cancelled", "result": result,
                  "finished_at": now_iso(), "updated_at": now_iso()}})


async def fail(job_id: str, error: str, allow_requeue: bool = True) -> str:
    """Requeue if attempts remain, else mark failed. Returns final status."""
    job = await db.data_layer_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        return "missing"
    if allow_requeue and job.get("attempts", 0) < job.get("max_attempts", MAX_ATTEMPTS):
        await db.data_layer_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "queued", "worker_id": None, "heartbeat_at": None,
                      "error": error, "updated_at": now_iso()}})
        return "queued"
    await db.data_layer_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "failed", "error": error,
                  "finished_at": now_iso(), "updated_at": now_iso()}})
    return "failed"


async def request_cancel(job_id: str) -> bool:
    res = await db.data_layer_jobs.update_one(
        {"job_id": job_id, "status": {"$nin": list(TERMINAL)}},
        {"$set": {"cancel_requested": True, "updated_at": now_iso()}})
    return res.modified_count > 0


async def is_cancel_requested(job_id: str) -> bool:
    doc = await db.data_layer_jobs.find_one({"job_id": job_id}, {"_id": 0, "cancel_requested": 1})
    return bool(doc and doc.get("cancel_requested"))


async def recover_stale(stale_seconds: int = STALE_SECONDS) -> Dict:
    """Requeue (or fail) running jobs whose heartbeat is older than the threshold."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)).isoformat()
    requeued = failed = 0
    async for job in db.data_layer_jobs.find(
            {"status": "running", "heartbeat_at": {"$lt": cutoff}}, {"_id": 0}):
        status = await fail(job["job_id"], "stale heartbeat (worker died)", allow_requeue=True)
        if status == "queued":
            requeued += 1
        else:
            failed += 1
    return {"requeued": requeued, "failed": failed}


async def get(job_id: str) -> Optional[Dict]:
    return await db.data_layer_jobs.find_one({"job_id": job_id}, {"_id": 0})


async def list_recent(limit: int = 20) -> list:
    return await db.data_layer_jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
