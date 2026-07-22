"""M2-preparation Snapshot-Diff Tests — enrich() parity over a frozen golden dataset.

These tests are the PARITY NET for migration M2 (intelligence_engine reading
companies_master → master_companies). They recompute `enrich_company` for each frozen
(master_company_id, profile) pair and assert the deterministic output (fields,
sources_with_data, found_map, engine_version) is byte-identical to the recorded snapshot.

Any future M2 change that alters a computed enrichment value WILL fail here.
Regenerate intentionally (only when a change is approved) with:
    python -m tests.golden.gen_enrich_golden
"""
import pytest

from smoke_loop import run_async
from services.intelligence_engine import enrich_company
from tests.golden.enrich_snapshot_util import load_snapshots, normalize, diff

_SNAPS = load_snapshots()
_ENTRIES = _SNAPS.get("entries", {})

pytestmark = pytest.mark.skipif(not _ENTRIES, reason="golden snapshot dataset not generated")


def test_golden_dataset_present_and_diverse():
    assert len(_ENTRIES) >= 10, "expected a non-trivial frozen golden dataset"
    buckets = {v.get("_bucket") for v in _ENTRIES.values()}
    # diversity: at least rich + one other bucket
    assert "rich_financials" in buckets and len(buckets) >= 2


@pytest.mark.parametrize("key", sorted(_ENTRIES.keys()))
def test_enrich_snapshot_parity(key):
    expected = _ENTRIES[key]
    mid, profile = key.split("::")
    result = run_async(enrich_company(mid, profile=profile))
    actual = normalize(result)
    drifts = diff(expected, actual)
    assert not drifts, f"enrich drift for {key}:\n" + "\n".join(drifts[:20])


def test_enrich_determinism_double_run():
    """Same input run twice → identical normalized output (no volatile leakage)."""
    key = sorted(_ENTRIES.keys())[0]
    mid, profile = key.split("::")
    a = normalize(run_async(enrich_company(mid, profile=profile)))
    b = normalize(run_async(enrich_company(mid, profile=profile)))
    assert diff(a, b) == [], "enrich is non-deterministic across runs"
