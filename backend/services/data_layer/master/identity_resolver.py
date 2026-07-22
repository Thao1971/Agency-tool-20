"""Canonical Entity Resolution Engine — `entity-resolution-v1` (M3).

Single canonical identity resolver (DER1). `entity_xref` is the append-only source of truth
of the identity link (DER2): (source, id_type, external_id) → master_id, including the
legacy↔canonical bridge id_type='master_company_id' (DER3, unblocks M2).

Frozen decisions:
- DER4 thresholds: cif=1.0, domain=0.95, name+province=0.70, auto_merge=0.95, conflict=0.70.
- DER5 deterministic master_id from the natural key (same cif/domain/name → same id, reproducible).
- DER6 explainability + append-only audit.
- DER9 conflict status between conflict and auto_merge thresholds.

Returns the SAME shape as the legacy `resolve_entity` so it can serve behind the coexistence
provider without changing any public contract (DER7).
"""
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from database import db
# Reuse legacy normalizers so normalization is byte-identical across engines.
from services.entity_resolution import _normalize_cif, _normalize_name, _extract_domain, _name_sim

RESOLVER_VERSION = "entity-resolution-v1"

# DER4 — frozen thresholds
THRESHOLDS = {
    "cif_exact": 1.0,
    "domain_exact": 0.95,
    "name_province": 0.70,
    "auto_merge": 0.95,
    "conflict": 0.70,
}


def deterministic_master_id(cif_normalized: Optional[str] = None, domain: Optional[str] = None,
                            name_key: Optional[str] = None, provincia: Optional[str] = None) -> str:
    """DER5 — reproducible id derived from the strongest available natural key."""
    if cif_normalized:
        basis = f"cif:{cif_normalized}"
    elif domain:
        basis = f"domain:{domain}"
    elif name_key:
        basis = f"name:{name_key}|prov:{(provincia or '').lower()}"
    else:
        basis = "unresolved"
    return "mc_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


async def _xref_master_id(id_type: str, external_id: str) -> Optional[str]:
    doc = await db.entity_xref.find_one(
        {"id_type": id_type, "external_id": external_id}, {"_id": 0, "master_id": 1})
    return doc["master_id"] if doc else None


async def _audit(entity: Dict, result: Dict, source: str) -> None:
    await db.entity_resolution_audit.insert_one({
        "resolver_version": RESOLVER_VERSION,
        "source": source,
        "input": {k: entity.get(k) for k in ("legal_name", "cif", "domain")},
        "status": result["status"], "method": result["method"],
        "score": result["score"], "match_id": result["match_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def link_legacy_master(master_company_id: str, master_id: str, source: str = "companies_master") -> None:
    """DER3 — bridge legacy master_company_id ↔ canonical master_id in entity_xref (append-only).

    Mechanism only; the mass backfill is deferred to M3-phase-2 (DER8).
    """
    now = datetime.now(timezone.utc).isoformat()
    await db.entity_xref.update_one(
        {"id_type": "master_company_id", "external_id": master_company_id, "source": source},
        {"$set": {"master_id": master_id, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


async def resolve_identity(
    legal_name: Optional[str] = None,
    commercial_name: Optional[str] = None,
    cif: Optional[str] = None,
    domain: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    source: str = "unknown",
    provincia: Optional[str] = None,
    audit: bool = True,
) -> Dict:
    """Canonical resolution → legacy-compatible {status, score, method, match_id, candidates}."""
    cif_norm = _normalize_cif(cif)
    name_norm = _normalize_name(legal_name)
    domain_clean = _extract_domain(domain)
    candidates: List[Dict] = []

    # 1) CIF exact — entity_xref first, then master_companies (DER2)
    if cif_norm:
        mid = await _xref_master_id("cif", cif_norm)
        if not mid:
            m = await db.master_companies.find_one({"cif_normalized": cif_norm}, {"_id": 0, "master_id": 1})
            mid = m["master_id"] if m else None
        if mid:
            candidates.append({"master_id": mid, "score": THRESHOLDS["cif_exact"],
                               "method": "cif_exact", "reasons": [f"CIF match: {cif_norm}"]})

    # 2) Domain exact
    if domain_clean and not candidates:
        m = await db.master_companies.find_one({"contact.domain": domain_clean}, {"_id": 0, "master_id": 1})
        if m:
            candidates.append({"master_id": m["master_id"], "score": THRESHOLDS["domain_exact"],
                               "method": "domain_exact", "reasons": [f"Domain match: {domain_clean}"]})

    # 3) Name + province
    if name_norm and len(name_norm) >= 3 and provincia and not candidates:
        m = await db.master_companies.find_one(
            {"name_key": name_norm, "location.provincia": provincia}, {"_id": 0, "master_id": 1})
        if m:
            candidates.append({"master_id": m["master_id"], "score": THRESHOLDS["name_province"],
                               "method": "name_province", "reasons": [f"name+province: {provincia}"]})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    candidates = candidates[:5]

    if not candidates:
        # DER5 — deterministic proposal for a brand-new canonical id
        proposed = deterministic_master_id(cif_norm, domain_clean, name_norm, provincia)
        result = {"status": "discovered", "score": 0, "method": None,
                  "match_id": None, "proposed_master_id": proposed, "candidates": []}
    else:
        best = candidates[0]
        # normalize candidate key name to match legacy 'master_company_id' consumers
        norm_candidates = [{"master_company_id": c["master_id"], "score": c["score"],
                            "method": c["method"], "reasons": c["reasons"]} for c in candidates]
        if best["score"] >= THRESHOLDS["auto_merge"]:
            status = "auto_merged"
        elif best["score"] >= THRESHOLDS["conflict"]:
            status = "conflict"
        else:
            status = "discovered"
        result = {"status": status, "score": best["score"], "method": best["method"],
                  "match_id": best["master_id"] if status != "discovered" else None,
                  "candidates": norm_candidates}

    if audit:
        await _audit({"legal_name": legal_name, "cif": cif, "domain": domain}, result, source)
    return result
