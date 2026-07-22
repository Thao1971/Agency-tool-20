"""Guard Tests — Master Record Provider (M2 internal coexistence).

Enforce the architectural rules:
- single public contract (the backend is chosen INTERNALLY, never via API);
- default backend is LEGACY (production-safe);
- the legacy path is byte-identical to the previous direct fetch (zero regression);
- the canonical path is transparent: it never causes master_not_found (falls back to legacy).
"""
from smoke_loop import run_async
from database import db
from services.intelligence_engine.master_provider import (
    get_master_record, active_master_source, LEGACY, CANONICAL,
)


def _a_master_id():
    d = run_async(db.companies_master.find_one({}, {"_id": 0, "master_company_id": 1}))
    return d["master_company_id"]


def test_default_source_is_legacy():
    assert active_master_source() == LEGACY


def test_legacy_path_is_byte_identical_to_direct_fetch():
    mid = _a_master_id()
    direct = run_async(db.companies_master.find_one({"master_company_id": mid}, {"_id": 0}))
    via_provider = run_async(get_master_record(mid, source=LEGACY))
    assert via_provider == direct, "legacy provider path must be byte-identical (zero regression)"


def test_canonical_falls_back_transparently():
    """Canonical datasets are disjoint today (overlap=0); the canonical path must still
    return a usable record by falling back to legacy — never master_not_found."""
    mid = _a_master_id()
    doc = run_async(get_master_record(mid, source=CANONICAL))
    assert doc is not None
    assert doc["master_company_id"] == mid


def test_unknown_id_returns_none_in_both_modes():
    assert run_async(get_master_record("mc_does_not_exist", source=LEGACY)) is None
    assert run_async(get_master_record("mc_does_not_exist", source=CANONICAL)) is None
