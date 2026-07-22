"""Recommendation Memory (DR9) + Feedback Loop (DR10).

Memory: lifecycle of each recommendation (proposed→accepted/rejected/ignored→
converted_to_opportunity/deal→outcome). Built as KNOWLEDGE for future recommendations
and consumed later by Strategy. Feedback: explicit events recorded as EVIDENCE for
future recalibration (does NOT mutate rules directly).
"""

from typing import Dict, List, Optional

from database import db
from models import now_iso

LIFECYCLE_STATES = ["proposed", "accepted", "rejected", "ignored",
                    "converted_to_opportunity", "converted_to_deal", "outcome"]
FEEDBACK_EVENTS = ["accepted", "rejected", "ended_in_acquisition",
                   "ended_in_failure", "never_executed"]

_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    await db.recommendation_memory.create_index("recommendation_id", unique=True)
    await db.recommendation_memory.create_index("target_master_id")
    await db.recommendation_memory.create_index("state")
    await db.recommendation_feedback.create_index("recommendation_id")
    _INDEXED = True


async def record_decision(rec: Dict, state: str) -> Dict:
    """Persist only meaningful states (DR3): accepted/rejected/converted*/outcome."""
    await ensure_indexes()
    if state not in LIFECYCLE_STATES:
        raise ValueError(f"invalid state: {state}")
    now = now_iso()
    rid = rec["recommendation_id"]
    await db.recommendation_memory.update_one(
        {"recommendation_id": rid},
        {"$set": {"recommendation_id": rid, "state": state,
                  "target_master_id": (rec.get("target") or {}).get("master_id"),
                  "candidate_master_id": (rec.get("candidate") or {}).get("master_id"),
                  "recommendation_type": rec.get("recommendation_type"),
                  "recommendation_role": rec.get("recommendation_role"),
                  "score": rec.get("score"), "fit_dimensions": rec.get("fit_dimensions"),
                  "updated_at": now},
         "$setOnInsert": {"created_at": now, "recommendation_snapshot": rec},
         "$push": {"timeline": {"state": state, "at": now}}},
        upsert=True,
    )
    return await db.recommendation_memory.find_one({"recommendation_id": rid}, {"_id": 0})


async def record_feedback(recommendation_id: str, event: str,
                          outcome: Optional[str] = None, notes: Optional[str] = None) -> Dict:
    await ensure_indexes()
    if event not in FEEDBACK_EVENTS:
        raise ValueError(f"invalid feedback event: {event}")
    now = now_iso()
    doc = {"recommendation_id": recommendation_id, "event": event,
           "outcome": outcome, "notes": notes, "recorded_at": now}
    await db.recommendation_feedback.insert_one(dict(doc))
    # mirror lifecycle state in memory (evidence only; rules unchanged)
    state_map = {"accepted": "accepted", "rejected": "rejected",
                 "ended_in_acquisition": "converted_to_deal",
                 "ended_in_failure": "outcome", "never_executed": "ignored"}
    state = state_map.get(event)
    if state:
        await db.recommendation_memory.update_one(
            {"recommendation_id": recommendation_id},
            {"$set": {"state": state, "updated_at": now},
             "$push": {"timeline": {"state": state, "at": now, "feedback": event}}},
            upsert=True,
        )
    return {"recorded": True, **doc}


async def query_memory(target: Optional[str] = None, recommendation_id: Optional[str] = None,
                       state: Optional[str] = None) -> List[Dict]:
    q: Dict = {}
    if recommendation_id:
        q["recommendation_id"] = recommendation_id
    if target:
        q["target_master_id"] = target
    if state:
        q["state"] = state
    out = []
    async for d in db.recommendation_memory.find(q, {"_id": 0, "recommendation_snapshot": 0}).limit(200):
        out.append(d)
    return out
