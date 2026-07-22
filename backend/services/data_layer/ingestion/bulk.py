"""Chunked, order-independent bulk upserter (bulk_write ordered=False).

Buffers UpdateOne(upsert=True) ops and flushes in fixed-size batches so RAM stays O(batch)
regardless of total volume. Idempotent: re-running upserts by natural key is a no-op.
"""

import logging
from typing import Dict, List

from pymongo import UpdateOne

from models import now_iso

logger = logging.getLogger(__name__)

DEFAULT_BATCH = 2000


class BulkUpserter:
    def __init__(self, collection, batch_size: int = DEFAULT_BATCH):
        self.collection = collection
        self.batch_size = batch_size
        self._ops: List[UpdateOne] = []
        self.upserted = 0
        self.modified = 0
        self.queued = 0

    def upsert(self, key: Dict, doc: Dict) -> None:
        payload = {**doc}
        payload.pop("created_at", None)
        self._ops.append(UpdateOne(
            key,
            {"$set": payload, "$setOnInsert": {"created_at": now_iso()}},
            upsert=True,
        ))
        self.queued += 1
        if len(self._ops) >= self.batch_size:
            # caller must await flush(); we expose a sync guard count
            pass

    async def maybe_flush(self) -> None:
        if len(self._ops) >= self.batch_size:
            await self.flush()

    async def flush(self) -> None:
        if not self._ops:
            return
        res = await self.collection.bulk_write(self._ops, ordered=False)
        self.upserted += res.upserted_count
        self.modified += res.modified_count
        self._ops = []

    def stats(self) -> Dict:
        return {"queued": self.queued, "upserted": self.upserted, "modified": self.modified}
