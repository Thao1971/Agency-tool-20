"""Source: territorial_statistics — INE socio-economic context by territory.

Aggregation level: Municipio / Provincia / CCAA. NOT per company.
Origin: INE (Renta, Actividad económica, Demografía, Paro).
"""

from typing import Dict, Tuple
from database import db


META = {
    "display_name": "Territoriales (INE)",
    "collection": "estadisticas_territoriales",
    "frequency": "Anual (1 febrero)",
    "signal_source": "estadisticas_territoriales",
    "audit_action": "public_source_ingest_estadisticas_territoriales",
    "phase": "active",
    "supports_manual_ingestion": True,
    "ingest_runner": "ingest_estadisticas_territoriales",
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "display_fields": ["province", "year", "average_income"],
    "field_labels": {"province": "Provincia", "year": "Año", "average_income": "Renta media"},
    "sidebar_dot": "bg-teal-400",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    municipio = master.get("municipio") or master.get("address_city")
    province = master.get("province") or master.get("address_province")
    ccaa = master.get("ccaa")

    if not (municipio or province or ccaa):
        return {}, {"source": "territorial", "found": False, "reason": "no_territory"}

    # Prefer most granular available: municipio > province > ccaa
    query: Dict = {}
    level = None
    if municipio:
        query = {"municipio": municipio}
        level = "municipio"
    elif province:
        query = {"province": province}
        level = "province"
    else:
        query = {"ccaa": ccaa}
        level = "ccaa"

    rec = await db.estadisticas_territoriales.find_one(
        query, {"_id": 0}, sort=[("year", -1)]
    )
    if not rec:
        return {}, {"source": "territorial", "found": False, "reason": "no_match", "level": level}

    fields = {
        "territorial.level": level,
        "territorial.average_income": rec.get("average_income"),
        "territorial.population_growth": rec.get("population_growth"),
        "territorial.economic_activity_index": rec.get("economic_activity_index"),
        "territorial.unemployment_rate": rec.get("unemployment_rate"),
        "territorial.population_density": rec.get("population_density"),
        "territorial.year": rec.get("year"),
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    return fields, {"source": "territorial", "found": True, "level": level, "year": rec.get("year")}
