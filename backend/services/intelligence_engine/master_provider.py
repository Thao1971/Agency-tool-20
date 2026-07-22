"""Master Record Provider — internal coexistence layer for M2.

ARCHITECTURAL RULE (M2): the public `enrich` contract is SINGLE and unchanged. The choice
of master-record backend (legacy `companies_master` vs canonical `master_companies`) is an
INTERNAL decision driven by configuration — NEVER a public API parameter. Consumers
(Valuo.pro, arroba.com) must never know which backend served the request.

Mechanism:
- `MASTER_RECORD_SOURCE` env flag: "legacy" (default) | "canonical".
- Rollback is immediate and transparent: flip the flag; no API/contract change.
- Safety: the canonical path falls back to legacy transparently if it cannot resolve a
  record, so switching the flag can never produce a `master_not_found` regression.

NOTE (2026-06-26): the canonical Master Layer (`master_companies`) and the legacy
`companies_master` are currently DISJOINT datasets (cif_normalized overlap = 0). The
canonical path therefore resolves ~nothing today and always falls back to legacy. M2 is
HALTED at validation until a backfill/linkage populates the canonical universe
(see LEGACY_MIGRATION_PLAN.md / MASTER_SOURCE_PARITY_REPORT.md).
"""
import os
from typing import Dict, Optional

from database import db

LEGACY = "legacy"
CANONICAL = "canonical"


def active_master_source() -> str:
    """Internal active backend. Default legacy. Operators flip this for canary/rollback."""
    return os.environ.get("MASTER_RECORD_SOURCE", LEGACY).strip().lower() or LEGACY


async def _from_legacy(master_company_id: str) -> Optional[Dict]:
    return await db.companies_master.find_one({"master_company_id": master_company_id}, {"_id": 0})


def _adapt_canonical(mc: Dict, master_company_id: str) -> Dict:
    """Map the nested canonical `master_companies` doc → the flat shape enrich sources read."""
    ident = mc.get("identity") or {}
    cls = mc.get("classification") or {}
    loc = mc.get("location") or {}
    commercial = ident.get("commercial_name")
    return {
        "master_company_id": master_company_id,
        "legal_name": ident.get("legal_name"),
        "cif": ident.get("cif"),
        "cif_normalized": mc.get("cif_normalized"),
        "domain": ident.get("domain"),
        "website": ident.get("website"),
        "commercial_names": [commercial] if commercial else (ident.get("aliases") or []),
        "aliases": ident.get("aliases") or [],
        "category_name": cls.get("cnae_description"),
        "cnae_primary": cls.get("cnae_code"),
        "country": ident.get("country") or loc.get("pais"),
        "confidence_score": (mc.get("provenance") or {}).get("confidence"),
        "classification": cls,
        "financials": mc.get("financials") or {},
        "sources": mc.get("sources") or {},
        "_master_source": CANONICAL,
    }


async def _from_canonical(master_company_id: str) -> Optional[Dict]:
    """Resolve the canonical record via cif_normalized linkage, adapted to the flat shape.

    Returns None if no canonical record is linkable (caller falls back to legacy).
    """
    legacy = await _from_legacy(master_company_id)
    if not legacy:
        return None
    key = legacy.get("cif_normalized")
    if not key:
        return None
    mc = await db.master_companies.find_one({"cif_normalized": key}, {"_id": 0})
    if not mc:
        return None
    return _adapt_canonical(mc, master_company_id)


async def get_master_record(master_company_id: str, source: Optional[str] = None) -> Optional[Dict]:
    """Return the master record for enrichment from the configured backend.

    Default/legacy: byte-identical to the previous direct `companies_master` fetch.
    Canonical: adapted canonical doc, with transparent fallback to legacy on miss.
    """
    src = (source or active_master_source())
    if src == CANONICAL:
        doc = await _from_canonical(master_company_id)
        if doc is not None:
            return doc
        return await _from_legacy(master_company_id)  # transparent, no contract change
    return await _from_legacy(master_company_id)
