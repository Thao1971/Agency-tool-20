"""Service-to-service API key auth (X-API-Key) for engine consumers (e.g. arroba.com).

Reuses the existing `api_keys` collection. Keys are stored hashed (sha256); only the
hash lives in the DB. The raw arroba service key is bootstrapped from env
(ARROBA_SERVICE_API_KEY) and upserted on startup. Boundary First: consumers authenticate
with a service key, not a user JWT.
"""

import os
import hashlib
from datetime import datetime, timezone

from fastapi import Header, HTTPException, status

from database import db
from services.rate_limit import TokenBucketLimiter

SERVICE_NAME = "arroba"
_RATE_PER_MIN = int(os.environ.get("ANALYZE_RATE_LIMIT_PER_MIN", "120"))
limiter = TokenBucketLimiter(capacity=_RATE_PER_MIN, per_seconds=60.0)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def ensure_service_key() -> None:
    """Idempotently upsert the arroba service key from env on startup."""
    raw = os.environ.get("ARROBA_SERVICE_API_KEY")
    if not raw:
        return
    key_hash = _hash(raw)
    await db.api_keys.create_index("key_hash", unique=True)
    await db.api_keys.update_one(
        {"kind": "service", "service_name": SERVICE_NAME},
        {"$set": {"key_hash": key_hash, "prefix": raw[:12], "active": True,
                  "kind": "service", "service_name": SERVICE_NAME, "user_id": None},
         "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def require_service_key(x_api_key: str = Header(None, alias="X-API-Key")) -> dict:
    """FastAPI dependency: validate X-API-Key + apply per-key rate limit."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing X-API-Key", headers={"WWW-Authenticate": "APIKey"})
    key_hash = _hash(x_api_key)
    doc = await db.api_keys.find_one({"key_hash": key_hash, "active": True}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid API key", headers={"WWW-Authenticate": "APIKey"})
    # rate-limit AFTER successful auth (invalid keys aren't counted)
    await limiter.consume(key_hash)
    await db.api_keys.update_one(
        {"key_hash": key_hash},
        {"$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}},
    )
    return doc
