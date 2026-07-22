"""Legacy → Canonical projection (M3-phase-2b).

Populates the canonical Master Layer (`master_companies`) with the SAME entity universe that
lives in legacy `companies_master`, using the LEGITIMATE Data Layer pipeline:
  project legacy identity → `norm_company` (tagged, reversible) → `rebuild_master(cif_list)`.

This preserves master_builder invariants (one cif xref per master; deterministic idempotent
build) so the arroba engines and the master-layer smoke suite keep working. It NEVER modifies
`companies_master` (read-only) and is fully reversible per projection batch.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from database import db
from services.data_layer.master.master_builder import rebuild_master

PROJECTION_SOURCE = "companies_master_projection"
PIPELINE_VERSION = "master-v1"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _map_legacy_to_norm(legacy: Dict, job_id: str) -> Dict:
    cnae = legacy.get("cnae_code") or legacy.get("cnae")
    return {
        "cif": legacy.get("cif"), "cif_normalized": legacy.get("cif_normalized"),
        "legal_name": legacy.get("legal_name"), "commercial_name": None,
        "aliases": legacy.get("aliases") or [],
        "name_key": legacy.get("name_key"),
        "cnae_code": cnae, "cnae_description": legacy.get("cnae_label"),
        "cnae_division": (str(cnae)[:2] if cnae else None), "cnae_section": legacy.get("cnae_section"),
        "address": {"provincia": legacy.get("province_name"), "municipio": None,
                    "codigo_postal": None, "pais": "ES"},
        "web": legacy.get("domain"), "objeto_social": legacy.get("objeto_social"),
        "employees_total": legacy.get("employees_latest"), "capital_social": None,
        "source": PROJECTION_SOURCE, "source_version": _now()[:10],
        "source_file_id": None, "iberinform_id": None,
        "projection_batch": job_id, "pipeline_version": PIPELINE_VERSION,
        "dirty": True, "created_at": _now(), "updated_at": _now(),
    }


async def project_and_build(limit: int = 500, dry_run: bool = False) -> Dict:
    """Project legacy entities NOT yet in the canonical layer, then rebuild them (cif_list)."""
    job_id = "proj_" + uuid.uuid4().hex[:12]
    existing = set(await db.norm_company.distinct("cif_normalized"))
    picked, cifs = [], []
    cur = db.companies_master.find(
        {"cif_normalized": {"$ne": None}, "legal_name": {"$nin": [None, ""]}},
        {"_id": 0, "cif": 1, "cif_normalized": 1, "legal_name": 1, "aliases": 1, "name_key": 1,
         "cnae_code": 1, "cnae": 1, "cnae_label": 1, "cnae_section": 1, "province_name": 1,
         "domain": 1, "objeto_social": 1, "employees_latest": 1}).sort("cif_normalized", 1)
    async for legacy in cur:
        cifn = legacy["cif_normalized"]
        if cifn in existing or cifn in cifs:
            continue
        picked.append(_map_legacy_to_norm(legacy, job_id))
        cifs.append(cifn)
        if len(cifs) >= limit:
            break

    if dry_run:
        return {"job_id": job_id, "dry_run": True, "would_project": len(cifs)}

    if picked:
        await db.norm_company.insert_many(picked, ordered=False)
    build_stats = await rebuild_master(scope="cif_list", cif_list=cifs) if cifs else {"built": 0}
    return {"job_id": job_id, "projected": len(cifs), "build_stats": build_stats,
            "completed_at": _now()}


async def rollback_projection(job_id: str) -> Dict:
    """Reverse a projection batch: remove ONLY its norm/master/xref rows. Legacy untouched."""
    cifs = await db.norm_company.distinct("cif_normalized", {"projection_batch": job_id})
    if not cifs:
        return {"job_id": job_id, "removed_norm": 0, "removed_master": 0, "removed_xref": 0}
    rm = await db.master_companies.delete_many({"cif_normalized": {"$in": cifs}})
    rx = await db.entity_xref.delete_many({"external_id": {"$in": cifs}, "id_type": "cif"})
    rn = await db.norm_company.delete_many({"projection_batch": job_id})
    return {"job_id": job_id, "removed_norm": rn.deleted_count,
            "removed_master": rm.deleted_count, "removed_xref": rx.deleted_count}


async def universe_overlap() -> Dict:
    """Read-only cross-universe coverage report (legacy vs canonical) by cif_normalized."""
    legacy = set(await db.companies_master.distinct("cif_normalized", {"cif_normalized": {"$ne": None}}))
    canon = set(await db.master_companies.distinct("cif_normalized", {"cif_normalized": {"$ne": None}}))
    overlap = legacy & canon
    return {
        "legacy_total": await db.companies_master.count_documents({}),
        "legacy_with_cif": len(legacy),
        "canonical_total": await db.master_companies.count_documents({}),
        "canonical_with_cif": len(canon),
        "overlap": len(overlap),
        "only_legacy": len(legacy - canon),
        "only_canonical": len(canon - legacy),
        "legacy_coverage_pct": round(100.0 * len(overlap) / len(legacy), 2) if legacy else 0.0,
        "canonical_coverage_pct": round(100.0 * len(overlap) / len(canon), 2) if canon else 0.0,
    }
