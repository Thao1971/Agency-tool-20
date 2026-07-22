"""Source: economic_intel — CNAE sector profile."""

from typing import Dict, Tuple


META = {
    "display_name": "Economic Intelligence",
    "collection": "economic_metrics",
    "frequency": "Diario — 04:15 Madrid",
    "signal_source": "ine",
    "audit_action": None,
    "phase": "derived",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "timestamp_field": "last_updated",
    "display_fields": ["cnae_code", "metric", "period", "value", "unit"],
    "field_labels": {"cnae_code": "CNAE", "metric": "Métrica", "period": "Periodo", "value": "Valor", "unit": "Unidad"},
    "actions": [
        {"id": "rebuild", "label": "Recalcular Economic Intelligence", "endpoint": "/economic-intelligence/rebuild", "kind": "button"},
    ],
    "sidebar_dot": "bg-amber-400",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cnae = master.get("cnae_primary", "")
    if not cnae:
        return {}, {"source": "economic_intel", "found": False, "reason": "no_cnae"}

    try:
        from services.economic_intelligence import get_cnae_economic_profile
        econ = await get_cnae_economic_profile(cnae)
    except Exception as e:
        return {}, {"source": "economic_intel", "found": False, "error": str(e)[:100]}

    if not econ.get("sources_available"):
        return {}, {"source": "economic_intel", "found": False, "reason": "empty_profile"}

    fields = {
        "economic_intel.cnae_code": cnae,
        "economic_intel.revenue_sector": (econ.get("revenue") or {}).get("value"),
        "economic_intel.active_companies": (econ.get("active_companies_national") or {}).get("value"),
        "economic_intel.sector_trend": econ.get("trend"),
        "economic_intel.signals_count": len(econ.get("signals") or []),
        "economic_intel.signals": econ.get("signals") or [],
        "economic_intel.sources": econ.get("sources_available", []),
    }
    fields = {k: v for k, v in fields.items() if v not in (None, "", [], {})}
    return fields, {"source": "economic_intel", "found": True, "cnae": cnae}
