"""Canonical company resolution capability (Boundary First).

Single source of truth for resolving a CIF or a name to the canonical `master_id` against the
MODERN `master_companies` schema. Both the public Company Intelligence route (`/company/resolve`)
and the Copilot entity-linker reuse THIS function — no duplicated matching logic, no ad-hoc Mongo
access scattered across callers. Everything resolves to `master_id`; CIF and name are resolution
attributes, not the canonical identity.
"""

from typing import Dict, List, Optional
from database import db
from services.data_layer.normalize import normalize_cif, name_key

_PROJ = {"master_id": 1, "cif_normalized": 1, "identity.legal_name": 1,
         "location.provincia": 1, "classification.cnae_section": 1}


def _match(doc: dict, match_type: str, score: float) -> Dict:
    return {
        "master_id": doc["master_id"],
        "cif": doc.get("cif_normalized"),
        "legal_name": (doc.get("identity") or {}).get("legal_name"),
        "province": (doc.get("location") or {}).get("provincia"),
        "cnae_section": (doc.get("classification") or {}).get("cnae_section"),
        "match_type": match_type,
        "score": score,
    }


async def resolve_company_query(cif: Optional[str] = None, name: Optional[str] = None,
                                limit: int = 5) -> Dict:
    """Resolve a CIF (exact) or a name (exact `name_key`, then partial regex) to canonical
    `master_id`(s). Returns {query, count, matches:[{master_id, cif, legal_name, province,
    cnae_section, match_type, score}]}. Never fabricates: empty matches if nothing found."""
    matches: List[Dict] = []
    if cif:
        cifn = normalize_cif(cif)
        if cifn:
            doc = await db.master_companies.find_one({"cif_normalized": cifn}, _PROJ)
            if doc:
                matches.append(_match(doc, "cif_exact", 1.0))
    elif name:
        nk = name_key(name)
        if nk:
            async for d in db.master_companies.find({"name_key": nk}, _PROJ).limit(limit):
                matches.append(_match(d, "name_exact", 1.0))
            if not matches:
                async for d in db.master_companies.find(
                    {"name_key": {"$regex": nk.replace(" ", ".*"), "$options": "i"}}, _PROJ
                ).limit(limit):
                    matches.append(_match(d, "name_partial", 0.6))
    return {"query": {"cif": cif, "name": name}, "count": len(matches), "matches": matches}
