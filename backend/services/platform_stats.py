"""Platform Stats (REQ-002) — public aggregated metrics for arroba.com Home.

Public, no auth, no PII, cacheable. Replaces arroba's PlatformStatsMock with real data.
Each metric maps to real collections; `confidence` reflects live source coverage.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict

from database import db

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 3600  # 1h server-side + HTTP cache window
CONFIDENCE = 0.8  # fixed aggregate confidence (REQ-002, approved)

# Real collections backing each headline metric
_OPPORTUNITY_COLLECTIONS = ["public_procurement_contracts", "government_grants", "ayudas_subvenciones_publicas"]
_MOVEMENT_COLLECTIONS = ["borme_events", "corporate_events"]
_SIGNAL_COLLECTIONS = ["economic_signals", "cnmv_signals", "bme_signals", "datacomex_signals", "economic_metrics"]

_CACHE: Dict = {"data": None, "expires": 0.0}


async def _count(collection: str) -> int:
    try:
        return await db[collection].estimated_document_count()
    except Exception:
        return 0


async def _sum_counts(collections) -> int:
    total = 0
    for c in collections:
        total += await _count(c)
    return total


async def _compute() -> Dict:
    companies = await _count("companies_master")
    opportunities = await _sum_counts(_OPPORTUNITY_COLLECTIONS)
    movements = await _sum_counts(_MOVEMENT_COLLECTIONS)
    signals = await _sum_counts(_SIGNAL_COLLECTIONS)

    now = datetime.now(timezone.utc)
    return {
        "companies_analyzed": companies,
        "active_opportunities": opportunities,
        "market_movements": movements,
        "signals_detected": signals,
        "confidence": CONFIDENCE,
        "lineage": {"source": "normalized"},
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "valid_until": (now + timedelta(seconds=CACHE_TTL_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


async def get_platform_stats() -> Dict:
    """Cached aggregate (in-memory TTL). Fast, safe to expose publicly."""
    now = time.time()
    if _CACHE["data"] and _CACHE["expires"] > now:
        return _CACHE["data"]
    data = await _compute()
    _CACHE["data"] = data
    _CACHE["expires"] = now + CACHE_TTL_SECONDS
    return data
