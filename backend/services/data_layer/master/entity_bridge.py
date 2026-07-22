"""Entity Bridge — canonical identity bridge builder + Master Record quality tool (M3-phase-2).

READ-ONLY over legacy. This job NEVER modifies `companies_master` and NEVER activates the
canonical engine or migrates traffic. It only WRITES to dedicated bridge collections:
  - `entity_xref`  : bridge rows id_type='master_company_id' (tagged origin='er_bridge', bridge_run_id)
  - `er_bridge_runs`    : one auditable summary per run (historical metrics)
  - `er_bridge_results` : per-entity classification for the run (conflicts/ambiguities/dups/orphans)

Idempotent (bridge rows upserted by external_id), repeatable, monitorable, auditable and
reversible (rollback_run deletes ONLY this job's rows for a run_id).
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Optional

from database import db
from services.entity_resolution import _normalize_cif, _normalize_name, _extract_domain
from services.data_layer.master.identity_resolver import THRESHOLDS

BRIDGE_VERSION = "entity-bridge-v1"
ORIGIN = "er_bridge"


def _now():
    return datetime.now(timezone.utc).isoformat()


async def ensure_indexes() -> None:
    await db.er_bridge_runs.create_index("run_id", unique=True)
    await db.er_bridge_results.create_index([("run_id", 1), ("status", 1)])
    await db.er_bridge_results.create_index("master_company_id")


async def _load_canonical_index():
    by_cif, by_domain, by_name = defaultdict(list), defaultdict(list), defaultdict(list)
    proj = {"_id": 0, "master_id": 1, "cif_normalized": 1, "contact": 1, "name_key": 1}
    async for mc in db.master_companies.find({}, proj):
        mid = mc["master_id"]
        if mc.get("cif_normalized"):
            by_cif[mc["cif_normalized"]].append(mid)
        dom = (mc.get("contact") or {}).get("domain")
        if dom:
            by_domain[dom].append(mid)
        if mc.get("name_key"):
            by_name[mc["name_key"]].append(mid)
    return by_cif, by_domain, by_name


def _classify(legacy: Dict, idx) -> Dict:
    by_cif, by_domain, by_name = idx
    cif = legacy.get("cif_normalized") or _normalize_cif(legacy.get("cif"))
    dom = _extract_domain(legacy.get("domain"))
    nk = legacy.get("name_key") or _normalize_name(legacy.get("legal_name"))

    cand = {}  # master_id -> (score, method)
    if cif:
        for mid in by_cif.get(cif, []):
            cand[mid] = max(cand.get(mid, (0, ""))[0], THRESHOLDS["cif_exact"]), "cif_exact"
    if dom:
        for mid in by_domain.get(dom, []):
            if THRESHOLDS["domain_exact"] > cand.get(mid, (0, ""))[0]:
                cand[mid] = (THRESHOLDS["domain_exact"], "domain_exact")
    if nk:
        for mid in by_name.get(nk, []):
            if THRESHOLDS["name_province"] > cand.get(mid, (0, ""))[0]:
                cand[mid] = (THRESHOLDS["name_province"], "name")

    if not cand:
        return {"status": "orphan", "match_id": None, "score": 0, "method": None, "candidate_ids": []}
    ids = list(cand.keys())
    best_id = max(cand, key=lambda k: cand[k][0])
    best_score, best_method = cand[best_id]
    if len(set(ids)) > 1:
        return {"status": "ambiguous", "match_id": None, "score": best_score,
                "method": best_method, "candidate_ids": ids}
    if best_score >= THRESHOLDS["auto_merge"]:
        return {"status": "linked", "match_id": best_id, "score": best_score,
                "method": best_method, "candidate_ids": ids}
    if best_score >= THRESHOLDS["conflict"]:
        return {"status": "conflict", "match_id": None, "score": best_score,
                "method": best_method, "candidate_ids": ids}
    return {"status": "orphan", "match_id": None, "score": best_score,
            "method": best_method, "candidate_ids": ids}


async def run_bridge(scope: str = "full", limit: Optional[int] = None, dry_run: bool = False) -> Dict:
    """Build the canonical bridge and compute Master Record quality metrics for this run."""
    await ensure_indexes()
    run_id = "erb_" + uuid.uuid4().hex[:12]
    started = _now()
    idx = await _load_canonical_index()

    counts = defaultdict(int)
    linked_to: Dict[str, list] = defaultdict(list)  # canonical master_id -> [legacy ids]
    result_ops, xref_ops = [], []
    processed = 0

    cur = db.companies_master.find(
        {}, {"_id": 0, "master_company_id": 1, "cif": 1, "cif_normalized": 1,
             "domain": 1, "legal_name": 1, "name_key": 1})
    if limit:
        cur = cur.limit(limit)

    async for legacy in cur:
        processed += 1
        mcid = legacy["master_company_id"]
        c = _classify(legacy, idx)
        counts[c["status"]] += 1
        result_ops.append({
            "run_id": run_id, "master_company_id": mcid, "status": c["status"],
            "match_id": c["match_id"], "score": c["score"], "method": c["method"],
            "candidate_ids": c["candidate_ids"], "created_at": started,
        })
        if c["status"] == "linked":
            linked_to[c["match_id"]].append(mcid)
            if not dry_run:
                xref_ops.append((mcid, c["match_id"], c["method"]))

    # potential duplicates: several legacy records mapping to the SAME canonical id
    potential_duplicates = {mid: legs for mid, legs in linked_to.items() if len(legs) > 1}
    dup_legacy_count = sum(len(v) for v in potential_duplicates.values())

    if not dry_run:
        if result_ops:
            await db.er_bridge_results.insert_many(result_ops, ordered=False)
        for mcid, mid, method in xref_ops:
            await db.entity_xref.update_one(
                {"id_type": "master_company_id", "external_id": mcid, "origin": ORIGIN},
                {"$set": {"master_id": mid, "match_method": method, "bridge_run_id": run_id,
                          "updated_at": started},
                 "$setOnInsert": {"source": "companies_master", "created_at": started}},
                upsert=True)

    coverage_pct = round(100.0 * counts["linked"] / processed, 2) if processed else 0.0
    report = {
        "run_id": run_id, "bridge_version": BRIDGE_VERSION, "scope": scope, "dry_run": dry_run,
        "started_at": started, "completed_at": _now(),
        "canonical_universe": sum(len(v) for v in idx[0].values()) or await db.master_companies.count_documents({}),
        "metrics": {
            "processed": processed,
            "linked": counts["linked"],
            "coverage_pct": coverage_pct,
            "conflicts": counts["conflict"],
            "ambiguous": counts["ambiguous"],
            "orphans": counts["orphan"],
            "potential_duplicate_groups": len(potential_duplicates),
            "potential_duplicate_records": dup_legacy_count,
            "pending_manual_review": counts["conflict"] + counts["ambiguous"],
        },
        "status": "completed",
    }
    if not dry_run:
        await db.er_bridge_runs.insert_one({**report})
    return report


async def rollback_run(run_id: str) -> Dict:
    """Reverse a run: delete ONLY this job's rows (bridge xref + results). Legacy untouched."""
    xref = await db.entity_xref.delete_many({"origin": ORIGIN, "bridge_run_id": run_id})
    res = await db.er_bridge_results.delete_many({"run_id": run_id})
    await db.er_bridge_runs.update_one(
        {"run_id": run_id}, {"$set": {"status": "rolled_back", "rolled_back_at": _now()}})
    return {"run_id": run_id, "xref_removed": xref.deleted_count,
            "results_removed": res.deleted_count, "status": "rolled_back"}


async def list_runs(limit: int = 20) -> list:
    return await db.er_bridge_runs.find({}, {"_id": 0}).sort("started_at", -1).to_list(limit)


async def get_run(run_id: str, sample: int = 20) -> Optional[Dict]:
    run = await db.er_bridge_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run:
        return None
    samples = {}
    for st in ("conflict", "ambiguous", "orphan"):
        samples[st] = await db.er_bridge_results.find(
            {"run_id": run_id, "status": st}, {"_id": 0}).limit(sample).to_list(sample)
    return {**run, "samples": samples}
