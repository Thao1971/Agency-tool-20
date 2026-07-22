"""Source: procurement — PLACSP public contracts."""

from typing import Dict, Tuple
from database import db


META = {
    "display_name": "Contratación Pública (PLACSP)",
    "collection": "public_procurement_contracts",
    "frequency": "Bajo demanda (sync-placsp)",
    "signal_source": "procurement",
    "audit_action": None,
    "phase": "active",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "sync_log": {"collection": "procurement_sync_logs", "time_field": "synced_at"},
    "display_fields": ["title", "awardee_name", "contracting_authority", "amount", "cpv_label", "status", "award_date"],
    "field_labels": {"title": "Objeto", "awardee_name": "Adjudicatario", "contracting_authority": "Órgano de contratación", "amount": "Importe", "cpv_label": "Categoría (CPV)", "status": "Estado", "award_date": "Fecha de adjudicación"},
    "actions": [
        {"id": "sync_placsp", "label": "Sincronizar PLACSP", "endpoint": "/public-procurement/sync-placsp", "params": {"dataset": "menores"}, "kind": "button"},
    ],
    "sidebar_dot": "bg-violet-500",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    cif = master.get("cif", "")
    if not cif:
        return {}, {"source": "procurement", "found": False, "reason": "no_cif"}

    # Try multiple CIF formats (with/without dashes/spaces)
    candidates = {cif, cif.upper(), cif.upper().replace("-", "").replace(" ", "")}
    count = 0
    matched_format = None
    for c in candidates:
        n = await db.public_procurement_contracts.count_documents({"awardee_tax_id": c})
        if n > 0:
            count = n
            matched_format = c
            break

    if count == 0:
        return {}, {"source": "procurement", "found": False, "reason": "no_match"}

    # Recent contracts
    recent = await db.public_procurement_contracts.find(
        {"awardee_tax_id": matched_format},
        {"_id": 0, "contract_id": 1, "title": 1, "amount_eur": 1, "awarded_date": 1, "buyer_name": 1}
    ).sort("awarded_date", -1).limit(5).to_list(5)

    total_amount = sum(r.get("amount_eur", 0) or 0 for r in await db.public_procurement_contracts.find(
        {"awardee_tax_id": matched_format}, {"_id": 0, "amount_eur": 1}
    ).to_list(1000))

    fields = {
        "procurement.contracts_count": count,
        "procurement.total_amount_eur": total_amount,
        "procurement.recent_contracts": recent,
    }
    return fields, {"source": "procurement", "found": True, "matched_format": matched_format}
