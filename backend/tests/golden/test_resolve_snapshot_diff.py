"""M3 safety-net — resolve_entity snapshot-diff via the coexistence provider.

Freezes the observable resolution behavior (status/method/score/match_id/candidate_count)
for stable identity inputs. With the default legacy backend this must match byte-for-byte.
The canonical backend must reproduce it before any traffic migration (M3).
"""
import json
import os
import pytest

from smoke_loop import run_async
from services.entity_resolution_provider import resolve_entity_provider

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "resolve_golden_snapshots.json")
_ENTRIES = json.load(open(_PATH, encoding="utf-8"))["entries"] if os.path.exists(_PATH) else {}

pytestmark = pytest.mark.skipif(not _ENTRIES, reason="resolve golden dataset not generated")


def _normalize(r):
    return {"status": r["status"], "method": r["method"], "score": r["score"],
            "match_id": r["match_id"], "candidate_count": len(r.get("candidates") or [])}


def test_resolve_dataset_present():
    assert {"cif_exact", "domain_exact", "discovered_new"}.issubset(set(_ENTRIES.keys()))


@pytest.mark.parametrize("label", sorted(_ENTRIES.keys()))
def test_resolve_snapshot_parity(label):
    entry = _ENTRIES[label]
    actual = _normalize(run_async(resolve_entity_provider(**entry["input"])))
    assert actual == entry["snapshot"], f"resolve drift for {label}: {entry['snapshot']} → {actual}"
