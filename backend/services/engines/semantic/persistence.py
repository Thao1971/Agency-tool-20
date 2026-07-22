"""Persistence for Company Semantic Profiles + derived embeddings.

Collection `semantic_profiles` keyed by master_id. Stores profile + embedding +
profile_checksum (reproducibility/incremental recompute). Regeneration is idempotent:
unchanged checksum → embedding not recomputed.
"""

from typing import Dict, List, Optional

from database import db
from models import now_iso

_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    await db.semantic_profiles.create_index("master_id", unique=True)
    await db.semantic_profiles.create_index("cnae_section")
    _INDEXED = True


async def save(master_id: str, cif: str, section: str, doc: Dict) -> None:
    await ensure_indexes()
    await db.semantic_profiles.update_one(
        {"master_id": master_id},
        {"$set": {**doc, "master_id": master_id, "cif_normalized": cif,
                  "cnae_section": section, "updated_at": now_iso()},
         "$setOnInsert": {"created_at": now_iso()}},
        upsert=True,
    )


async def get(master_id: str) -> Optional[Dict]:
    return await db.semantic_profiles.find_one({"master_id": master_id}, {"_id": 0})


async def candidates_with_embeddings(section: Optional[str], exclude: str, limit: int) -> List[Dict]:
    q: Dict = {"embedding.vector": {"$exists": True}, "master_id": {"$ne": exclude}}
    if section:
        q["cnae_section"] = section
    out = []
    async for d in db.semantic_profiles.find(
            q, {"_id": 0, "master_id": 1, "cif_normalized": 1, "identity_name": 1,
                "cnae_section": 1, "embedding.vector": 1}).limit(limit):
        out.append(d)
    return out
