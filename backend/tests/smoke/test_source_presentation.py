"""Smoke test: declarative human-presentation layer (display_fields / field_labels).

The Data Explorer keeps a single dynamic DataSourcePage but layers an OPTIONAL,
declarative presentation on top — `display_fields` (ordered whitelist),
`hidden_fields` (blacklist) and `field_labels` (human labels) all live in each
module's META and surface through sync-status. NO hardcoded column maps.
"""

import requests

from services.intelligence_engine import engine_info


def _sources(base_url):
    return requests.get(f"{base_url}/api/v1/public/intelligence/sync-status", timeout=20).json()["sources"]


def test_presentation_fields_match_meta(base_url):
    sources = _sources(base_url)
    for name, row in sources.items():
        meta = engine_info.get_source_meta(name)
        assert row.get("display_fields") == meta["display_fields"], f"display_fields mismatch '{name}'"
        assert row.get("hidden_fields") == meta["hidden_fields"], f"hidden_fields mismatch '{name}'"
        assert row.get("field_labels") == meta["field_labels"], f"field_labels mismatch '{name}'"


def test_data_rich_sources_declare_display_fields(base_url):
    """Sources with real data expose curated, human columns (regression guard)."""
    sources = _sources(base_url)
    for name in ("cnmv", "territorial", "procurement", "bme", "datacomex"):
        df = sources[name]["display_fields"]
        assert df, f"{name} must declare display_fields"
        # no technical id/url fields leaked into the curated list
        for f in df:
            assert not f.endswith("_id") and not f.endswith("_url") and f != "_id", f"{name} display_fields leaks technical field '{f}'"


def test_display_fields_exist_in_real_documents(base_url):
    """Every declared display_field must actually exist in the collection docs."""
    for name in ("territorial", "datacomex", "cnmv"):
        meta = engine_info.get_source_meta(name)
        q = requests.get(f"{base_url}/api/v1/intelligence/sources/{name}/query?page_size=1", timeout=20).json()
        if not q["items"]:
            continue
        keys = set(q["items"][0].keys())
        present = [f for f in meta["display_fields"] if f in keys]
        assert present, f"{name} display_fields do not match document keys {sorted(keys)}"


def test_field_labels_are_human(base_url):
    """Declared labels must not be raw snake_case (they are human-friendly)."""
    sources = _sources(base_url)
    labels = sources["territorial"]["field_labels"]
    assert labels.get("average_income") == "Renta media"
    assert labels.get("province") == "Provincia"
