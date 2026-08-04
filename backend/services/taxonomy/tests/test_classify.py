"""Company Classification Engine v1 — clasificación multiclase determinista + fingerprint + persistencia."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "taxonomy_cls_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["taxonomy_cls_test"]
except Exception:
    pass

import asyncio
from services.taxonomy import classify as CLS

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def _by_role(rows, role):
    return [r for r in rows if r["role"] == role]


def test_adtech_platform_multiclass():
    # Plataforma tecnológica de publicidad contextual con IA (el caso del canon)
    r = _run(CLS.classify({"company_id": "ACME", "inputs": {
        "cnae": "6201",
        "name": "ACME Contextual",
        "description": "Plataforma de publicidad programática y contextual basada en inteligencia "
                       "artificial para anunciantes y agencias. SaaS B2B."}}))
    sectors = {x["taxonomy_id"]: x for x in r["classifications"]["sector"]}
    # S03 (Medios/Marketing) y S02 (Tecnología) presentes; multiclase con primary + secondary
    assert "S03" in sectors and "S02" in sectors
    assert any(s["role"] == "primary" for s in sectors.values())
    inds = [x["taxonomy_id"] for x in r["classifications"]["industry"]]
    assert "IND-S03-adtech" in inds
    verticals = [x["label_es"] for x in r["classifications"]["verticals"]]
    assert "AdTech" in verticals
    assert r["fingerprint"]["sector"] > 0 and r["overall_confidence"] > 0
    # evidencia presente en toda clasificación
    assert all(x.get("evidence") for x in r["classifications"]["sector"])


def test_core_vs_used_technology():
    # Empresa tecnológica con IA como núcleo → core_technology True
    r = _run(CLS.classify({"company_id": "AICO", "inputs": {
        "cnae": "6201", "name": "AI Core",
        "description": "Desarrollo de software basado en inteligencia artificial y machine learning."}}))
    techs = r["classifications"]["technologies"]
    ai = next((t for t in techs if "Inteligencia" in t["label_es"] or "IA" in t["label_es"]), None)
    assert ai is not None and ai.get("core_technology") is True
    # Una agencia que solo 'usa' IA no la marca como core
    r2 = _run(CLS.classify({"company_id": "AGX", "inputs": {
        "cnae": "7311", "name": "Agencia X",
        "description": "Agencia de publicidad creativa. Utilizamos inteligencia artificial puntualmente."}}))
    techs2 = r2["classifications"]["technologies"]
    ai2 = next((t for t in techs2 if "Inteligencia" in t["label_es"] or "IA" in t["label_es"]), None)
    assert (ai2 is None) or (ai2.get("core_technology") is False)


def test_persistence_idempotent():
    inp = {"company_id": "PCO", "inputs": {"cnae": "6201", "name": "Persist Co",
                                           "description": "Desarrollo de software a medida."}}
    _run(CLS.classify(inp))
    _run(CLS.classify(inp))   # reclasificar no duplica
    from database import db
    n = _run(db.company_classifications.count_documents({"company_id": "PCO"}))
    stored = _run(CLS.get_company_classification("PCO"))
    assert n == len(stored["classifications"]) and stored["fingerprint"] is not None


def test_semantic_signal_classifies_without_cnae():
    from database import db
    # Perfil del Semantic Engine (sin CNAE ni descripción en inputs)
    _run(db.semantic_profiles.insert_one({
        "master_id": "SEMCO",
        "economic_activity": {"value": "agencia de publicidad y marketing digital"},
        "capabilities": [{"value": "branding"}, {"value": "compra de medios"}],
        "technologies": [{"value": "inteligencia artificial"}],
    }))
    r = _run(CLS.classify({"company_id": "SEMCO", "inputs": {"name": "SemCo"}}))
    sectors = [x["taxonomy_id"] for x in r["classifications"]["sector"]]
    assert "S03" in sectors                                   # el sector sale del perfil semántico
    inds = [x["label_es"] for x in r["classifications"]["industry"]]
    assert any("Agencias" in i for i in inds)
    # desactivar la señal semántica → ya no clasifica por ese texto
    r2 = _run(CLS.classify({"company_id": "SEMCO", "inputs": {"name": "SemCo"}, "use_semantic": False}))
    assert "S03" not in [x["taxonomy_id"] for x in r2["classifications"]["sector"]]


def test_cnae_group_precision():
    from services.taxonomy import bridge as B
    assert B.anchor_from_cnae("6311")[0] == "S02"   # hosting/proceso de datos → Tecnología
    assert B.anchor_from_cnae("6312")[0] == "S03"   # portal web → Medios
    assert B.anchor_from_cnae("7211")[0] == "S05"   # I+D biotech → Salud
    assert B.anchor_from_cnae("2110")[0] == "S05"   # farma
    assert B.anchor_from_cnae("62")[0] == "S02"     # división (fallback) sigue funcionando


if __name__ == "__main__":
    for fn in (test_adtech_platform_multiclass, test_core_vs_used_technology, test_persistence_idempotent,
               test_semantic_signal_classifies_without_cnae, test_cnae_group_precision):
        fn(); print("OK", fn.__name__)
