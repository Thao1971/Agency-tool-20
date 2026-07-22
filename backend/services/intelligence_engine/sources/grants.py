"""Source: government_grants — public subsidies received by a company.

Origin: datos.gob.es (Base Nacional de Subvenciones, ENISA, CDTI, Fondos europeos).
Match: by CIF or by normalized legal_name.
Ingestion: poblado vía scripts batch contra los datasets abiertos (pendiente).
"""

from typing import Dict, Tuple
from database import db


def _norm_cif(cif: str) -> str:
    return (cif or "").upper().replace("-", "").replace(" ", "").strip()


META = {
    "display_name": "Ayudas y Subvenciones (BDNS)",
    "collection": "ayudas_subvenciones_publicas",
    "frequency": "Diario — 04:30 Madrid",
    "signal_source": "ayudas_subvenciones_publicas",
    "audit_action": "public_source_ingest_ayudas_subvenciones_publicas",
    "phase": "active",
    "supports_manual_ingestion": True,
    "ingest_runner": "ingest_ayudas_subvenciones",
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "display_fields": ["beneficiary_name", "amount_eur", "program", "organism", "admin_region", "granted_date"],
    "field_labels": {"beneficiary_name": "Beneficiario", "amount_eur": "Importe (€)", "program": "Convocatoria", "organism": "Organismo", "admin_region": "Ámbito", "granted_date": "Fecha de concesión"},
    "sidebar_dot": "bg-emerald-400",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cif = master.get("cif", "")
    name = master.get("legal_name", "")
    if not cif and not name:
        return {}, {"source": "grants", "found": False, "reason": "no_cif_no_name"}

    query = {"$or": []}
    if cif:
        query["$or"].append({"cif_normalized": _norm_cif(cif)})
    if name:
        query["$or"].append({"company_name_normalized": name.upper().strip()})

    grants = await db.ayudas_subvenciones_publicas.find(query, {"_id": 0}).to_list(200)
    if not grants:
        return {}, {"source": "grants", "found": False, "reason": "no_match"}

    total_amount = sum((g.get("amount_eur") or 0) for g in grants)
    largest = max(grants, key=lambda g: g.get("amount_eur") or 0)
    programs = sorted({g.get("program") for g in grants if g.get("program")})
    last_date = max((g.get("granted_date") for g in grants if g.get("granted_date")), default=None)

    fields = {
        "grants.grants_count": len(grants),
        "grants.grants_total_amount": total_amount,
        "grants.largest_grant_amount": largest.get("amount_eur"),
        "grants.largest_grant_program": largest.get("program"),
        "grants.last_grant_date": last_date,
        "grants.grant_programs": programs,
    }
    return fields, {"source": "grants", "found": True, "count": len(grants)}
