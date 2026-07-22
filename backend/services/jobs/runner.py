"""Generic JobRunner — claims jobs from the queue and runs their registered handler.

Knows nothing about any specific pipeline. `process_one` is unit-testable; `run_forever`
is the worker loop (periodic stale-recovery + claim/run/sleep).
"""

import asyncio
import logging
import traceback
from typing import Optional

from services.jobs import queue, registry
from services.jobs.context import JobContext

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id

    async def process_one(self) -> Optional[str]:
        job = await queue.claim_next(self.worker_id)
        if not job:
            return None
        job_id = job["job_id"]
        handler = registry.get_handler(job["job_type"])
        if handler is None:
            await queue.fail(job_id, f"no handler registered for '{job['job_type']}'", allow_requeue=False)
            return job_id
        ctx = JobContext(job)
        try:
            if await ctx.should_cancel():
                await queue.mark_cancelled(job_id)
                return job_id
            result = await handler(ctx)
            if await ctx.should_cancel():
                await queue.mark_cancelled(job_id, result)
            else:
                await queue.complete(job_id, result)
        except Exception as e:
            logger.error(f"job {job_id} ({job['job_type']}) failed: {e}\n{traceback.format_exc()}")
            await queue.fail(job_id, f"{type(e).__name__}: {e}")
        return job_id

    async def run_forever(self, poll_interval: float = 2.0, recovery_interval: float = 60.0) -> None:
        logger.info(f"JobRunner {self.worker_id} started; handlers={registry.registered_types()}")
        loop = asyncio.get_event_loop()
        last_recovery = 0.0
        while True:
            try:
                now = loop.time()
                if now - last_recovery >= recovery_interval:
                    rec = await queue.recover_stale()
                    if rec["requeued"] or rec["failed"]:
                        logger.info(f"stale recovery: {rec}")
                    last_recovery = now
                processed = await self.process_one()
                if processed is None:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error(f"runner loop error: {e}")
                await asyncio.sleep(poll_interval)
