"""Analyze cache + telemetry (P2 hardening).

Cache key = sha256(master_company_id | include_narrative | data_version), where
data_version derives from the master record's mutable timestamps + an ANALYZE_VERSION
bump. Avoids repeated Claude calls. TTL configurable via ANALYZE_CACHE_TTL_SECONDS.

Telemetry persisted to `analyze_metrics` (one doc per call): latency, cache hit,
tokens, estimated cost, Claude errors, retries. No new public API — read from DB/logs.
"""

import os
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from database import db
from models import now_iso

logger = logging.getLogger(__name__)

ANALYZE_VERSION = "analyze-v1"
TTL_SECONDS = int(os.environ.get("ANALYZE_CACHE_TTL_SECONDS", "86400"))
COST_PER_1K = float(os.environ.get("ANALYZE_CLAUDE_COST_PER_1K_TOKENS", "0.009"))

_indexes_ready = False


async def ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    await db.analyze_cache.create_index("cache_key", unique=True)
    # Mongo TTL: auto-evict expired entries
    await db.analyze_cache.create_index("expires_at", expireAfterSeconds=0)
    await db.analyze_metrics.create_index("created_at")
    _indexes_ready = True


def data_version(doc: Dict) -> str:
    parts = [str(doc.get(k)) for k in ("updated_at", "signals_updated_at", "last_enriched_at")]
    return "|".join(parts) + "|" + ANALYZE_VERSION


def cache_key(master_company_id: str, include_narrative: bool, dv: str) -> str:
    raw = f"{master_company_id}|{int(include_narrative)}|{dv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_cached(key: str) -> Optional[Dict]:
    doc = await db.analyze_cache.find_one({"cache_key": key}, {"_id": 0})
    if not doc:
        return None
    exp = doc.get("expires_at")
    # defensive: honor TTL even before Mongo's background sweep (Mongo may return naive UTC)
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            return None
    return doc.get("payload")


async def set_cached(key: str, payload: Dict) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TTL_SECONDS)
    await db.analyze_cache.update_one(
        {"cache_key": key},
        {"$set": {"cache_key": key, "payload": payload,
                  "cached_at": now_iso(), "expires_at": expires_at}},
        upsert=True,
    )


def estimate_tokens(text: str) -> int:
    # ~4 chars/token heuristic (no usage object from the chat wrapper)
    return max(0, len(text or "") // 4)


async def record_metric(*, master_company_id: str, include_narrative: bool, cache_hit: bool,
                        latency_ms: float, tokens: int = 0, claude_error: bool = False,
                        retries: int = 0) -> None:
    try:
        await db.analyze_metrics.insert_one({
            "master_company_id": master_company_id,
            "include_narrative": include_narrative,
            "cache_hit": cache_hit,
            "latency_ms": round(latency_ms, 1),
            "tokens": tokens,
            "estimated_cost_usd": round(tokens / 1000 * COST_PER_1K, 6),
            "claude_error": claude_error,
            "retries": retries,
            "created_at": now_iso(),
        })
    except Exception as e:  # telemetry must never break the request
        logger.warning(f"analyze metric persist failed: {e}")
