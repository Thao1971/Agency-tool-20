"""Lightweight in-process caches for the semantic search hot path.

- QueryEmbeddingCache: LRU of query → embedding vector. Avoids re-calling OpenAI for
  repeated/popular queries (saves latency + cost + rate-limit pressure).
- ResultCache: LRU + short TTL of (query, limit, section) → search response. Serves
  popular queries instantly.

Both are per-process (each pod keeps its own). No external deps.
"""

import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Optional, Tuple


class _LRU:
    def __init__(self, maxsize: int, ttl: Optional[float] = None):
        self.maxsize = maxsize
        self.ttl = ttl
        self._d: "OrderedDict[Any, Tuple[float, Any]]" = OrderedDict()
        self._lock = Lock()

    def get(self, key) -> Optional[Any]:
        with self._lock:
            item = self._d.get(key)
            if item is None:
                return None
            ts, val = item
            if self.ttl is not None and (time.time() - ts) > self.ttl:
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return val

    def put(self, key, val) -> None:
        with self._lock:
            self._d[key] = (time.time(), val)
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._d), "maxsize": self.maxsize, "ttl": self.ttl}


# query string (normalized) → (vector, model)
query_embedding_cache = _LRU(maxsize=4096)

# (query_norm, limit, section) → search response dict
result_cache = _LRU(maxsize=2048, ttl=60.0)


def qkey(query: str) -> str:
    return " ".join((query or "").lower().split())
