"""Source: DataComex — foreign trade aggregates by CNAE."""

from typing import Dict, Tuple
from database import db


META = {
    "display_name": "DataComex",
    "collection": "datacomex_raw_data",
    "frequency": "Mensual (día 15, Playwright)",
    "signal_source": "datacomex",
    "audit_action": None,
    "phase": "active",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "sync_log": {"collection": "datacomex_sync_logs", "time_field": "synced_at"},
    "display_fields": ["flow", "period", "country", "taric_code", "taric_description", "euros", "kilos"],
    "field_labels": {"flow": "Flujo", "period": "Periodo", "country": "País", "taric_code": "TARIC", "taric_description": "Descripción", "euros": "Euros", "kilos": "Kilos"},
    "actions": [
        {"id": "sync", "label": "Sincronizar DataComex", "endpoint": "/datacomex/sync", "params": {"years": "2022,2023,2024,2025"}, "kind": "button"},
        {"id": "rebuild_metrics", "label": "Recalcular métricas", "endpoint": "/datacomex/rebuild-metrics", "kind": "button"},
        {"id": "rebuild_signals", "label": "Recalcular señales", "endpoint": "/datacomex/rebuild-signals", "kind": "button"},
        {"id": "upload", "label": "Subir CSV", "endpoint": "/datacomex/upload-csv", "kind": "upload"},
    ],
    "sidebar_dot": "bg-cyan-500",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cnae = master.get("cnae_primary", "")
    if not cnae:
        return {}, {"source": "datacomex", "found": False, "reason": "no_cnae"}

    # Match the 2-digit CNAE division
    cnae_2 = cnae[:2] if len(cnae) >= 2 else cnae
    docs = await db.datacomex_records.find(
        {"cnae_code": {"$regex": f"^{cnae_2}"}},
        {"_id": 0, "exports_eur": 1, "imports_eur": 1, "trade_balance_eur": 1, "year": 1}
    ).sort("year", -1).limit(3).to_list(3)

    if not docs:
        return {}, {"source": "datacomex", "found": False, "reason": "no_match", "cnae_2": cnae_2}

    latest = docs[0]
    fields = {
        "datacomex.latest_year": latest.get("year"),
        "datacomex.exports_eur": latest.get("exports_eur"),
        "datacomex.imports_eur": latest.get("imports_eur"),
        "datacomex.trade_balance_eur": latest.get("trade_balance_eur"),
        "datacomex.history": docs,
    }
    fields = {k: v for k, v in fields.items() if v not in (None, "", [], {})}
    return fields, {"source": "datacomex", "found": True, "cnae_2": cnae_2}
