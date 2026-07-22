"""Smoke test: the DATA sidebar is 100% dynamic (ZERO HARDCODES rule).

Guards that the sidebar catalog endpoint derives its source list exclusively from
the Intelligence Engine (`engine_info.get_all_sources()` + each module's META),
never from a static array in the frontend or backend.

Also asserts Layout.js no longer hardcodes the DATA source items (it must consume
`/intelligence/sources/sidebar` at runtime).
"""

import os

import requests

from services.intelligence_engine import engine_info

LAYOUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "frontend", "src", "components", "Layout.js",
)


def _catalog(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/sources/sidebar", timeout=15)
    assert r.status_code == 200, f"sidebar catalog failed {r.status_code}: {r.text[:200]}"
    return r.json()


def test_sidebar_catalog_matches_engine(base_url):
    """Sidebar sources must equal the engine sources where META.show_in_sidebar."""
    data = _catalog(base_url)
    items = data.get("groups", {}).get("data", [])
    endpoint_sources = [i["source"] for i in items]

    expected = [
        n for n in engine_info.get_all_sources()
        if engine_info.get_source_meta(n)["show_in_sidebar"]
    ]
    assert endpoint_sources == expected, (
        "Sidebar drifted from the engine (possible hardcode).\n"
        f"  endpoint: {endpoint_sources}\n  engine:   {expected}"
    )
    # The 15 product sources must be present (OEPM legacy stub is hidden).
    assert len(endpoint_sources) >= 15, f"Expected >= 15 sidebar sources, got {len(endpoint_sources)}"
    assert "oepm" not in endpoint_sources, "Legacy OEPM stub must NOT appear in the sidebar"


def test_sidebar_items_are_self_describing(base_url):
    """Every sidebar item carries label + route + dot derived from its META."""
    data = _catalog(base_url)
    for item in data.get("groups", {}).get("data", []):
        for field in ("source", "label", "route", "dot", "phase"):
            assert item.get(field), f"sidebar item {item.get('source')} missing '{field}'"
        meta = engine_info.get_source_meta(item["source"])
        assert item["label"] == meta["display_name"]


def test_layout_has_no_hardcoded_data_array():
    """Layout.js must NOT statically list data sources — it derives them at runtime."""
    with open(LAYOUT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    # The dynamic section must be wired to the engine catalog endpoint.
    assert "/intelligence/sources/sidebar" in content, "Layout.js must fetch the dynamic sidebar catalog"
    assert "dataSources.map" in content, "Layout.js DATA section must render from dynamic state"
    # Legacy hardcoded source labels must be gone from the static config.
    for legacy in ("label: 'Companies Master'", "label: 'Agency Results'", "label: 'BORME'", "label: 'DataComex'"):
        assert legacy not in content, f"Hardcoded sidebar item leaked back into Layout.js: {legacy}"
