"""Source: activos_inmobiliarios — Catastro. STUB Fase 2.
Origen futuro: Sede Catastro (API OVC). Datos: superficie construida, uso,
referencias catastrales asociadas a una compañía.
"""
from typing import Dict, Tuple
from database import db


META = {
    "display_name": "Activos Inmobiliarios (Catastro)",
    "collection": "activos_inmobiliarios",
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
    "sidebar_dot": "bg-orange-400",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cif = (master.get("cif") or "").upper().replace("-", "").replace(" ", "").strip()
    if not cif:
        return {}, {"source": "catastro", "found": False, "reason": "no_cif"}
    docs = await db.activos_inmobiliarios.find({"cif_normalized": cif}, {"_id": 0}).to_list(200)
    if not docs:
        return {}, {"source": "catastro", "found": False, "reason": "no_match"}
    total_area = sum((d.get("built_area_sqm") or 0) for d in docs)
    fields = {
        "catastro.properties_count": len(docs),
        "catastro.total_built_area_sqm": total_area,
        "catastro.uses": sorted({d.get("use") for d in docs if d.get("use")}),
    }
    return fields, {"source": "catastro", "found": True, "count": len(docs)}
