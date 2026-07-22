"""Persistent job worker v2.0 — Multi-consumer with backpressure and memory protection."""

import asyncio
import logging
import os
import psutil
from datetime import datetime, timezone
from database import db

logger = logging.getLogger(__name__)

# Configuration
MAX_CONCURRENT = int(os.environ.get("WORKER_MAX_CONCURRENT", "3"))
POLL_INTERVAL = 3
JOB_TIMEOUT = 90
ZOMBIE_THRESHOLD = 180
HEARTBEAT_INTERVAL = 15

# Backpressure thresholds — based on PROCESS memory and CONTAINER memory
PROCESS_RSS_NORMAL = 1500       # MB — below this: full capacity
PROCESS_RSS_ELEVATED = 2500     # MB — reduce to 2 concurrent
PROCESS_RSS_HIGH = 3500         # MB — reduce to 1 concurrent
PROCESS_RSS_CRITICAL = 4500     # MB — stop accepting

# Container-based thresholds (cgroup)
CONTAINER_PCT_WARN = 80         # % — cap at 2 concurrent
CONTAINER_PCT_CRITICAL = 90     # % — stop accepting

# State
_worker_running = False
_active_jobs = 0
_effective_concurrent = MAX_CONCURRENT
_accepting_new_jobs = True
_backpressure_reason = None


def _get_memory():
    """Get process-level, container-level (cgroup), and host-level memory."""
    host_mem = psutil.virtual_memory()

    # Process tree RSS
    process_rss = 0
    chromium_count = 0
    try:
        proc = psutil.Process()
        process_rss = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                child_info = child.memory_info()
                process_rss += child_info.rss
                if any(x in child.name().lower() for x in ['chrom', 'headless_shell']):
                    chromium_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass

    # Orphan chromium
    try:
        my_children = {c.pid for c in psutil.Process().children(recursive=True)}
        for p in psutil.process_iter(['name']):
            if any(x in p.info['name'].lower() for x in ['chromium', 'headless_shell']) and p.pid not in my_children:
                chromium_count += 1
    except Exception:
        pass

    # Container memory from cgroups v2 (Kubernetes)
    cg_limit = 0
    cg_current = 0
    try:
        with open('/sys/fs/cgroup/memory.max') as f:
            val = f.read().strip()
            cg_limit = int(val) if val != 'max' else 0
        with open('/sys/fs/cgroup/memory.current') as f:
            cg_current = int(f.read().strip())
    except Exception:
        pass

    # If cgroup not available, fall back to host (but flag it)
    if cg_limit > 0:
        container_limit_mb = round(cg_limit / 1024 / 1024)
        container_used_mb = round(cg_current / 1024 / 1024)
        container_available_mb = container_limit_mb - container_used_mb
        container_pct = round(cg_current / cg_limit * 100, 1) if cg_limit > 0 else 0
        cgroup_available = True
    else:
        container_limit_mb = round(host_mem.total / 1024 / 1024)
        container_used_mb = round(host_mem.used / 1024 / 1024)
        container_available_mb = round(host_mem.available / 1024 / 1024)
        container_pct = round(host_mem.percent, 1)
        cgroup_available = False

    return {
        "process_mb": round(process_rss / 1024 / 1024),
        "chromium_count": chromium_count,
        # Container (primary — used for alerts & backpressure)
        "container_limit_mb": container_limit_mb,
        "container_used_mb": container_used_mb,
        "container_available_mb": container_available_mb,
        "container_pct": container_pct,
        "cgroup_available": cgroup_available,
        # Host (secondary — informational only)
        "host_total_mb": round(host_mem.total / 1024 / 1024),
        "host_available_mb": round(host_mem.available / 1024 / 1024),
        "host_pct": round(host_mem.percent, 1),
    }


def _update_backpressure():
    """Backpressure based on process RSS (primary) and container memory (safety net)."""
    global _effective_concurrent, _accepting_new_jobs, _backpressure_reason
    mem = _get_memory()

    process_mb = mem["process_mb"]
    container_pct = mem["container_pct"]

    # Primary signal: process RSS
    if process_mb >= PROCESS_RSS_CRITICAL:
        _effective_concurrent = 0
        _accepting_new_jobs = False
        _backpressure_reason = f"process_critical ({process_mb}MB)"
    elif process_mb >= PROCESS_RSS_HIGH:
        _effective_concurrent = 1
        _accepting_new_jobs = True
        _backpressure_reason = f"process_high ({process_mb}MB)"
    elif process_mb >= PROCESS_RSS_ELEVATED:
        _effective_concurrent = 2
        _accepting_new_jobs = True
        _backpressure_reason = f"process_elevated ({process_mb}MB)"
    else:
        _effective_concurrent = MAX_CONCURRENT
        _accepting_new_jobs = True
        _backpressure_reason = None

    # Secondary safety net: container cgroup memory (overrides only if worse)
    if container_pct >= CONTAINER_PCT_CRITICAL:
        _effective_concurrent = 0
        _accepting_new_jobs = False
        _backpressure_reason = f"container_critical ({container_pct}%)"
    elif container_pct >= CONTAINER_PCT_WARN and _effective_concurrent > 2:
        _effective_concurrent = 2
        _backpressure_reason = _backpressure_reason or f"container_warn ({container_pct}%)"


async def get_worker_status() -> dict:
    _update_backpressure()
    mem = _get_memory()

    pending = await db.analysis_jobs.count_documents({"status": "pending"})
    processing = await db.analysis_jobs.count_documents({"status": {"$in": ["processing", "claimed"]}})

    return {
        "service": "agency-scraper",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),

        "accepting_new_jobs": _accepting_new_jobs,
        "backpressure_reason": _backpressure_reason,

        "worker_running": _worker_running,
        "active_jobs": _active_jobs,
        "max_concurrent": MAX_CONCURRENT,
        "effective_concurrent": _effective_concurrent,
        "available_slots": max(0, _effective_concurrent - _active_jobs),
        "queue_depth": pending,
        "processing": processing,
        "estimated_wait_seconds": pending * 22 // max(1, _effective_concurrent) if _effective_concurrent > 0 else pending * 22,
        "job_timeout_seconds": JOB_TIMEOUT,

        # Container memory (primary — cgroup-based)
        "container_limit_mb": mem["container_limit_mb"],
        "container_used_mb": mem["container_used_mb"],
        "container_available_mb": mem["container_available_mb"],
        "container_memory_pct": mem["container_pct"],
        "cgroup_available": mem["cgroup_available"],

        # Process memory
        "process_memory_mb": mem["process_mb"],
        "chromium_processes": mem["chromium_count"],

        # Host memory (informational only — NOT used for alerts)
        "host_total_mb": mem["host_total_mb"],
        "host_available_mb": mem["host_available_mb"],
        "host_memory_pct": mem["host_pct"],

        # Legacy compat fields (now mapped to container)
        "memory_usage_mb": mem["container_used_mb"],
        "memory_limit_mb": mem["container_limit_mb"],
        "memory_usage_pct": mem["container_pct"],
        "system_available_mb": mem["container_available_mb"],
        "system_memory_pct": mem["container_pct"],
    }


async def start_worker():
    global _worker_running
    if _worker_running:
        return
    _worker_running = True
    logger.info("Worker v2 started (max_concurrent=%d, process_critical=%dMB)", MAX_CONCURRENT, PROCESS_RSS_CRITICAL)
    asyncio.create_task(_worker_loop())


def _kill_orphan_chromium():
    """Kill any orphan chromium/chrome processes not attached to active jobs."""
    killed = 0
    for p in psutil.process_iter(['pid', 'name', 'create_time']):
        try:
            name = p.info['name'].lower()
            if any(x in name for x in ['chromium', 'chrome', 'headless_shell']):
                # Kill if older than 3 minutes (job timeout is 90s)
                import time
                age = time.time() - p.info['create_time']
                if age > 180:
                    p.kill()
                    killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        logger.info(f"Worker: killed {killed} orphan chromium processes")


async def _worker_loop():
    global _worker_running, _active_jobs

    _cleanup_counter = 0

    while _worker_running:
        try:
            _update_backpressure()
            _cleanup_counter += 1

            # Every 20 cycles (~60s): cleanup orphan chromium processes and force GC
            if _cleanup_counter % 20 == 0 and _active_jobs == 0:
                _kill_orphan_chromium()
                import gc
                gc.collect()

            # Zombie detection: jobs claimed/processing without heartbeat > ZOMBIE_THRESHOLD
            now = datetime.now(timezone.utc)
            zombies = await db.analysis_jobs.find(
                {"status": {"$in": ["processing", "claimed"]}, "heartbeat_at": {"$exists": True}},
                {"_id": 0, "id": 1, "heartbeat_at": 1}
            ).to_list(20)
            for z in zombies:
                if z.get("heartbeat_at"):
                    try:
                        hb = datetime.fromisoformat(z["heartbeat_at"])
                        if (now - hb).total_seconds() > ZOMBIE_THRESHOLD:
                            await db.analysis_jobs.update_one(
                                {"id": z["id"]},
                                {"$set": {"status": "pending", "phase": None, "started_at": None, "heartbeat_at": None}}
                            )
                            logger.warning(f"Worker: zombie reset {z['id'][:12]}")
                    except (ValueError, TypeError):
                        pass

            # Also catch jobs stuck without heartbeat_at
            stuck_old = await db.analysis_jobs.find(
                {"status": {"$in": ["processing", "claimed"]}, "heartbeat_at": {"$exists": False}, "started_at": {"$exists": True}},
                {"_id": 0, "id": 1, "started_at": 1}
            ).to_list(20)
            for s in stuck_old:
                if s.get("started_at"):
                    try:
                        started = datetime.fromisoformat(s["started_at"])
                        if (now - started).total_seconds() > ZOMBIE_THRESHOLD:
                            await db.analysis_jobs.update_one(
                                {"id": s["id"]},
                                {"$set": {"status": "pending", "phase": None, "started_at": None}}
                            )
                            logger.warning(f"Worker: stuck reset {s['id'][:12]}")
                    except (ValueError, TypeError):
                        pass

            # Check capacity
            if _active_jobs >= _effective_concurrent or not _accepting_new_jobs:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # Claim a pending job atomically
            job = await db.analysis_jobs.find_one_and_update(
                {"status": "pending"},
                {"$set": {
                    "status": "claimed",
                    "claimed_at": now.isoformat(),
                    "heartbeat_at": now.isoformat()
                }},
                sort=[("created_at", 1)],
                return_document=True
            )

            if not job:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            job_id = str(job["id"])
            url = job["url"]
            consumer = job.get("consumer_id", "direct")
            entity = job.get("entity_id", "-")
            logger.info(f"Worker: claimed {job_id[:12]} | consumer={consumer} | entity={entity} | url={url[:50]}")

            asyncio.create_task(_process_job(job_id, url))

        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


async def _process_job(job_id: str, url: str):
    global _active_jobs
    _active_jobs += 1

    try:
        # Start heartbeat
        heartbeat_task = asyncio.create_task(_heartbeat(job_id))

        from services.orchestrator import run_analysis
        result = await run_analysis(job_id, url)

        heartbeat_task.cancel()

        # Attach consumer metadata and fire callback
        meta = await db.enrichment_metadata.find_one({"job_id": job_id}, {"_id": 0})
        if meta and result:
            update_fields = {
                "consumer_id": meta.get("consumer_id"),
                "environment": meta.get("environment"),
                "entity_id": meta.get("entity_id") or meta.get("cis_company_id"),
                "profile_id": meta.get("profile_id"),
                "cis_company_id": meta.get("cis_company_id") or meta.get("entity_id"),
                "cif": meta.get("cif"),
                "cif_normalized": meta.get("cif_normalized"),
                "enrichment_source": meta.get("consumer_id", "direct"),
                "requested_fields": meta.get("requested_fields", []),
            }
            if meta.get("callback_url"):
                update_fields["callback_url"] = meta["callback_url"]
                update_fields["callback_status"] = "pending"

            await db.agency_results.update_one(
                {"id": result["id"]},
                {"$set": update_fields}
            )

            if meta.get("callback_url"):
                from services.enrichment_helpers import fire_enrichment_callback
                await fire_enrichment_callback(result["id"])

        # Intelligence Engine post-link: if the job was queued by the engine,
        # link the resulting agency_result back to the master_company.
        try:
            job_doc = await db.analysis_jobs.find_one({"id": job_id}, {"_id": 0, "metadata": 1, "consumer_id": 1})
            mc_id = (job_doc or {}).get("metadata", {}).get("master_company_id") if job_doc else None
            if mc_id and result:
                from services.intelligence_engine.linker import link_one
                full_ar = await db.agency_results.find_one({"id": result["id"]}, {"_id": 0})
                if full_ar:
                    await link_one(full_ar, mc_id)
                    logger.info(f"Intelligence Engine: linked agency_result {result['id'][:12]} → master {mc_id}")
        except Exception as e:
            logger.warning(f"Intelligence Engine post-link failed for job {job_id[:12]}: {e}")

        logger.info(f"Worker: completed {job_id[:12]}")

    except Exception as e:
        logger.error(f"Worker: job {job_id[:12]} failed: {e}")
    finally:
        _active_jobs -= 1


async def _heartbeat(job_id: str):
    while True:
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await db.analysis_jobs.update_one(
                {"id": job_id},
                {"$set": {"heartbeat_at": datetime.now(timezone.utc).isoformat()}}
            )
        except asyncio.CancelledError:
            break
        except Exception:
            pass


async def stop_worker():
    global _worker_running
    _worker_running = False
    logger.info("Worker stopped")
