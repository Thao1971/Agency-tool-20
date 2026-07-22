"""Strategy Memory + canonical Strategic Thesis persistence (DT4/DT14/DT15).

Theses live as INDEPENDENT entities in `strategic_theses` (not ephemeral API responses).
Lifecycle states tracked; thesis can convert to Opportunity/Mandate/Transaction without
rebuilding the reasoning.
"""
from typing import Dict, List, Optional

from database import db
from models import now_iso

LIFECYCLE_STATES = ["proposed", "validated", "rejected", "executing", "completed", "abandoned"]
CONVERT_TARGETS = ["opportunity", "mandate", "transaction"]

_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    await db.strategic_theses.create_index("thesis_id", unique=True)
    await db.strategic_theses.create_index("company_master_id")
    await db.strategic_theses.create_index("thesis_type")
    await db.strategic_theses.create_index("lifecycle.state")
    _INDEXED = True


async def save(thesis: Dict) -> Dict:
    await ensure_indexes()
    now = now_iso()
    tid = thesis["thesis_id"]
    await db.strategic_theses.update_one(
        {"thesis_id": tid},
        {"$set": {**thesis, "updated_at": now},
         "$setOnInsert": {"created_at": now,
                          "lifecycle": {"state": "proposed", "result": None,
                                        "result_date": None, "learning": None,
                                        "timeline": [{"state": "proposed", "at": now}]}}},
        upsert=True,
    )
    return await db.strategic_theses.find_one({"thesis_id": tid}, {"_id": 0})


async def update_lifecycle(thesis_id: str, state: str, result: Optional[str] = None,
                           learning: Optional[str] = None) -> Optional[Dict]:
    if state not in LIFECYCLE_STATES:
        raise ValueError(f"invalid lifecycle state: {state}")
    now = now_iso()
    res = await db.strategic_theses.update_one(
        {"thesis_id": thesis_id},
        {"$set": {"lifecycle.state": state, "lifecycle.result": result,
                  "lifecycle.result_date": now if result else None,
                  "lifecycle.learning": learning, "status": "available", "updated_at": now},
         "$push": {"lifecycle.timeline": {"state": state, "at": now}}},
    )
    if res.matched_count == 0:
        return None
    return await db.strategic_theses.find_one({"thesis_id": thesis_id}, {"_id": 0})


async def convert(thesis_id: str, target: str) -> Optional[Dict]:
    if target not in CONVERT_TARGETS:
        raise ValueError(f"invalid convert target: {target}")
    now = now_iso()
    res = await db.strategic_theses.update_one(
        {"thesis_id": thesis_id},
        {"$set": {"converts_to": target, "updated_at": now},
         "$push": {"lifecycle.timeline": {"state": f"converted_to_{target}", "at": now}}},
    )
    if res.matched_count == 0:
        return None
    return await db.strategic_theses.find_one({"thesis_id": thesis_id}, {"_id": 0})


async def query(company_master_id: Optional[str] = None, thesis_id: Optional[str] = None,
                state: Optional[str] = None, thesis_type: Optional[str] = None) -> List[Dict]:
    q: Dict = {}
    if thesis_id:
        q["thesis_id"] = thesis_id
    if company_master_id:
        q["company_master_id"] = company_master_id
    if state:
        q["lifecycle.state"] = state
    if thesis_type:
        q["thesis_type"] = thesis_type
    out = []
    async for d in db.strategic_theses.find(q, {"_id": 0}).limit(200):
        out.append(d)
    return out
