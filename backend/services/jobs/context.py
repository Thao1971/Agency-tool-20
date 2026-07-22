"""JobContext — what a handler receives. Decouples handlers from the queue internals.

Handlers MUST: resume from `ctx.checkpoint`, call `ctx.heartbeat(...)` periodically with
an updated checkpoint, and honor `await ctx.should_cancel()` between batches.
"""

from typing import Dict, Optional

from services.jobs import queue


class JobContext:
    def __init__(self, job: Dict):
        self.job_id: str = job["job_id"]
        self.job_type: str = job["job_type"]
        self.worker_id: str = job["worker_id"]
        self.params: Dict = job.get("params") or {}
        self.checkpoint: Dict = job.get("checkpoint") or {}

    async def heartbeat(self, progress: Optional[Dict] = None, checkpoint: Optional[Dict] = None) -> None:
        if checkpoint is not None:
            self.checkpoint = checkpoint
        await queue.heartbeat(self.job_id, self.worker_id, progress, checkpoint)

    async def should_cancel(self) -> bool:
        return await queue.is_cancel_requested(self.job_id)
