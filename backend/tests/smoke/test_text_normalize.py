"""Smoke test: stored text is HTML-entity-free (ingestion normalization).

Normalization happens at ingestion (services.text_normalize) and a backfill
cleaned historical docs. The database must contain decoded, canonical strings so
search / matching / exports / embeddings operate on clean text.
"""

import html

from services.text_normalize import normalize_strings


def test_normalize_decodes_entities():
    assert normalize_strings("COMPA&#209;IA &amp; ASOCIADOS") == "COMPAÑIA & ASOCIADOS"
    assert normalize_strings("se&ntilde;al &aacute;rea") == html.unescape("se&ntilde;al &aacute;rea")


def test_normalize_is_recursive():
    src = {"name": "A&amp;B", "tags": ["x&#211;", "ok"], "nested": {"t": "&aacute;"}}
    out = normalize_strings(src)
    assert out["name"] == "A&B"
    assert out["tags"][0] == "xÓ"
    assert out["nested"]["t"] == "á"


def test_normalize_noop_on_clean_and_nonstring():
    assert normalize_strings("Clean Name SA") == "Clean Name SA"
    assert normalize_strings(42) == 42
    assert normalize_strings(None) is None
    assert normalize_strings(True) is True


def test_db_has_no_html_entities(base_url):
    """After backfill, the offender collections must store no HTML entities."""
    import os
    from pymongo import MongoClient

    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    pat = {"$regex": "&[#a-zA-Z0-9]+;"}
    checks = {
        "cnmv_entities": ["name", "fund_manager_name"],
        "public_procurement_contracts": ["title", "contracting_authority", "awardee_name"],
    }
    for coll, fields in checks.items():
        q = {"$or": [{f: pat} for f in fields]}
        remaining = db[coll].count_documents(q)
        assert remaining == 0, f"{coll} still has {remaining} HTML-encoded docs"
    client.close()
