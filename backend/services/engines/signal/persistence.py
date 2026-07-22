"""Signal persistence & history (D5). Signals are system knowledge from v1.

Persisted in `signals` keyed by (master_id, signal_type, source_version). Maintains
lifecycle (active/resolved/disappeared), first_detected_at, last_seen_at, occurrences,
trend and a history timeline. Enables: when it appeared, how long active, how many
times, whether it worsened, disappeared, and how it evolved.
"""

from typing import Dict, List

from database import db
from models import now_iso

_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    await db.signals.create_index(
        [("master_id", 1), ("signal_type", 1), ("source_version", 1)], unique=True)
    await db.signals.create_index("signal_id")
    await db.signals.create_index([("category", 1), ("dimensions.impact", -1)])
    await db.signals.create_index("master_id")
    _INDEXED = True


def _trend(polarity: str, new_impact: float, old_impact) -> str:
    if old_impact is None:
        return "stable"
    delta = new_impact - old_impact
    if abs(delta) < 0.05:
        return "stable"
    if polarity == "negative":
        return "worsening" if delta > 0 else "improving"
    if polarity == "positive":
        return "improving" if delta > 0 else "worsening"
    return "stable"


async def persist(master_id: str, source_version: str, signals: List[Dict]) -> None:
    """Upsert each detected signal; maintain lifecycle, occurrences and history."""
    await ensure_indexes()
    now = now_iso()
    detected_types = {s["signal_type"] for s in signals}

    for s in signals:
        key = {"master_id": master_id, "signal_type": s["signal_type"],
               "source_version": source_version}
        existing = await db.signals.find_one(key, {"_id": 0, "occurrences": 1,
                                                   "first_detected_at": 1,
                                                   "dimensions": 1, "history": 1})
        polarity = s.get("polarity", "neutral")
        new_impact = (s.get("dimensions") or {}).get("impact", 0.0)
        old_impact = (existing or {}).get("dimensions", {}).get("impact") if existing else None
        hist_entry = {"observed_at": now, "source_version": source_version,
                      "dimensions": s.get("dimensions"), "evidence": s.get("evidence")}
        await db.signals.update_one(
            key,
            {"$set": {**s, "master_id": master_id, "source_version": source_version,
                      "status": "active", "last_seen_at": now,
                      "trend": _trend(polarity, new_impact, old_impact)},
             "$setOnInsert": {"first_detected_at": now},
             "$inc": {"occurrences": 1},
             "$push": {"history": {"$each": [hist_entry], "$slice": -50}}},
            upsert=True,
        )
    # Signals previously active for this source_version but no longer detected → disappeared
    await db.signals.update_many(
        {"master_id": master_id, "source_version": source_version,
         "status": "active", "signal_type": {"$nin": list(detected_types)}},
        {"$set": {"status": "disappeared", "last_seen_at": now}},
    )


async def get_history(master_id: str, signal_type: str = None) -> List[Dict]:
    q = {"master_id": master_id}
    if signal_type:
        q["signal_type"] = signal_type
    out = []
    async for d in db.signals.find(q, {"_id": 0}).sort("first_detected_at", 1):
        out.append({
            "signal_id": d["signal_id"], "signal_type": d["signal_type"],
            "category": d.get("category"), "status": d.get("status"),
            "first_detected_at": d.get("first_detected_at"),
            "last_seen_at": d.get("last_seen_at"),
            "occurrences": d.get("occurrences"), "trend": d.get("trend"),
            "source_version": d.get("source_version"),
            "dimensions": d.get("dimensions"), "timeline": d.get("history", []),
        })
    return out


async def get_signal(signal_id: str) -> Dict:
    return await db.signals.find_one({"signal_id": signal_id}, {"_id": 0})
