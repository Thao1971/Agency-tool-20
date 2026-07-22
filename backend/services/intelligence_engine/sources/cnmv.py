"""Source: CNMV — investor entity + potential buyers for CNAE."""

from typing import Dict, Tuple
from database import db


META = {
    "display_name": "CNMV",
    "collection": "cnmv_entities",
    "frequency": "Diario ~04:00 UTC (scheduler) + manual",
    "signal_source": "cnmv",
    "audit_action": None,
    "phase": "active",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "sync_log": {"collection": "cnmv_sync_logs", "time_field": "synced_at"},
    "display_fields": ["name", "entity_type_label", "nif", "fund_manager_name", "cnae_codes", "status", "registration_date"],
    "field_labels": {"name": "Nombre", "entity_type_label": "Tipo de entidad", "nif": "NIF", "fund_manager_name": "Gestora", "cnae_codes": "CNAE", "status": "Estado", "registration_date": "Fecha de registro"},
    "actions": [
        {"id": "sync", "label": "Sincronizar CNMV", "endpoint": "/cnmv/sync", "params": {"types": "fcr,scr"}, "kind": "button"},
        {"id": "match", "label": "Match empresas", "endpoint": "/cnmv/match-companies", "kind": "button"},
    ],
    "sidebar_dot": "bg-rose-400",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    fields = {}
    meta = {"source": "cnmv", "found": False}

    cif = master.get("cif", "")
    if cif:
        entity = await db.cnmv_entities.find_one(
            {"nif": cif},
            {"_id": 0, "entity_type": 1, "name": 1, "registration_number": 1}
        )
        if entity:
            fields["cnmv.entity_type"] = entity.get("entity_type")
            fields["cnmv.entity_name"] = entity.get("name")
            fields["cnmv.registration_number"] = entity.get("registration_number")
            meta["found"] = True
            meta["entity_type"] = entity.get("entity_type")

    # Potential buyers for CNAE
    cnae = master.get("cnae_primary", "")
    if cnae:
        try:
            from services.cnmv_investor_intelligence import get_buyers_for_cnae
            buyers = await get_buyers_for_cnae(cnae)
            total = buyers.get("total_buyers", 0) + buyers.get("total_managers", 0)
            if total > 0:
                fields["cnmv.potential_buyers_count"] = total
                fields["cnmv.buyers_breakdown"] = {
                    "buyers": buyers.get("total_buyers", 0),
                    "managers": buyers.get("total_managers", 0),
                }
                meta["potential_buyers"] = total
        except Exception as e:
            meta["buyers_error"] = str(e)[:100]

    return fields, meta
