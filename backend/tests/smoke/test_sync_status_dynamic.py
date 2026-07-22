"""Smoke test: /sync-status is 100% dynamic (ZERO HARDCODES rule).

Guards the architectural invariant that the public sync-status endpoint derives
its source list exclusively from the Intelligence Engine
(`engine_info.get_all_sources()`), never from a hardcoded array/dict.

This test FAILS the moment someone:
  - reintroduces a static source list in the endpoint,
  - drops a source so it no longer matches the engine,
  - returns legacy keys (e.g. `banco_espana`, `economic_intelligence`) that are
    not real engine source names.

It also asserts the self-extensibility contract: a source that exists in the
engine MUST appear in the endpoint with its full dynamic metric set — meaning a
newly added source module (+ META + profile) shows up with no endpoint edits.
"""

import requests

from services.intelligence_engine import engine_info

REQUIRED_FIELDS = {
    "name", "source", "phase", "frequency", "records", "signals_count",
    "supports_manual_ingestion", "last_run", "last_status", "duration_ms",
    "inserted_count", "error_count", "status",
}


def _fetch(base_url):
    r = requests.get(f"{base_url}/api/v1/public/intelligence/sync-status", timeout=20)
    assert r.status_code == 200, f"sync-status failed {r.status_code}: {r.text[:200]}"
    return r.json()


def test_at_least_16_sources(base_url):
    data = _fetch(base_url)
    sources = data.get("sources") or {}
    assert len(sources) >= 16, f"Expected >= 16 sources, got {len(sources)}: {list(sources)}"
    assert data.get("source_count") == len(sources)


def test_sources_match_engine_exactly(base_url):
    """Endpoint source keys must EQUAL engine_info.get_all_sources() — no extras,
    no legacy hardcodes, no omissions."""
    data = _fetch(base_url)
    endpoint_sources = set((data.get("sources") or {}).keys())
    engine_sources = set(engine_info.get_all_sources())
    assert endpoint_sources == engine_sources, (
        "sync-status drifted from the engine (possible hardcode).\n"
        f"  only in endpoint: {endpoint_sources - engine_sources}\n"
        f"  only in engine:   {engine_sources - endpoint_sources}"
    )


def test_no_legacy_hardcoded_keys(base_url):
    """The old hardcoded breakdown used keys that are NOT engine source names."""
    data = _fetch(base_url)
    sources = data.get("sources") or {}
    legacy_only = {"banco_espana", "placsp", "ine", "economic_intelligence"}
    leaked = legacy_only & set(sources.keys())
    assert not leaked, f"Legacy hardcoded keys leaked back into sync-status: {leaked}"


def test_every_source_is_self_describing(base_url):
    """Each source row must carry the full dynamic metric set (proves it is
    rendered from META + collections, not from a partial static dict)."""
    data = _fetch(base_url)
    for name, row in (data.get("sources") or {}).items():
        missing = REQUIRED_FIELDS - set(row.keys())
        assert not missing, f"Source '{name}' missing dynamic fields: {missing}"
        assert row["source"] == name
        assert isinstance(row["records"], int)
        assert row["phase"] in {"active", "stub", "derived"}


def test_arroba_profile_sources_all_present(base_url):
    """All 16 sources of the `arroba` profile must be present in sync-status."""
    profiles = requests.get(f"{base_url}/api/v1/intelligence/profiles", timeout=10).json()["profiles"]
    arroba = next(p for p in profiles if p["name"] == "arroba")
    data = _fetch(base_url)
    endpoint_sources = set((data.get("sources") or {}).keys())
    for s in arroba["sources"]:
        assert s in endpoint_sources, f"arroba source '{s}' missing from sync-status"


def test_manual_ingestion_flag_comes_from_meta(base_url):
    """`supports_manual_ingestion` must mirror each module's META exactly —
    no hardcoded source-name checks in the endpoint."""
    data = _fetch(base_url)
    for name, row in (data.get("sources") or {}).items():
        expected = engine_info.get_source_meta(name)["supports_manual_ingestion"]
        assert row["supports_manual_ingestion"] == expected, (
            f"manual flag mismatch for '{name}': endpoint={row['supports_manual_ingestion']} meta={expected}"
        )
