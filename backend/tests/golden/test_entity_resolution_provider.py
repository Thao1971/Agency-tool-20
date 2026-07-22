"""Guard Tests — Entity Resolution coexistence provider + canonical resolver (M3).

Enforce: single public contract (backend chosen internally), default LEGACY (production-safe),
legacy path byte-identical, canonical resolver returns the legacy-compatible shape,
deterministic ids (DER5), and the legacy↔canonical xref bridge (DER3).
"""
from smoke_loop import run_async
from database import db
from services.entity_resolution import resolve_entity
from services.entity_resolution_provider import (
    resolve_entity_provider, active_resolution_source, LEGACY, CANONICAL,
)
from services.data_layer.master.identity_resolver import (
    resolve_identity, deterministic_master_id, link_legacy_master, THRESHOLDS,
)

_SAMPLE = {"legal_name": "ZZZ NONEXISTENT GOLDEN CO", "cif": "B00000000"}


def test_default_source_is_legacy():
    assert active_resolution_source() == LEGACY


def test_provider_legacy_is_byte_identical():
    direct = run_async(resolve_entity(**_SAMPLE))
    via = run_async(resolve_entity_provider(**_SAMPLE))
    assert via == direct, "legacy provider path must be byte-identical (zero regression)"


def test_frozen_thresholds():
    assert THRESHOLDS == {"cif_exact": 1.0, "domain_exact": 0.95, "name_province": 0.70,
                          "auto_merge": 0.95, "conflict": 0.70}


def test_canonical_returns_legacy_compatible_shape():
    r = run_async(resolve_identity(**_SAMPLE, audit=False))
    assert set(r.keys()) >= {"status", "score", "method", "match_id", "candidates"}
    assert r["status"] in ("auto_merged", "conflict", "discovered")


def test_deterministic_master_id_is_reproducible():
    a = deterministic_master_id(cif_normalized="B12345678")
    b = deterministic_master_id(cif_normalized="B12345678")
    c = deterministic_master_id(cif_normalized="B99999999")
    assert a == b and a != c
    assert a.startswith("mc_")
    # priority: cif over domain over name
    assert deterministic_master_id(cif_normalized="B1", domain="x.com") == deterministic_master_id(cif_normalized="B1")


def test_legacy_canonical_xref_bridge():
    """DER3 — link legacy master_company_id ↔ canonical master_id in entity_xref (append-only)."""
    mcid, mid = "mc_golden_bridge_test", "mc_canonical_bridge_test"
    run_async(link_legacy_master(mcid, mid))
    doc = run_async(db.entity_xref.find_one(
        {"id_type": "master_company_id", "external_id": mcid}, {"_id": 0}))
    assert doc and doc["master_id"] == mid
    run_async(db.entity_xref.delete_one({"id_type": "master_company_id", "external_id": mcid}))
