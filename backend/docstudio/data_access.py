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


async def scoped_opportunities(cnae_section: Optional[str] = None,
                               provincia: Optional[str] = None,
                               signal_types: Optional[List[str]] = None,
                               sort_by: str = "impact", limit: int = 50) -> List[Dict]:
    """Active M&A opportunities (severity=='opportunity') SCOPED by filters — never a
    dump of the whole universe (decisión 6 del plan). Same taxonomy rule as the
    Signal Engine's /opportunities. Joins to master for name/section/provincia.
    """
    q = {"severity": "opportunity", "status": "active"}
    if signal_types:
        q["signal_type"] = {"$in": signal_types}
    dim = sort_by if sort_by in ("impact", "confidence", "urgency", "persistence") else "impact"
    rows: List[Dict] = []
    async for s in db.signals.find(q, {"_id": 0}).sort(f"dimensions.{dim}", -1).limit(limit * 4):
        m = await db.master_companies.find_one(
            {"master_id": s["master_id"]},
            {"_id": 0, "identity.legal_name": 1, "classification.cnae_section": 1, "location.provincia": 1})
        if not m:
            continue
        sec = (m.get("classification") or {}).get("cnae_section")
        prov = (m.get("location") or {}).get("provincia")
        if cnae_section and sec != cnae_section:
            continue
        if provincia and prov != provincia:
            continue
        rows.append({
            "signal_id": s.get("signal_id"), "master_id": s["master_id"],
            "name": (m.get("identity") or {}).get("legal_name"),
            "provincia": prov, "cnae_section": sec,
            "signal_type": s.get("signal_type"), "dimensions": s.get("dimensions", {}),
            "explanation": s.get("explanation"), "trend": s.get("trend"),
            "recommended_actions": s.get("recommended_actions"),
        })
        if len(rows) >= limit:
            break
    return rows


async def rank_companies(cnae_section: Optional[str] = None, cnae_code: Optional[str] = None,
                         provincia: Optional[str] = None, sort_by: str = "revenue",
                         limit: int = 25) -> List[Dict]:
    """Rank real companies in a sector/territory by a real metric (revenue). Reads
    `master_companies` (financials.latest), enriches with active-signal count. For the
    Ranking document (B4). Never estimated — companies without the metric are dropped."""
    q: Dict = {"status": "active"}
    if cnae_code:
        q["classification.cnae_code"] = cnae_code
    elif cnae_section:
        q["classification.cnae_section"] = cnae_section
    if provincia:
        q["location.provincia"] = provincia
    rows: List[Dict] = []
    async for m in db.master_companies.find(
        q, {"_id": 0, "master_id": 1, "identity.legal_name": 1, "location.provincia": 1,
            "classification.cnae_code": 1, "financials.latest": 1}).limit(limit * 6):
        fl = (m.get("financials") or {}).get("latest") or {}
        rev = fl.get("revenue")
        if rev is None:
            continue
        n_sig = await db.signals.count_documents({"master_id": m["master_id"], "status": "active"})
        rows.append({
            "master_id": m["master_id"],
            "name": (m.get("identity") or {}).get("legal_name"),
            "provincia": (m.get("location") or {}).get("provincia"),
            "cnae_code": (m.get("classification") or {}).get("cnae_code"),
            "revenue": rev, "ebitda": fl.get("ebitda"),
            "ebitda_margin": fl.get("ebitda_margin"), "active_signals": n_sig,
        })
    key = "active_signals" if sort_by == "signals" else "revenue"
    rows.sort(key=lambda r: (r.get(key) or 0), reverse=True)
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
