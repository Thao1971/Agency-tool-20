"""Master Layer builder — Normalized → master_companies (canonical, batched, no N+1).

Resolves each company to a permanent master_id, merges fields non-destructively with
provenance, projects financials/ownership, and records entity_xref. Supports full,
incremental (dirty) and cif_list scopes (P0.3). Idempotent via profile source_hash.
"""

import json
import hashlib
import logging
from typing import Dict, List, Optional

from pymongo import UpdateOne

from database import db
from models import now_iso
from services.data_layer.master.merge import merge_provenance, canonical, _domain_from_web
from services.data_layer.master import entity_resolution as er

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "master-v1"
BATCH = 500


async def ensure_indexes() -> None:
    await db.master_companies.create_index("master_id", unique=True)
    await db.master_companies.create_index("cif_normalized", unique=True)
    await db.master_companies.create_index("name_key")
    await db.master_companies.create_index("contact.domain")
    await db.master_companies.create_index("classification.cnae_section")
    await db.master_companies.create_index("location.provincia")
    await db.master_companies.create_index("status")
    await db.master_companies.create_index("dirty")
    await db.master_companies.create_index("ownership.group_id")
    await db.entity_xref.create_index(
        [("source", 1), ("id_type", 1), ("external_id", 1)], unique=True)
    await db.entity_xref.create_index("master_id")


def _profile_hash(nc: Dict, fin_latest: Optional[Dict], own: List[Dict]) -> str:
    payload = {
        "id": [nc.get("legal_name"), nc.get("commercial_name"), nc.get("cnae_code"),
               nc.get("web"), nc.get("employees_total"), nc.get("capital_social"),
               (nc.get("address") or {}).get("provincia")],
        "fin": fin_latest,
        "own": sorted([str((o.get("relationship_type"), o.get("counterparty_cif"),
                            o.get("counterparty_name"), o.get("pct"))) for o in own]),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _fin_summary(fin_docs: List[Dict]) -> Dict:
    individual = [f for f in fin_docs if f.get("basis") == "individual"]
    chosen = sorted(individual or fin_docs, key=lambda f: (f.get("year") or 0), reverse=True)
    keys = ("revenue", "ebitda", "ebitda_margin", "equity", "total_assets", "net_income",
            "operating_income")
    latest = None
    if chosen:
        f = chosen[0]
        latest = {"year": f.get("year"), "basis": f.get("basis"), **{k: f.get(k) for k in keys}}
    history = [{"year": f.get("year"), "basis": f.get("basis"),
                "revenue": f.get("revenue"), "ebitda": f.get("ebitda"),
                "net_income": f.get("net_income")} for f in chosen]
    return {"latest": latest, "history": history}


def _ownership_summary(own: List[Dict]) -> Dict:
    def pick(t):
        return [{"cif": o.get("counterparty_cif"), "name": o.get("counterparty_name"),
                 "pct": o.get("pct")} for o in own if o.get("relationship_type") == t]
    ult = pick("ultimate_parent_co")
    return {
        "shareholders": pick("shareholder"),
        "parents": pick("parent_co"),
        "ultimate_parent": ult[0] if ult else None,
        "investees": pick("investee_co"),
        "group_id": None,  # assigned by the ownership-graph job (union-find)
    }


async def _process_batch(ncs: List[Dict], source: str, force: bool, stats: Dict) -> None:
    cifs = [n["cif_normalized"] for n in ncs]
    existing = {m["cif_normalized"]: m async for m in
                db.master_companies.find({"cif_normalized": {"$in": cifs}}, {"_id": 0})}
    fin_by_cif: Dict[str, List[Dict]] = {}
    async for f in db.norm_financials.find({"cif_normalized": {"$in": cifs}}, {"_id": 0}):
        fin_by_cif.setdefault(f["cif_normalized"], []).append(f)
    own_by_cif: Dict[str, List[Dict]] = {}
    async for o in db.norm_ownership.find({"src_cif": {"$in": cifs}}, {"_id": 0}):
        own_by_cif.setdefault(o["src_cif"], []).append(o)
    off_counts = {d["_id"]: d["n"] async for d in db.norm_officers.aggregate([
        {"$match": {"cif_normalized": {"$in": cifs}}},
        {"$group": {"_id": "$cif_normalized", "n": {"$sum": 1}}}])}

    master_ops, xref_ops, clean_ops = [], [], []
    now = now_iso()
    for nc in ncs:
        cif = nc["cif_normalized"]
        fin_docs = fin_by_cif.get(cif, [])
        own = own_by_cif.get(cif, [])
        fin = _fin_summary(fin_docs)
        phash = _profile_hash(nc, fin["latest"], own)
        ex = existing.get(cif)
        clean_ops.append(UpdateOne({"cif_normalized": cif}, {"$set": {"dirty": False}}))
        if ex and ex.get("source_hash") == phash and not force:
            stats["skipped"] += 1
            continue

        master_id = ex["master_id"] if ex else \
            (await er.resolve({"cif_normalized": cif, "domain": _domain_from_web(nc.get("web")),
                               "name_key": nc.get("name_key"),
                               "provincia": (nc.get("address") or {}).get("provincia")}, source))[0]
        domain = _domain_from_web(nc.get("web"))
        fields = {
            "legal_name": nc.get("legal_name"), "commercial_name": nc.get("commercial_name"),
            "cnae_code": nc.get("cnae_code"), "cnae_description": nc.get("cnae_description"),
            "web": nc.get("web"), "domain": domain,
            "provincia": (nc.get("address") or {}).get("provincia"),
            "municipio": (nc.get("address") or {}).get("municipio"),
            "employees_total": nc.get("employees_total"), "capital_social": nc.get("capital_social"),
        }
        confidence = 0.9
        prov = merge_provenance(ex.get("provenance") if ex else None, source, fields, now, confidence)
        source_entry = {"source": source, "external_id": cif,
                        "source_version": nc.get("source_version"),
                        "source_file_id": nc.get("source_file_id"), "ingested_at": now}
        sources = [s for s in (ex.get("sources") if ex else []) if s.get("source") != source]
        sources.append(source_entry)

        doc = {
            "master_id": master_id, "cif_normalized": cif, "status": "active",
            "identity": {
                "legal_name": canonical(prov["legal_name"]),
                "commercial_name": canonical(prov["commercial_name"]),
                "aliases": nc.get("aliases") or [], "cif": nc.get("cif"), "country": (nc.get("address") or {}).get("pais"),
            },
            "classification": {
                "cnae_code": canonical(prov["cnae_code"]),
                "cnae_description": canonical(prov["cnae_description"]),
                "cnae_division": nc.get("cnae_division"), "cnae_section": nc.get("cnae_section"),
            },
            "location": {"provincia": canonical(prov["provincia"]), "municipio": canonical(prov["municipio"]),
                         "codigo_postal": (nc.get("address") or {}).get("codigo_postal"),
                         "pais": (nc.get("address") or {}).get("pais")},
            "contact": {"web": canonical(prov["web"]), "domain": canonical(prov["domain"])},
            "name_key": nc.get("name_key"),
            "size": {"employees_total": canonical(prov["employees_total"]),
                     "capital_social": canonical(prov["capital_social"])},
            "financials": fin,
            "ownership": _ownership_summary(own),
            "officers_count": off_counts.get(cif, 0),
            "objeto_social": nc.get("objeto_social"),
            "provenance": prov, "sources": sources,
            "pipeline_version": PIPELINE_VERSION, "source_hash": phash, "dirty": True,
            "built_at": now, "updated_at": now,
        }
        master_ops.append(UpdateOne({"cif_normalized": cif},
                                    {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True))
        for key, val in er.xref_rows(source, master_id, nc.get("source_version"),
                                     cif, nc.get("iberinform_id"), domain):
            xref_ops.append(UpdateOne(key, {"$set": val, "$setOnInsert": {"created_at": now}}, upsert=True))
        stats["built"] += 1

    if master_ops:
        await db.master_companies.bulk_write(master_ops, ordered=False)
    if xref_ops:
        await db.entity_xref.bulk_write(xref_ops, ordered=False)
    if clean_ops:
        await db.norm_company.bulk_write(clean_ops, ordered=False)


async def rebuild_master(scope: str = "full", cif_list: Optional[List[str]] = None,
                         force: bool = False, source: str = "iberinform",
                         heartbeat=None) -> Dict:
    """Build/refresh master_companies from norm_company. scope: full | incremental | cif_list."""
    await ensure_indexes()
    q: Dict = {}
    if scope == "incremental":
        q = {"dirty": True}
    if cif_list:
        q = {"cif_normalized": {"$in": cif_list}}
    stats = {"built": 0, "skipped": 0, "scope": scope}
    batch: List[Dict] = []
    async for nc in db.norm_company.find(q, {"_id": 0}):
        batch.append(nc)
        if len(batch) >= BATCH:
            await _process_batch(batch, source, force, stats)
            batch = []
            if heartbeat:
                await heartbeat({"processed": stats["built"] + stats["skipped"], "message": "master"})
    if batch:
        await _process_batch(batch, source, force, stats)
    stats["total_master"] = await db.master_companies.count_documents({})
    return stats


FIXTURE_SOURCE_VERSION = "iberinform"


async def purge_fixture_sample() -> Dict:
    """Remove the bundled test-fixture Iberinform sample (tests/fixtures/iberinform_sample,
    ~1,000 real companies in the old Valu8 CSV format that ended up loaded into production
    via bootstrap.py's DEFAULT_SOURCE_DIR) from the MODERN schema.

    Mirrors services/iberinform_processor.py's purge_synthetic_dataset() for the legacy
    schema: intentionally conservative, identifies affected records by a stable data-driven
    marker rather than a hardcoded id list, and never deletes anything a real delivery has
    since touched.

    Identification: iberinform_ingest.py's ingest_directory() (used only by the original
    fixture-seeded /bootstrap run) defaults source_version to the literal string "iberinform"
    when none is supplied. iberinform_tab_ingest.py's ingest_tab_directory() (used by every
    real delivery via /bootstrap-tab and /upload-delivery) instead defaults to a random
    "iberinform_tab_<hex>" tag, and both ingestors upsert norm_company/norm_financials/
    norm_ownership/norm_officers by cif_normalized with a plain $set — so any fixture CIF
    that a real delivery has since re-ingested already has its source_version overwritten
    and is excluded here automatically. Only CIFs that STILL carry the literal "iberinform"
    default (i.e. no real delivery has ever included that CIF) are purged.
    """
    marker = {"source": "iberinform", "source_version": FIXTURE_SOURCE_VERSION}
    cifs = await db.norm_company.distinct("cif_normalized", marker)

    if not cifs:
        return {
            "status": "completed", "cifs_purged": 0,
            "norm_company_deleted": 0, "norm_financials_deleted": 0,
            "norm_ownership_deleted": 0, "norm_officers_deleted": 0,
            "master_companies_deleted": 0, "entity_xref_deleted": 0,
        }

    # Capture master_ids BEFORE deleting anything, scoped to these exact CIFs, so the
    # entity_xref cleanup below can never touch a master_id created for a different (real) CIF.
    master_ids = await db.master_companies.distinct(
        "master_id", {"cif_normalized": {"$in": cifs}})

    norm_company_deleted = (await db.norm_company.delete_many(
        {"cif_normalized": {"$in": cifs}, **marker})).deleted_count
    norm_financials_deleted = (await db.norm_financials.delete_many(
        {"cif_normalized": {"$in": cifs}, **marker})).deleted_count
    norm_ownership_deleted = (await db.norm_ownership.delete_many(
        {"src_cif": {"$in": cifs}, **marker})).deleted_count
    norm_officers_deleted = (await db.norm_officers.delete_many(
        {"cif_normalized": {"$in": cifs}, **marker})).deleted_count

    master_deleted = 0
    if master_ids:
        result = await db.master_companies.delete_many({
            "master_id": {"$in": master_ids},
            "cif_normalized": {"$in": cifs},
        })
        master_deleted = result.deleted_count

    xref_deleted = 0
    if master_ids:
        xref_deleted = (await db.entity_xref.delete_many(
            {"master_id": {"$in": master_ids}})).deleted_count

    # 2026-07-23 fix (found by Neo's testing agent after v12): signals persisted for these
    # master_ids (e.g. opportunity.succession_signal from old fixture "administrators") were
    # never cleaned up, so they kept polluting the Opportunities ranking after every purge —
    # their master_id no longer resolves to a real company, so they were silently discarded
    # by the join in _list_opportunities()/_opportunities_feed(), crowding out real results.
    signals_deleted = 0
    if master_ids:
        signals_deleted = (await db.signals.delete_many(
            {"master_id": {"$in": master_ids}})).deleted_count

    return {
        "status": "completed",
        "cifs_purged": len(cifs),
        "norm_company_deleted": norm_company_deleted,
        "norm_financials_deleted": norm_financials_deleted,
        "norm_ownership_deleted": norm_ownership_deleted,
        "norm_officers_deleted": norm_officers_deleted,
        "master_companies_deleted": master_deleted,
        "entity_xref_deleted": xref_deleted,
        "signals_deleted": signals_deleted,
    }
