"""Utilities for the M2-preparation snapshot-diff harness.

Captures the DETERMINISTIC computed output of `enrich_company` over a FROZEN golden
dataset, so the upcoming M2 migration (intelligence_engine reading companies_master →
master_companies) can be validated for byte-level PARITY of the enriched `fields`.

Only stable fields are snapshotted (volatile timing/ids are stripped):
  kept    → profile, engine_version, fields{...}, sources_with_data[sorted], found_map{src:bool}
  dropped → duration_ms, started_at, completed_at, per-source volatile meta
"""
import json
import os
from typing import Dict, List

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "enrich_golden_snapshots.json")
PROFILES = ["valuo", "arroba"]


def _canon(v):
    """Order-insensitive canonicalization: sort dict keys and lists (by JSON) recursively.

    enrich aggregates some sources into lists whose order is non-deterministic; parity
    cares about the SET of values, not their order.
    """
    if isinstance(v, dict):
        return {k: _canon(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        items = [_canon(x) for x in v]
        try:
            return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
        except TypeError:
            return items
    return v


def normalize(result: Dict) -> Dict:
    """Strip volatile fields; keep only the deterministic, migration-relevant contract."""
    found_map = {m.get("source"): bool(m.get("found"))
                 for m in (result.get("sources_consulted") or [])}
    return {
        "profile": result.get("profile"),
        "engine_version": result.get("engine_version"),
        "fields": _canon(result.get("fields") or {}),
        "sources_with_data": sorted(result.get("sources_with_data") or []),
        "found_map": found_map,
    }


def load_snapshots() -> Dict:
    if not os.path.exists(SNAPSHOT_PATH):
        return {}
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_snapshots(payload: Dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)


def diff(expected: Dict, actual: Dict) -> List[str]:
    """Human-readable list of contract drifts between two normalized snapshots."""
    drifts = []
    if expected.get("engine_version") != actual.get("engine_version"):
        drifts.append(f"engine_version {expected.get('engine_version')} → {actual.get('engine_version')}")
    if expected.get("sources_with_data") != actual.get("sources_with_data"):
        drifts.append(f"sources_with_data {expected.get('sources_with_data')} → {actual.get('sources_with_data')}")
    if expected.get("found_map") != actual.get("found_map"):
        drifts.append(f"found_map changed: {expected.get('found_map')} → {actual.get('found_map')}")
    ef, af = expected.get("fields") or {}, actual.get("fields") or {}
    for k in sorted(set(ef) | set(af)):
        if ef.get(k) != af.get(k):
            drifts.append(f"field '{k}': {ef.get(k)!r} → {af.get(k)!r}")
    return drifts
