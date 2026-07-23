"""Signal persistence & history (D5). Signals are system knowledge from v1.

Persisted in `signals` keyed by (master_id, signal_type) — NOT source_version (fixed
2026-07-23; see migrate_dedupe_and_reindex() below for why and how existing duplicates
from before this fix are reconciled). Maintains lifecycle (active/resolved/disappeared),
first_detected_at, last_seen_at, occurrences, trend and a history timeline. Enables:
when it appeared, how long active, how many times, whether it worsened, disappeared, and
how it evolved — genuinely across monthly deliveries, not just within a single re-run of
the same delivery.
"""

from typing import Dict, List

from database import db
from models import now_iso

_INDEXED = False

_OLD_INDEX_NAME = "master_id_1_signal_type_1_source_version_1"


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    try:
        await db.signals.create_index([("master_id", 1), ("signal_type", 1)], unique=True)
    except Exception:  # noqa: BLE001 — a DB deployed before this fix may still have
        # duplicate (master_id, signal_type) docs under different source_versions (the
        # exact bug this fix addresses). Building the new unique index over them fails
        # until migrate_dedupe_and_reindex() runs once. Never let that crash every write —
        # persist() still works (just without the new uniqueness guarantee) until then.
        pass
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
    """Upsert each detected signal; maintain lifecycle, occurrences and history.

    Keyed by (master_id, signal_type) only — re-detecting the same signal_type in a later
    delivery (different source_version) updates the SAME document instead of creating a
    new one, so first_detected_at/occurrences/trend genuinely span the company's history
    across monthly deliveries, not just re-runs of one delivery."""
    await ensure_indexes()
    now = now_iso()
    detected_types = {s["signal_type"] for s in signals}

    for s in signals:
        key = {"master_id": master_id, "signal_type": s["signal_type"]}
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
    # Signals previously active for this company but no longer detected → disappeared.
    # Deliberately NOT scoped to source_version anymore: a signal from an older delivery
    # that isn't re-detected today must close out regardless of which version last
    # confirmed it (that was the bug — this used to only compare within one delivery).
    await db.signals.update_many(
        {"master_id": master_id, "status": "active", "signal_type": {"$nin": list(detected_types)}},
        {"$set": {"status": "disappeared", "last_seen_at": now, "source_version": source_version}},
    )


async def migrate_dedupe_and_reindex() -> Dict:
    """One-time migration for databases that ran under the pre-2026-07-23 keying
    ((master_id, signal_type, source_version)). Every prior monthly delivery left its own
    copy of each recurring signal, all still "active" — this collapses each
    (master_id, signal_type) group down to one document and then builds the new unique
    index, so it's safe to run exactly once, before the next delivery. Idempotent: running
    it again with no duplicates left is a no-op.

    For each group with duplicates: keeps the doc with the latest last_seen_at as the
    winner (reflects the most recent delivery's view of the signal), but reconstructs
    first_detected_at as the MIN across all duplicates (recovering the true original
    detection date the bug had fragmented) and occurrences as the SUM. Never invents data —
    only merges values that were already real, previously-persisted signal documents."""
    groups: Dict[tuple, List[Dict]] = {}
    async for doc in db.signals.find({}, {"_id": 0}):
        groups.setdefault((doc["master_id"], doc["signal_type"]), []).append(doc)

    merged = 0
    deleted = 0
    for (master_id, signal_type), docs in groups.items():
        if len(docs) <= 1:
            continue
        docs.sort(key=lambda d: d.get("last_seen_at") or "")
        winner = docs[-1]
        losers = docs[:-1]

        first_detected_at = min(
            (d.get("first_detected_at") for d in docs if d.get("first_detected_at")), default=None)
        occurrences = sum(d.get("occurrences") or 0 for d in docs)
        history = []
        for d in docs:
            history.extend(d.get("history") or [])
        history.sort(key=lambda h: h.get("observed_at") or "")
        history = history[-50:]

        await db.signals.update_one(
            {"signal_id": winner["signal_id"]},
            {"$set": {"first_detected_at": first_detected_at, "occurrences": occurrences,
                      "history": history}},
        )
        loser_ids = [d["signal_id"] for d in losers]
        if loser_ids:
            res = await db.signals.delete_many({"signal_id": {"$in": loser_ids}})
            deleted += res.deleted_count
        merged += 1

    try:
        await db.signals.drop_index(_OLD_INDEX_NAME)
    except Exception:  # noqa: BLE001 — fine if it never existed (fresh DB) or was already dropped
        pass
    await db.signals.create_index([("master_id", 1), ("signal_type", 1)], unique=True)

    return {"status": "completed", "groups_merged": merged, "documents_deleted": deleted}


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
