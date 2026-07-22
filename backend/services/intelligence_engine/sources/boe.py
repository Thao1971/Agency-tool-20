"""Source: eventos_regulatorios — BOE. STUB Fase 2.
Origen futuro: API BOE (https://boe.es/datosabiertos/api/). Eventos legales que
mencionan a la compañía (sanciones, autorizaciones, ayudas individuales).
"""
from typing import Dict, Tuple
from database import db


META = {
    "display_name": "Eventos Regulatorios (BOE)",
    "collection": "eventos_regulatorios",
    "frequency": "Fase 2 (pendiente)",
    "signal_source": None,
    "audit_action": None,
    "phase": "stub",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "sidebar_dot": "bg-amber-600",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cif = (master.get("cif") or "").upper().replace("-", "").replace(" ", "").strip()
    name = (master.get("legal_name") or "").upper().strip()
    q = {"$or": []}
    if cif:
        q["$or"].append({"cif_normalized": cif})
    if name:
        q["$or"].append({"company_name_normalized": name})
    if not q["$or"]:
        return {}, {"source": "boe", "found": False, "reason": "no_match_key"}
    docs = await db.eventos_regulatorios.find(q, {"_id": 0}).to_list(200)
    if not docs:
        return {}, {"source": "boe", "found": False, "reason": "no_match"}
    fields = {
        "boe.events_count": len(docs),
        "boe.last_event_date": max((d.get("published_at") or "" for d in docs), default=None),
        "boe.event_types": sorted({d.get("event_type") for d in docs if d.get("event_type")}),
    }
    return fields, {"source": "boe", "found": True, "count": len(docs)}
