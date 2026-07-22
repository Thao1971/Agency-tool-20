"""Source: identity — companies_master core fields.

Always returns what's already on the master record. Useful as a baseline so
downstream products know the canonical identity (legal_name, cif, domain) even
if nothing else enriched.
"""

from typing import Dict, Tuple


META = {
    "display_name": "Identidad (Master)",
    "collection": "companies_master",
    "frequency": "Continuo (núcleo canónico)",
    "signal_source": None,
    "audit_action": None,
    "phase": "derived",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "timestamp_field": "updated_at",
    "display_fields": ["legal_name", "cif", "category_name", "confidence_score", "merge_status", "website"],
    "field_labels": {"legal_name": "Razón social", "cif": "CIF", "category_name": "Categoría", "confidence_score": "Confianza", "merge_status": "Estado", "website": "Web"},
    "actions": [
        {"id": "ingest_scraper", "label": "Ingestar desde scraper", "endpoint": "/master/ingest-all-scraper", "kind": "button"},
        {"id": "bulk_verify", "label": "Verificar en lote", "endpoint": "/master/bulk-verify", "kind": "button"},
        {"id": "bulk_publish", "label": "Publicar a Valuo", "endpoint": "/master/bulk-publish-to-valuo", "kind": "button"},
    ],
    "sidebar_dot": "bg-blue-500",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    fields = {}
    for k in ("legal_name", "cif", "domain", "website", "commercial_names",
              "aliases", "category_name", "cnae_primary", "country", "confidence_score"):
        v = master.get(k)
        if v:
            fields[f"identity.{k}"] = v
    meta = {"source": "identity", "found": bool(fields)}
    return fields, meta
