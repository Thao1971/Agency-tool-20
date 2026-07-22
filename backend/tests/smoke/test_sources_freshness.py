"""Smoke test: every populated source reports a real 'última actualización'.

The audit requirement is that ALL active sources show a last-update timestamp,
resolved uniformly from audit logs → source sync-logs → freshest document.
"""

import requests


def _sources(base_url):
    return requests.get(f"{base_url}/api/v1/public/intelligence/sync-status", timeout=20).json()["sources"]


def test_active_sources_have_last_update(base_url):
    sources = _sources(base_url)
    missing = []
    for name, row in sources.items():
        # Stubs / empty collections legitimately have no update timestamp.
        if row["phase"] == "stub" or row["records"] == 0:
            continue
        if not row.get("last_run"):
            missing.append(name)
    assert not missing, f"Active sources without 'última actualización': {missing}"


def test_grants_endpoint_fixed_and_has_data(base_url):
    """BDNS endpoint fix: grants must expose real concessions with curated fields."""
    sources = _sources(base_url)
    grants = sources["grants"]
    assert grants["records"] > 0, "grants (BDNS) collection is empty — ingestion endpoint may be broken"
    q = requests.get(f"{base_url}/api/v1/intelligence/sources/grants/query?page_size=1", timeout=20).json()
    if q["items"]:
        keys = set(q["items"][0].keys())
        assert {"beneficiary_name", "amount_eur", "program"}.issubset(keys), f"grants schema unexpected: {sorted(keys)}"


def test_procurement_sync_action_endpoint_is_valid(base_url):
    """PLACSP sync button must target an existing route (was /procurement, now /public-procurement)."""
    sources = _sources(base_url)
    actions = sources["procurement"]["actions"]
    sync = next((a for a in actions if a["id"] == "sync_placsp"), None)
    assert sync and sync["endpoint"].startswith("/public-procurement/"), f"PLACSP action endpoint wrong: {sync}"
