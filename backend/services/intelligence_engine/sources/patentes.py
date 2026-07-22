"""Source: patentes_y_marcas — OEPM. STUB Fase 2.
Origen futuro: https://invenes.oepm.es/InvenesWeb/  (búsqueda pública de patentes/marcas).
Colección: patentes_y_marcas. Match por CIF/razón social.
"""
from typing import Dict, Tuple
from database import db


META = {
    "display_name": "Patentes y Marcas (OEPM)",
    "collection": "patentes_y_marcas",
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
    "sidebar_dot": "bg-fuchsia-400",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cif = (master.get("cif") or "").upper().replace("-", "").replace(" ", "").strip()
    name = (master.get("legal_name") or "").upper().strip()
    if not cif and not name:
        return {}, {"source": "patentes", "found": False, "reason": "no_match_key"}
    q = {"$or": [{"cif_normalized": cif}] if cif else []}
    if name:
        q["$or"].append({"holder_name_normalized": name})
    if not q["$or"]:
        return {}, {"source": "patentes", "found": False, "reason": "no_match_key"}
    docs = await db.patentes_y_marcas.find(q, {"_id": 0}).to_list(100)
    if not docs:
        return {}, {"source": "patentes", "found": False, "reason": "no_match"}
    fields = {
        "patentes.count": len(docs),
        "patentes.patents": sum(1 for d in docs if d.get("type") == "patent"),
        "patentes.trademarks": sum(1 for d in docs if d.get("type") == "trademark"),
        "patentes.industrial_designs": sum(1 for d in docs if d.get("type") == "design"),
    }
    return fields, {"source": "patentes", "found": True, "count": len(docs)}
