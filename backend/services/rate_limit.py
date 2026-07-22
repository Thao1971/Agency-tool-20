"""In-process per-key token-bucket rate limiter (single uvicorn worker).

Resets on restart and is per-process — acceptable for the current single-instance
deployment. Move to Redis if the backend ever scales to multiple workers/pods.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict

from fastapi import HTTPException, status


@dataclass
class _Bucket:
    tokens: float
    last: float


class TokenBucketLimiter:
    def __init__(self, capacity: int, per_seconds: float = 60.0):
        self.capacity = max(1, capacity)
        self.refill_per_second = self.capacity / per_seconds
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def consume(self, key: str) -> Dict[str, int]:
        now = time.monotonic()
        async with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = _Bucket(tokens=self.capacity, last=now)
            else:
                elapsed = now - b.last
                b.tokens = min(self.capacity, b.tokens + elapsed * self.refill_per_second)
                b.last = now
            if b.tokens < 1:
                retry_after = max(1, int((1 - b.tokens) / self.refill_per_second))
                self._buckets[key] = b
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            b.tokens -= 1
            self._buckets[key] = b
            return {"limit": self.capacity, "remaining": int(b.tokens)}
