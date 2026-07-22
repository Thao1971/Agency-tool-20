"""Reusable, explainable Entity Resolution engine.

Deterministic rule chain (highest confidence first). Architecture is pluggable: a
probabilistic / ML resolver can be added later as additional rules without changing callers.
Resolution maps an external entity → a permanent internal master_id, recorded in entity_xref.
The original sources are NEVER modified.
"""

import uuid
from typing import Dict, Optional, Tuple

from database import db
from models import now_iso

# (id_type, confidence) deterministic rules, in priority order.
RULES = [
    ("cif", 1.0),
    ("domain", 0.9),
    ("name_province", 0.7),
]


def new_master_id() -> str:
    return f"mc_{uuid.uuid4().hex[:12]}"


async def _xref_lookup(source: str, id_type: str, external_id: str) -> Optional[str]:
    if not external_id:
        return None
    doc = await db.entity_xref.find_one(
        {"source": source, "id_type": id_type, "external_id": external_id},
        {"_id": 0, "master_id": 1})
    return doc["master_id"] if doc else None


async def _master_lookup(field: str, value: str) -> Optional[str]:
    if not value:
        return None
    doc = await db.master_companies.find_one({field: value}, {"_id": 0, "master_id": 1})
    return doc["master_id"] if doc else None


async def resolve(entity: Dict, source: str) -> Tuple[str, str, float, bool]:
    """Resolve an entity to a master_id. Returns (master_id, match_rule, confidence, created).

    CIF is the authoritative company identifier (Iberinform and all other real sources
    always provide one). The domain / name+province rules below are fallbacks for the rare
    case an entity has NO usable CIF at all — they must never be used to override an entity
    that already carries its own CIF, because two distinct, legally separate companies
    (e.g. a holding and one of its investees) commonly share a website domain or a
    name+province pair. Matching on that alone previously caused unrelated real companies
    to collide onto the same master_id (E11000 duplicate key on cif_normalized bulk-upsert).
    """
    cif = entity.get("cif_normalized")
    domain = entity.get("domain")
    name_key = entity.get("name_key")
    provincia = entity.get("provincia")

    # 1) exact CIF (deterministic)
    mid = await _xref_lookup(source, "cif", cif) or await _master_lookup("cif_normalized", cif)
    if mid:
        return mid, "exact_cif", 1.0, False

    # A CIF was provided but didn't match any existing master record: this is a genuinely
    # new company. Do NOT fall through to domain/name matching, which could incorrectly
    # merge it onto a different, already-CIF-identified company's master_id.
    if cif:
        return new_master_id(), "new", 1.0, True

    # 2) web domain (only reached when the entity has no CIF at all)
    mid = await _master_lookup("contact.domain", domain)
    if mid:
        return mid, "domain", 0.9, False
    # 3) normalized name + province (blocking key)
    if name_key and provincia:
        doc = await db.master_companies.find_one(
            {"name_key": name_key, "location.provincia": provincia}, {"_id": 0, "master_id": 1})
        if doc:
            return doc["master_id"], "name_province", 0.7, False
    # no match → new permanent id
    return new_master_id(), "new", 1.0, True


def xref_rows(source: str, master_id: str, source_version: str,
              cif: Optional[str], iberinform_id: Optional[str], domain: Optional[str]) -> list:
    """Build entity_xref upsert specs (source external id → master_id), non-destructive."""
    now = now_iso()
    rows = []
    for id_type, ext in (("cif", cif), ("iberinform_id", iberinform_id), ("domain", domain)):
        if not ext:
            continue
        rows.append((
            {"source": source, "id_type": id_type, "external_id": ext},
            {"master_id": master_id, "source_version": source_version, "updated_at": now},
        ))
    return rows
