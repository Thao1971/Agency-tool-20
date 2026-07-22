"""Source: employment_statistics — Seguridad Social + SEPE aggregates.

Aggregation level: NOT per company. By CNAE × Provincia × CCAA.
Origin: datasets abiertos de Seg. Social y SEPE.
"""

from typing import Dict, Tuple
from database import db


META = {
    "display_name": "Empleo (INE / SEPE)",
    "collection": "estadisticas_empleo",
    "frequency": "Mensual (día 5)",
    "signal_source": "estadisticas_empleo",
    "audit_action": "public_source_ingest_estadisticas_empleo",
    "phase": "active",
    "supports_manual_ingestion": True,
    "ingest_runner": "ingest_estadisticas_empleo",
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "display_fields": ["ccaa", "period", "unemployment_rate"],
    "field_labels": {"ccaa": "Comunidad Autónoma", "period": "Periodo", "unemployment_rate": "Tasa de paro"},
    "sidebar_dot": "bg-lime-400",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cnae = master.get("cnae_primary", "")
    province = master.get("province") or master.get("address_province")

    if not cnae and not province:
        return {}, {"source": "employment", "found": False, "reason": "no_cnae_no_province"}

    # Latest aggregate matching cnae/province/ccaa
    query: Dict = {}
    if cnae:
        query["cnae_code"] = {"$regex": f"^{cnae[:2]}"}
    if province:
        query["province"] = province

    rec = await db.estadisticas_empleo.find_one(
        query, {"_id": 0}, sort=[("period", -1)]
    )
    if not rec:
        return {}, {"source": "employment", "found": False, "reason": "no_match"}

    fields = {
        "employment.sector_employment_growth": rec.get("sector_employment_growth"),
        "employment.province_employment_growth": rec.get("province_employment_growth"),
        "employment.employment_growth_rate": rec.get("employment_growth_rate"),
        "employment.unemployment_rate": rec.get("unemployment_rate"),
        "employment.period": rec.get("period"),
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    return fields, {"source": "employment", "found": True, "period": rec.get("period")}
