"""Company data adapter — the single door between the document composer and the
MODERN intelligence layer.

Fase 2 (DOCUMENT_STUDIO_UNIFICATION_PLAN): the composers must stop reading the LEGACY
schema (`companies_master` / `iberinform_financials`) and their own duplicated
`docstudio/financial_engine.py`, and instead read `master_companies` / `master_id`
and call the REAL canonical engines in-process:

  - Financial Intelligence Engine  (services/engines/financial/engine.analyze)
      -> KPIs, ratios, evolution, comparables REALES, valoración HONESTA
         (market_observed vs inferred_reference), assessment (fortalezas/riesgos).
  - Signal Intelligence Engine     (services/engines/signal/engine.analyze)
      -> señales/oportunidades activas de la empresa (severity/category reales).

This adapter returns a normalized dict the composers can turn into blocks. It never
invents data: missing pieces come back as None / empty, honestly.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from database import db


async def resolve_company(identifier: Optional[str] = None,
                          cif: Optional[str] = None) -> Optional[Dict]:
    """Resolve a company from the MODERN master (`master_companies`).

    `identifier` may be a master_id or a cif_normalized; `cif` is an alias.
    Returns the master doc (or None). Never touches the legacy `companies_master`.
    """
    ident = identifier or cif
    if not ident:
        return None
    return await db.master_companies.find_one(
        {"$or": [{"master_id": ident}, {"cif_normalized": ident}]}, {"_id": 0})


async def financial_profile(identifier: str) -> Dict:
    """Real Financial Intelligence Engine profile (in-process, no HTTP)."""
    from services.engines.financial import engine as fin_engine
    prof = await fin_engine.analyze(identifier)
    return prof or {}


async def active_signals(identifier: str, limit: int = 12) -> List[Dict]:
    """Active signals/opportunities for the company from the Signal Engine.

    Returns the real persisted signals (severity/category/dimensions/explanation),
    most impactful first. Empty list if none — never fabricated.
    """
    company = await resolve_company(identifier)
    if not company:
        return []
    master_id = company.get("master_id")
    rows = await db.signals.find(
        {"master_id": master_id, "status": "active"}, {"_id": 0}
    ).to_list(200)
    rows.sort(key=lambda s: (s.get("dimensions", {}) or {}).get("impact", 0), reverse=True)
    return rows[:limit]


def _identity(profile: Dict, company: Optional[Dict]) -> Dict:
    ident = profile.get("identity") or {}
    if not ident and company:
        ident = {
            "name": (company.get("identity") or {}).get("legal_name"),
            "cnae_code": (company.get("classification") or {}).get("cnae_code"),
            "cnae_section": (company.get("classification") or {}).get("cnae_section"),
            "provincia": (company.get("location") or {}).get("provincia"),
        }
    return ident


async def company_intelligence(identifier: str = None, cif: str = None,
                               include_signals: bool = True) -> Dict:
    """One-call bundle for the composer: identity + real financials + active signals.

    Shape (all fields honest; missing -> None/empty, never invented):
        {
          "found": bool,
          "master_id": str, "cif_normalized": str,
          "identity": {name, cnae_code, cnae_section, provincia},
          "has_financials": bool,
          "kpis": {...}, "valuation": {...}, "evolution": {...},
          "comparables": {...}, "assessment": {strengths, weaknesses, risks},
          "statements": {...},
          "signals": [ {signal_type, category, severity, dimensions, explanation}, ... ],
          "engine_versions": {financial, signal},
        }
    """
    ident_value = identifier or cif
    company = await resolve_company(ident_value)
    if not company:
        return {"found": False, "identity": {}, "signals": [], "has_financials": False}

    master_id = company.get("master_id")
    profile = await financial_profile(master_id)
    signals = await active_signals(master_id) if include_signals else []

    return {
        "found": True,
        "master_id": master_id,
        "cif_normalized": company.get("cif_normalized"),
        "identity": _identity(profile, company),
        "has_financials": profile.get("has_financials", False),
        "kpis": profile.get("kpis", {}),
        "valuation": profile.get("valuation", {}),
        "evolution": profile.get("evolution", {}),
        "comparables": profile.get("comparables", {}),
        "assessment": profile.get("assessment", {}),
        "statements": profile.get("statements", {}),
        "financial_quality": profile.get("financial_quality", {}),
        "signals": signals,
        "engine_versions": {
            "financial": profile.get("engine_version"),
            "signal": "signal-intelligence-v1",
        },
    }
