"""Source: iberinform — financial data (revenue, employees, CNAE)."""

from typing import Dict, Tuple
from database import db


def _normalize_cif(cif: str) -> str:
    return (cif or "").upper().replace("-", "").replace(" ", "").strip()


META = {
    "display_name": "Iberinform",
    "collection": "iberinform_companies",
    "frequency": "Bajo demanda (al subir fichero)",
    "signal_source": "iberinform",
    "audit_action": None,
    "phase": "active",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "sidebar_dot": "bg-amber-500",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cif = master.get("cif", "")
    if not cif:
        return {}, {"source": "iberinform", "found": False, "reason": "no_cif"}

    cif_norm = _normalize_cif(cif)
    ib = await db.iberinform_companies.find_one(
        {"cif_normalized": cif_norm},
        {"_id": 0, "revenue_latest": 1, "employees_latest": 1, "ebitda_latest": 1,
         "cnae_code": 1, "legal_name": 1, "year_latest": 1, "revenue_history": 1,
         "employees_history": 1}
    )

    if not ib:
        return {}, {"source": "iberinform", "found": False, "reason": "no_match", "cif_normalized": cif_norm}

    fields = {}
    if ib.get("revenue_latest"):
        fields["iberinform.revenue_latest"] = ib["revenue_latest"]
    if ib.get("employees_latest"):
        fields["iberinform.employees_latest"] = ib["employees_latest"]
    if ib.get("ebitda_latest"):
        fields["iberinform.ebitda_latest"] = ib["ebitda_latest"]
    if ib.get("year_latest"):
        fields["iberinform.year_latest"] = ib["year_latest"]
    if ib.get("cnae_code"):
        fields["iberinform.cnae_code"] = ib["cnae_code"]
    if ib.get("revenue_history"):
        fields["iberinform.revenue_history"] = ib["revenue_history"]
    if ib.get("employees_history"):
        fields["iberinform.employees_history"] = ib["employees_history"]

    return fields, {"source": "iberinform", "found": True, "cif_normalized": cif_norm}
