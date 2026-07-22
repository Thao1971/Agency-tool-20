"""Taxonomy Intelligence — Semantic Mapping Engine v2 (Governance Engine).

Single source of truth for ALL external taxonomy → CNAE correspondences.
Supported taxonomies: TARIC (DataComex), CPV (Procurement), NACE, CIS internal, CNMV.

Paradigm shift (v2):
  - NO human approval. Mappings are `active` or `inactive` (deprecated), never "pending".
  - Multi-mapping with proportional `weight`: a source code can map to several CNAEs
    (e.g. TARIC 27 → CNAE 06 @ 62% + CNAE 19 @ 38%). Weights of active mappings of the
    same source code ALWAYS sum to 1.0 (normalized from confidence_score).
  - `confidence_score` (0..1): intrinsic quality/certainty of each individual mapping.
  - `weight` (0..1): proportional share within the source code's mapping set.
  - `origin`: seed | manual | llm — where the mapping came from.
  - `resolve()` NEVER returns None: unmapped codes return {"orphan": true}. No signal is lost.

Quality is observed, not approved: /health, /coverage, /orphans, /inconsistencies.
"""

import logging
from typing import Dict, List, Optional
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

# Quality thresholds (observational, not gatekeeping)
WEAK_CONFIDENCE_THRESHOLD = 0.5   # below this, an individual mapping is "weak"
CONFLICT_MIN_CNAES = 3            # a source code mapping to >= N CNAEs is "fragmented/conflict"
WEIGHT_TOLERANCE = 0.01           # allowed deviation of sum(weights) from 1.0

SUPPORTED_TAXONOMIES = ["taric", "cpv", "nace", "cis_category", "cnmv"]


def _normalize_weights(group: List[Dict]) -> List[Dict]:
    """Normalize `weight` across a group of mappings (same source_code) from confidence_score.

    Weights of all active mappings of a source code sum to 1.0, so the full economic
    value is always distributed (zero loss) when proportionally split downstream.
    """
    total = sum(max(m.get("confidence_score", 0.0), 0.0) for m in group)
    n = len(group)
    if total <= 0:
        for m in group:
            m["weight"] = round(1.0 / n, 6) if n else 0.0
    else:
        for m in group:
            m["weight"] = round(max(m.get("confidence_score", 0.0), 0.0) / total, 6)
    return group


# ──────────────────────────────────────────────────────────────────────────
# Resolution (public, consumed by Arroba/Valuo and signal pipelines)
# ──────────────────────────────────────────────────────────────────────────

async def resolve_to_cnae(source_taxonomy: str, source_code: str) -> List[Dict]:
    """Resolve a code to its weighted CNAE list. Returns [] if orphan (use resolve() for the verdict)."""
    mappings = await db.taxonomy_mappings.find(
        {"source_taxonomy": source_taxonomy, "source_code": source_code, "status": "active"},
        {"_id": 0, "cnae_code": 1, "confidence_score": 1, "weight": 1, "origin": 1},
    ).to_list(50)
    return [{
        "cnae": m["cnae_code"],
        "confidence_score": m.get("confidence_score", 0.0),
        "weight": m.get("weight", 0.0),
        "origin": m.get("origin", "seed"),
    } for m in mappings]


async def resolve(source_taxonomy: str, source_code: str) -> Dict:
    """Full resolution verdict. NEVER returns None — orphan codes are explicitly flagged."""
    mappings = await resolve_to_cnae(source_taxonomy, source_code)
    if not mappings:
        return {
            "taxonomy": source_taxonomy,
            "code": source_code,
            "orphan": True,
            "mappings": [],
        }
    return {
        "taxonomy": source_taxonomy,
        "code": source_code,
        "orphan": False,
        "mappings": mappings,
    }


async def resolve_batch(source_taxonomy: str, source_codes: List[str]) -> Dict[str, List[Dict]]:
    """Resolve multiple codes. Returns {code: [{cnae, confidence_score, weight, origin}]}."""
    mappings = await db.taxonomy_mappings.find(
        {"source_taxonomy": source_taxonomy, "source_code": {"$in": source_codes}, "status": "active"},
        {"_id": 0},
    ).to_list(5000)

    result: Dict[str, List[Dict]] = {}
    for m in mappings:
        result.setdefault(m["source_code"], []).append({
            "cnae": m["cnae_code"],
            "confidence_score": m.get("confidence_score", 0.0),
            "weight": m.get("weight", 0.0),
            "origin": m.get("origin", "seed"),
        })
    return result


# ──────────────────────────────────────────────────────────────────────────
# Seeding & weight maintenance
# ──────────────────────────────────────────────────────────────────────────

async def upsert_mappings(source_taxonomy: str, mappings: List[Dict], origin: str = "seed") -> Dict:
    """Upsert mappings for a taxonomy and (re)normalize weights per source_code.

    Each mapping: {source_code, source_label, cnae_code, confidence_score}
    """
    now = now_iso()
    by_code: Dict[str, List[Dict]] = {}
    for m in mappings:
        by_code.setdefault(m["source_code"], []).append(m)

    created = updated = 0
    for code, group in by_code.items():
        _normalize_weights(group)
        for m in group:
            r = await db.taxonomy_mappings.update_one(
                {"source_taxonomy": source_taxonomy, "source_code": code, "cnae_code": m["cnae_code"]},
                {"$set": {
                    "source_taxonomy": source_taxonomy,
                    "source_code": code,
                    "source_label": m.get("source_label", ""),
                    "cnae_code": m["cnae_code"],
                    "confidence_score": round(m.get("confidence_score", 0.0), 4),
                    "weight": m["weight"],
                    "origin": origin,
                    "status": "active",
                    "updated_at": now,
                },
                "$setOnInsert": {"mapping_id": new_id(), "created_at": now}},
                upsert=True,
            )
            if r.upserted_id:
                created += 1
            elif r.modified_count > 0:
                updated += 1

    return {"taxonomy": source_taxonomy, "created": created, "updated": updated,
            "source_codes": len(by_code)}


async def recompute_all_weights() -> Dict:
    """Re-normalize weights for every (taxonomy, source_code) group of active mappings.

    Idempotent. Keeps weight integrity = sum to 1.0 per code after any manual edit.
    """
    actives = await db.taxonomy_mappings.find({"status": "active"}, {"_id": 0}).to_list(20000)
    groups: Dict[tuple, List[Dict]] = {}
    for m in actives:
        groups.setdefault((m["source_taxonomy"], m["source_code"]), []).append(m)

    fixed = 0
    for (_tax, _code), group in groups.items():
        _normalize_weights(group)
        for m in group:
            r = await db.taxonomy_mappings.update_one(
                {"mapping_id": m["mapping_id"]},
                {"$set": {"weight": m["weight"]}},
            )
            if r.modified_count > 0:
                fixed += 1
    return {"groups": len(groups), "weights_updated": fixed}


async def migrate_to_v2() -> Dict:
    """Migrate legacy schema (confidence/status approval) to v2 (confidence_score/weight/origin)."""
    legacy = await db.taxonomy_mappings.find(
        {"confidence_score": {"$exists": False}}, {"_id": 0}
    ).to_list(20000)

    migrated = 0
    for m in legacy:
        old_status = m.get("status")
        new_status = "inactive" if old_status == "rejected" else "active"
        origin = "manual" if m.get("reviewed_by") else "seed"
        await db.taxonomy_mappings.update_one(
            {"mapping_id": m["mapping_id"]},
            {"$set": {
                "confidence_score": round(m.get("confidence", 0.5), 4),
                "status": new_status,
                "origin": origin,
            },
            "$unset": {"confidence": "", "reviewed_by": "", "reviewed_at": ""}},
        )
        migrated += 1

    if migrated:
        logger.info(f"Taxonomy v2 migration: {migrated} legacy mappings upgraded")
    return {"migrated": migrated}


async def seed_all_taxonomies() -> Dict:
    """Seed all known taxonomy mappings from defaults (v2 schema). Idempotent."""
    results = {}

    # 1. TARIC → CNAE (DataComex)
    from services.taric_cnae_mapping import DEFAULT_TARIC_TO_CNAE, TARIC_CHAPTERS
    taric_mappings = []
    for taric_code, cnae_list in DEFAULT_TARIC_TO_CNAE.items():
        for m in cnae_list:
            taric_mappings.append({
                "source_code": taric_code,
                "source_label": TARIC_CHAPTERS.get(taric_code, ""),
                "cnae_code": m["cnae"],
                "confidence_score": m["confidence"],
            })
    results["taric"] = await upsert_mappings("taric", taric_mappings, origin="seed")

    # 2. CPV → CNAE (Procurement)
    from services.cnae_catalog import CPV_TO_CNAE
    cpv_mappings = [{
        "source_code": cpv_code,
        "source_label": f"CPV {cpv_code}",
        "cnae_code": cnae_div,
        "confidence_score": 0.85,
    } for cpv_code, cnae_div in CPV_TO_CNAE.items()]
    results["cpv"] = await upsert_mappings("cpv", cpv_mappings, origin="seed")

    return results


async def accept_llm_mapping(source_taxonomy: str, source_code: str, source_label: str,
                             cnae_code: str, confidence_score: float) -> bool:
    """Promote an LLM suggestion into an active mapping (origin=llm). Caller re-normalizes weights."""
    now = now_iso()
    r = await db.taxonomy_mappings.update_one(
        {"source_taxonomy": source_taxonomy, "source_code": source_code, "cnae_code": cnae_code},
        {"$set": {
            "source_taxonomy": source_taxonomy,
            "source_code": source_code,
            "source_label": source_label or "",
            "cnae_code": cnae_code,
            "confidence_score": round(confidence_score, 4),
            "origin": "llm",
            "status": "active",
            "updated_at": now,
        },
        "$setOnInsert": {"mapping_id": new_id(), "created_at": now, "weight": 0.0}},
        upsert=True,
    )
    return bool(r.upserted_id or r.modified_count)


async def ensure_taxonomy_v2() -> Dict:
    """Startup hook: seed if empty, migrate legacy docs, and re-normalize all weights."""
    count = await db.taxonomy_mappings.count_documents({})
    seeded = None
    if count == 0:
        seeded = await seed_all_taxonomies()
    migrated = await migrate_to_v2()
    weights = await recompute_all_weights()
    return {"seeded": seeded, "migrated": migrated["migrated"], "weights": weights}


# ──────────────────────────────────────────────────────────────────────────
# Quality console (observational endpoints data)
# ──────────────────────────────────────────────────────────────────────────

def _taxonomy_universe(taxonomy: str) -> Optional[set]:
    """Known full set of source codes for a taxonomy, when determinable."""
    if taxonomy == "taric":
        from services.taric_cnae_mapping import TARIC_CHAPTERS
        return set(TARIC_CHAPTERS.keys())
    if taxonomy == "cpv":
        from services.cnae_catalog import CPV_TO_CNAE
        return set(CPV_TO_CNAE.keys())
    return None


async def _active_groups() -> Dict[tuple, List[Dict]]:
    actives = await db.taxonomy_mappings.find({"status": "active"}, {"_id": 0}).to_list(20000)
    groups: Dict[tuple, List[Dict]] = {}
    for m in actives:
        groups.setdefault((m["source_taxonomy"], m["source_code"]), []).append(m)
    return groups


async def get_coverage() -> Dict:
    """Per-taxonomy coverage + weight integrity."""
    groups = await _active_groups()
    by_tax: Dict[str, Dict] = {}

    for (tax, code), group in groups.items():
        entry = by_tax.setdefault(tax, {"mapped_codes": 0, "weight_ok": 0, "total_mappings": 0})
        entry["mapped_codes"] += 1
        entry["total_mappings"] += len(group)
        wsum = sum(m.get("weight", 0.0) for m in group)
        if abs(wsum - 1.0) <= WEIGHT_TOLERANCE:
            entry["weight_ok"] += 1

    coverage = []
    for tax in sorted(set(list(by_tax.keys()) + SUPPORTED_TAXONOMIES)):
        entry = by_tax.get(tax, {"mapped_codes": 0, "weight_ok": 0, "total_mappings": 0})
        universe = _taxonomy_universe(tax)
        universe_size = len(universe) if universe is not None else entry["mapped_codes"]
        mapped = entry["mapped_codes"]
        coverage.append({
            "taxonomy": tax,
            "universe_size": universe_size,
            "mapped_codes": mapped,
            "total_mappings": entry["total_mappings"],
            "coverage_pct": round(mapped / universe_size * 100, 1) if universe_size else 0.0,
            "weight_integrity_pct": round(entry["weight_ok"] / mapped * 100, 1) if mapped else 100.0,
            "universe_known": universe is not None,
        })
    return {"coverage": coverage}


async def get_orphans(limit: int = 500) -> Dict:
    """Codes with NO active mapping. Data-driven first (real signal loss), then universe gaps."""
    groups = await _active_groups()
    mapped_by_tax: Dict[str, set] = {}
    for (tax, code), _g in groups.items():
        mapped_by_tax.setdefault(tax, set()).add(code)

    from services.taric_cnae_mapping import TARIC_CHAPTERS
    orphans = []

    # TARIC — data-driven: codes present in real trade data but unmapped (these LOSE value)
    taric_mapped = mapped_by_tax.get("taric", set())
    seen = await db.datacomex_raw_data.aggregate([
        {"$group": {"_id": "$taric_code", "occurrences": {"$sum": 1}}},
    ]).to_list(2000)
    seen_map = {s["_id"]: s["occurrences"] for s in seen if s["_id"]}
    for code, occ in seen_map.items():
        if code not in taric_mapped:
            orphans.append({
                "taxonomy": "taric", "code": code,
                "label": TARIC_CHAPTERS.get(code, ""),
                "seen_in_data": True, "occurrences": occ,
            })

    # TARIC — universe gaps (catalogued chapters never mapped)
    for code in _taxonomy_universe("taric") or set():
        if code not in taric_mapped and code not in seen_map:
            orphans.append({
                "taxonomy": "taric", "code": code,
                "label": TARIC_CHAPTERS.get(code, ""),
                "seen_in_data": False, "occurrences": 0,
            })

    # CPV — universe gaps
    cpv_mapped = mapped_by_tax.get("cpv", set())
    for code in _taxonomy_universe("cpv") or set():
        if code not in cpv_mapped:
            orphans.append({
                "taxonomy": "cpv", "code": code, "label": f"CPV {code}",
                "seen_in_data": False, "occurrences": 0,
            })

    orphans.sort(key=lambda o: (not o["seen_in_data"], -o["occurrences"], o["taxonomy"], o["code"]))
    return {
        "total": len(orphans),
        "with_data_loss": sum(1 for o in orphans if o["seen_in_data"]),
        "orphans": orphans[:limit],
    }


async def get_inconsistencies(limit: int = 500) -> Dict:
    """Weight integrity breaches, weak mappings and fragmented (conflict) codes."""
    groups = await _active_groups()

    weight_breaches = []
    conflicts = []
    weak = []

    for (tax, code), group in groups.items():
        wsum = sum(m.get("weight", 0.0) for m in group)
        if abs(wsum - 1.0) > WEIGHT_TOLERANCE:
            weight_breaches.append({
                "taxonomy": tax, "code": code, "label": group[0].get("source_label", ""),
                "weight_sum": round(wsum, 4), "cnae_count": len(group),
            })
        if len(group) >= CONFLICT_MIN_CNAES:
            conflicts.append({
                "taxonomy": tax, "code": code, "label": group[0].get("source_label", ""),
                "cnae_count": len(group),
                "cnaes": [{"cnae": m["cnae_code"], "weight": m.get("weight", 0.0)} for m in group],
            })
        for m in group:
            if m.get("confidence_score", 0.0) < WEAK_CONFIDENCE_THRESHOLD:
                weak.append({
                    "taxonomy": tax, "code": code, "label": group[0].get("source_label", ""),
                    "cnae_code": m["cnae_code"],
                    "confidence_score": m.get("confidence_score", 0.0),
                    "weight": m.get("weight", 0.0), "origin": m.get("origin", "seed"),
                })

    conflicts.sort(key=lambda c: -c["cnae_count"])
    weak.sort(key=lambda w: w["confidence_score"])
    return {
        "weight_breaches": {"total": len(weight_breaches), "items": weight_breaches[:limit]},
        "weak_mappings": {"total": len(weak), "items": weak[:limit]},
        "conflicts": {"total": len(conflicts), "items": conflicts[:limit]},
    }


async def get_health() -> Dict:
    """Top-level health verdict of the mapping engine."""
    total = await db.taxonomy_mappings.count_documents({})
    active = await db.taxonomy_mappings.count_documents({"status": "active"})
    inactive = await db.taxonomy_mappings.count_documents({"status": "inactive"})

    groups = await _active_groups()
    source_codes = len(groups)
    weight_ok = 0
    weak = 0
    conflicts = 0
    for (_tax, _code), group in groups.items():
        wsum = sum(m.get("weight", 0.0) for m in group)
        if abs(wsum - 1.0) <= WEIGHT_TOLERANCE:
            weight_ok += 1
        if len(group) >= CONFLICT_MIN_CNAES:
            conflicts += 1
        weak += sum(1 for m in group if m.get("confidence_score", 0.0) < WEAK_CONFIDENCE_THRESHOLD)

    orphan_data = await get_orphans(limit=10000)
    orphans_with_loss = orphan_data["with_data_loss"]

    weight_integrity_pct = round(weight_ok / source_codes * 100, 1) if source_codes else 100.0

    # Verdict
    if orphans_with_loss > 0 or weight_integrity_pct < 95:
        verdict = "critical" if (orphans_with_loss > 5 or weight_integrity_pct < 80) else "degraded"
    else:
        verdict = "healthy"

    # By-taxonomy origin breakdown
    origin_agg = await db.taxonomy_mappings.aggregate([
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$origin", "count": {"$sum": 1}}},
    ]).to_list(20)
    by_origin = {o["_id"] or "seed": o["count"] for o in origin_agg}

    taxonomies = sorted(set(tax for (tax, _c) in groups.keys()))

    return {
        "verdict": verdict,
        "total_mappings": total,
        "active": active,
        "inactive": inactive,
        "source_codes_mapped": source_codes,
        "taxonomies": taxonomies,
        "taxonomies_count": len(taxonomies),
        "weight_integrity_pct": weight_integrity_pct,
        "orphans_with_data_loss": orphans_with_loss,
        "orphans_total": orphan_data["total"],
        "weak_mappings": weak,
        "conflicts": conflicts,
        "by_origin": by_origin,
    }
