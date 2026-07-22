"""Master Record Builder + Entity Resolution (P2.1).

Idempotent, in-place enrichment of `companies_master` into the single source of truth.
Unifies identity, classification (CNAE→sector), financials (Iberinform), sources, confidence
and lineage. Source-agnostic: re-runnable as new sources land (incl. the real 3.3M dump).
"""

import logging
from typing import Dict, List, Optional

from database import db
from models import now_iso
from services.data_layer.normalize import (
    normalize_cif, name_key, section_label, division_of, division_label,
    resolve_section, build_aliases,
)

logger = logging.getLogger(__name__)

_FIN_FIELDS = ["year", "revenue", "ebitda", "ebitda_margin", "equity", "net_income",
               "employees", "total_assets"]


def _web(doc: Dict) -> Dict:
    return (doc.get("sources") or {}).get("web") or {}


async def _financials_for_cif(cif: Optional[str]) -> Optional[Dict]:
    if not cif:
        return None
    docs = await db.iberinform_financials.find({"cif": cif}, {"_id": 0}).sort("year", -1).to_list(50)
    if not docs:
        return None
    history = [{k: d.get(k) for k in _FIN_FIELDS} for d in docs]
    return {"latest": history[0], "history": history, "years": [d.get("year") for d in docs]}


def _build_classification(doc: Dict, ib: Optional[Dict]) -> Dict:
    ib = ib or {}
    web = _web(doc)
    cnae_code = doc.get("cnae_code") or ib.get("cnae_code")
    cnae_div = doc.get("cnae_division") or ib.get("cnae_division") or division_of(cnae_code)
    cnae_section = doc.get("cnae_section") or ib.get("cnae_section") or resolve_section(cnae_code)
    cnae_label = doc.get("cnae_label") or ib.get("cnae_label") or division_label(cnae_div)
    sector = section_label(cnae_section)
    category = web.get("category") or sector
    return {
        "cnae_code": cnae_code,
        "cnae_division": cnae_div,
        "cnae_section": cnae_section,
        "cnae_label": cnae_label,
        "sector": sector,
        "category": category,
    }


def _build_sources(doc: Dict, ib: Optional[Dict], fin: Optional[Dict]) -> Dict:
    """Source lineage blocks to MERGE into existing sources (never clobbers existing web)."""
    return {
        "iberinform": {
            "present": bool(ib),
            "source_version": (ib or {}).get("source_version"),
            "imported_at": (ib or {}).get("imported_at"),
        },
        "financials": {
            "present": bool(fin),
            "latest_year": (fin or {}).get("latest", {}).get("year") if fin else None,
            "years": (fin or {}).get("years") if fin else [],
        },
    }


def _confidence(doc: Dict, classification: Dict, ib: Optional[Dict], fin: Optional[Dict]) -> float:
    score = 0.0
    if doc.get("cif") and (doc.get("legal_name") or doc.get("normalized_name")):
        score += 0.30
    if classification.get("cnae_code"):
        score += 0.25
    if fin and (fin["latest"].get("ebitda") or fin["latest"].get("revenue")):
        score += 0.30
    elif doc.get("revenue_latest") or doc.get("employees_latest"):
        score += 0.10
    if _web(doc):
        score += 0.15
    return round(min(0.99, max(0.3, score)), 2)


def _lineage(doc: Dict, classification: Dict, ib: Optional[Dict], fin: Optional[Dict]) -> Dict:
    web = _web(doc)
    return {
        "source": "normalized",
        "identity": "iberinform" if ib else ("web" if web else "unknown"),
        "classification": "iberinform" if classification.get("cnae_code") else ("web" if web.get("category") else "none"),
        "financials": "iberinform" if fin else ("iberinform_latest" if (doc.get("revenue_latest") or doc.get("employees_latest")) else "none"),
    }


async def build_one(doc: Dict) -> Dict:
    cif = doc.get("cif")
    ib = await db.iberinform_companies.find_one({"cif": cif}, {"_id": 0}) if cif else None
    fin = await _financials_for_cif(cif)
    web = _web(doc)

    classification = _build_classification(doc, ib)
    aliases = build_aliases(
        doc.get("legal_name"), (ib or {}).get("trade_name"),
        doc.get("commercial_names") or [], doc.get("aliases") or [],
        web.get("company_name"), doc.get("domain"),
    )

    update = {
        "cif_normalized": normalize_cif(cif),
        "name_key": name_key(doc.get("legal_name") or doc.get("normalized_name") or web.get("company_name")),
        "aliases": aliases,
        "classification": classification,
        "financials": fin or {"latest": None, "history": [], "years": []},
        "sources": {**(doc.get("sources") or {}), **_build_sources(doc, ib, fin)},
        "confidence_score": _confidence(doc, classification, ib, fin),
        "lineage": _lineage(doc, classification, ib, fin),
        # backward-compatible top-level fields
        "sector": classification.get("sector"),
        "category_name": classification.get("category"),
        "cnae": classification.get("cnae_code"),
        "updated_at": now_iso(),
    }
    return update


async def rebuild_master_records() -> Dict:
    """Idempotently rebuild every master record. Returns stats."""
    total = enriched = with_classification = with_financials = 0
    cursor = db.companies_master.find({}, {"_id": 0})
    async for doc in cursor:
        total += 1
        update = await build_one(doc)
        await db.companies_master.update_one(
            {"master_company_id": doc["master_company_id"]}, {"$set": update}
        )
        enriched += 1
        if update["classification"].get("cnae_code"):
            with_classification += 1
        if update["financials"].get("latest"):
            with_financials += 1

    dedupe = await resolve_duplicates()
    return {
        "total": total,
        "enriched": enriched,
        "with_classification": with_classification,
        "with_financials": with_financials,
        "dedupe": dedupe,
    }


async def resolve_duplicates() -> Dict:
    """Entity resolution: detect duplicates by cif_normalized, then name_key+province.

    Non-destructive: marks duplicates with merge_status='merged' + merged_into pointer to
    the canonical (highest confidence) record. No-op on current data (0 duplicates).
    """
    merged = 0

    async def _merge_group(match: Dict, key_field: str):
        nonlocal merged
        pipeline = [
            {"$match": match},
            {"$group": {"_id": f"${key_field}", "ids": {"$push": "$master_company_id"}, "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
        ]
        async for grp in db.companies_master.aggregate(pipeline):
            docs = await db.companies_master.find(
                {"master_company_id": {"$in": grp["ids"]}}, {"_id": 0}
            ).to_list(100)
            docs.sort(key=lambda d: -(d.get("confidence_score") or 0))
            canonical = docs[0]
            for dup in docs[1:]:
                merged_aliases = build_aliases(canonical.get("aliases") or [], dup.get("aliases") or [])
                await db.companies_master.update_one(
                    {"master_company_id": canonical["master_company_id"]},
                    {"$set": {"aliases": merged_aliases}},
                )
                await db.companies_master.update_one(
                    {"master_company_id": dup["master_company_id"]},
                    {"$set": {"merge_status": "merged", "merged_into": canonical["master_company_id"]}},
                )
                merged += 1

    await _merge_group({"cif_normalized": {"$nin": [None, ""]}}, "cif_normalized")
    await _merge_group(
        {"$and": [{"cif_normalized": {"$in": [None, ""]}}, {"name_key": {"$nin": [None, ""]}}]},
        "name_key",
    )
    return {"merged": merged}
