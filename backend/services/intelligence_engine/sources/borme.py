"""Source: BORME — corporate events count + last events sample."""

import re
from typing import Dict, Tuple
from database import db


def _normalize_name(name: str) -> str:
    """Strip suffixes and punctuation for fuzzy matching."""
    s = (name or "").upper()
    s = re.sub(r"[,\.]", " ", s)
    s = re.sub(r"\b(S\s*A|S\s*L|SA|SL|SAU|SLU|SRL|SCA|SLR|LTD|LIMITED|INC|CORP|GMBH)\b\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


META = {
    "display_name": "BORME",
    "collection": "borme_events",
    "frequency": "Diario (L-V)",
    "signal_source": "borme",
    "audit_action": None,
    "phase": "active",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "sync_log": {"collection": "borme_scheduler_logs", "time_field": "attempt_time"},
    "display_fields": ["company_name_normalized", "publication_date", "event_title", "section_name", "registry_province", "cnae_title"],
    "field_labels": {"company_name_normalized": "Empresa", "publication_date": "Fecha de publicación", "event_title": "Acto", "section_name": "Sección", "registry_province": "Provincia", "cnae_title": "Sector (CNAE)"},
    "actions": [
        {"id": "reprocess", "label": "Reprocesar fallos", "endpoint": "/borme/reprocess-failures", "kind": "button"},
    ],
    "sidebar_dot": "bg-blue-500",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    name = master.get("legal_name", "")
    if not name or name.lower() == "unknown":
        return {}, {"source": "borme", "found": False, "reason": "no_name"}

    name_norm = _normalize_name(name)
    if len(name_norm) < 4:
        return {}, {"source": "borme", "found": False, "reason": "name_too_short"}

    # Build a tolerant regex — first 20 chars of normalized name, ignoring punctuation
    pattern = re.escape(name_norm[:20])
    count = await db.borme_events.count_documents({
        "company_name_raw": {"$regex": pattern, "$options": "i"}
    })

    if count == 0:
        return {}, {"source": "borme", "found": False, "reason": "no_match"}

    # Get latest 5 events for context
    recent = await db.borme_events.find(
        {"company_name_raw": {"$regex": pattern, "$options": "i"}},
        {"_id": 0, "event_date": 1, "event_type": 1, "company_name_raw": 1}
    ).sort("event_date", -1).limit(5).to_list(5)

    fields = {
        "borme.events_count": count,
        "borme.recent_events": recent,
    }
    return fields, {"source": "borme", "found": True, "match_pattern": pattern}
