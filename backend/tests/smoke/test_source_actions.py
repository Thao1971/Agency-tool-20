"""Smoke test: operational actions are declared in META and exposed dynamically.

Per the 2c migration, each source's operational actions (sync/rebuild/upload/...)
live in its module META and surface through `sync-status`. The generic
DataSourcePage renders them — NO per-source forms, NO hardcoded action maps.
"""

import requests

from services.intelligence_engine import engine_info

ACTION_FIELDS = {"id", "label", "endpoint", "kind"}


def _sources(base_url):
    return requests.get(f"{base_url}/api/v1/public/intelligence/sync-status", timeout=20).json()["sources"]


def test_actions_exposed_and_match_meta(base_url):
    sources = _sources(base_url)
    for name, row in sources.items():
        expected = engine_info.get_source_meta(name)["actions"]
        assert row.get("actions") == expected, f"actions mismatch for '{name}'"


def test_known_sources_declare_actions(base_url):
    """cnmv + datacomex must declare their operational actions (regression guard)."""
    sources = _sources(base_url)
    cnmv_ids = {a["id"] for a in sources["cnmv"]["actions"]}
    assert {"sync", "match"}.issubset(cnmv_ids), f"cnmv actions: {cnmv_ids}"
    dcx = sources["datacomex"]["actions"]
    dcx_ids = {a["id"] for a in dcx}
    assert {"sync", "rebuild_metrics", "rebuild_signals", "upload"}.issubset(dcx_ids), f"datacomex actions: {dcx_ids}"
    assert any(a["kind"] == "upload" for a in dcx), "datacomex must expose an upload action"


def test_action_specs_well_formed(base_url):
    sources = _sources(base_url)
    for name, row in sources.items():
        for a in row.get("actions", []):
            missing = ACTION_FIELDS - set(a.keys())
            assert not missing, f"{name} action {a.get('id')} missing {missing}"
            assert a["endpoint"].startswith("/"), f"{name} action endpoint must be a relative API path"
            assert a["kind"] in {"button", "upload"}


def test_stub_sources_have_no_actions(base_url):
    """OEPM legacy stub declares no operational actions."""
    sources = _sources(base_url)
    assert sources["oepm"]["actions"] == []
