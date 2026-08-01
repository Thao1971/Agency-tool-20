"""F3 — clasificación por lotes sobre master_companies + informe de auditoría (fixture, mongomock)."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "taxonomy_batch_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["taxonomy_batch_test"]
except Exception:
    pass

import asyncio
from services.taxonomy import batch as BATCH
from services.taxonomy import audit as AUDIT

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def _master(mid, legal, cnae, desc, cnae_desc=""):
    return {"master_id": mid, "identity": {"legal_name": legal, "business_description": desc},
            "classification": {"cnae_code": cnae, "cnae_description": cnae_desc}}


def _seed_universe():
    from database import db
    docs = [
        _master("M1", "ACME Contextual", "6201", "Plataforma de publicidad programática y contextual con inteligencia artificial. SaaS B2B."),
        _master("M2", "Agencia Creativa Sur", "7311", "Agencia de publicidad creativa."),
        _master("M3", "Constructora Norte", "4121", "Construcción de edificios residenciales."),
        _master("M4", "Clínica Salud", "8610", "Hospital y atención sanitaria."),
        _master("M5", "MergedCo", "6201", "x", ""),
    ]
    _run(db.master_companies.insert_many(docs))
    _run(db.master_companies.update_one({"master_id": "M5"}, {"$set": {"merge_status": "merged"}}))


def test_classify_batch_runs_and_persists():
    _seed_universe()
    stats = _run(BATCH.classify_batch())
    assert stats["processed"] == 4          # M5 (merged) se salta
    assert stats["classified"] >= 3
    assert sum(stats["by_primary_sector"].values()) == stats["classified"]
    assert 0 <= stats["avg_confidence"] <= 1
    # persistido
    from database import db
    assert _run(db.company_fingerprint.count_documents({})) == 4


def test_audit_report_and_markdown():
    rep = _run(AUDIT.audit_report(sample_n=10))
    assert rep["total_classified"] == 4
    assert rep["distribution_by_sector"] and rep["distribution_by_sector"][0]["count"] >= 1
    assert len(rep["sample"]) == 4
    md = AUDIT.render_audit_md(rep)
    assert "Auditoría de clasificación" in md and "Distribución por sector" in md


if __name__ == "__main__":
    for fn in (test_classify_batch_runs_and_persists, test_audit_report_and_markdown):
        fn(); print("OK", fn.__name__)
