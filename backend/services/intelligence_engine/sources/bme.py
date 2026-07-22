"""Source: BME — market listing, ISIN, market cap."""

import re
from typing import Dict, Tuple
from database import db


def _norm(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[,\.]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


META = {
    "display_name": "BME (Bolsas y Mercados)",
    "collection": "bme_companies",
    "frequency": "Bajo demanda",
    "signal_source": "bme",
    "audit_action": None,
    "phase": "active",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": True,
    "sidebar_group": "data",
    "supports_sample": True,
    "queryable": True,
    "sync_log": {"collection": "bme_sync_logs", "time_field": "synced_at"},
    "display_fields": ["company_name", "ticker", "market", "sector", "share_price", "market_cap", "annual_performance"],
    "field_labels": {"company_name": "Empresa", "ticker": "Ticker", "market": "Mercado", "sector": "Sector", "share_price": "Cotización", "market_cap": "Capitalización", "annual_performance": "Rentabilidad anual"},
    "actions": [
        {"id": "sync", "label": "Sincronizar BME", "endpoint": "/bme-markets/sync", "params": {"markets": "growth,scaleup"}, "kind": "button"},
        {"id": "enrich", "label": "Enriquecer detalles", "endpoint": "/bme-markets/enrich-details", "kind": "button"},
    ],
    "sidebar_dot": "bg-indigo-400",
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    name = master.get("legal_name", "")
    if not name or name.lower() == "unknown":
        return {}, {"source": "bme", "found": False, "reason": "no_name"}

    name_norm = _norm(name)
    # Match on first significant word(s) — drop legal suffix
    base = re.sub(r"\b(S\s*A|S\s*L|SA|SL|SAU|SLU)\b\s*$", "", name_norm).strip()
    if len(base) < 3:
        return {}, {"source": "bme", "found": False, "reason": "name_too_short"}

    pattern = f"^{re.escape(base[:12])}"
    bme = await db.bme_companies.find_one(
        {"company_name": {"$regex": pattern, "$options": "i"}},
        {"_id": 0, "company_name": 1, "isin": 1, "ticker": 1,
         "market_segment": 1, "market_cap": 1, "sector": 1, "cnae_code": 1}
    )

    if not bme:
        return {}, {"source": "bme", "found": False, "reason": "no_match", "pattern": pattern}

    fields = {
        "bme.company_name": bme.get("company_name"),
        "bme.isin": bme.get("isin"),
        "bme.ticker": bme.get("ticker"),
        "bme.market_segment": bme.get("market_segment"),
        "bme.market_cap": bme.get("market_cap"),
        "bme.sector": bme.get("sector"),
        "bme.cnae_code": bme.get("cnae_code"),
        "is_public_company": True,
    }
    fields = {k: v for k, v in fields.items() if v not in (None, "", [], {})}
    return fields, {"source": "bme", "found": True, "isin": bme.get("isin")}
