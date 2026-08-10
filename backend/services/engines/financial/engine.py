"""Financial Intelligence Engine — orchestrator.

Generates the full financial intelligence profile of a company FROM the Master Layer
(+ Normalized statements, internal). Valuation is one capability among KPIs, ratios,
evolution, quality and comparables. Rules-based, explainable, NO AI.
"""

from typing import Dict, List, Optional

from database import db
from models import now_iso
from services.engines.financial import metrics as M
from services.engines.financial import ratios_library as R
from services.engines.financial import market_multiples as MM

ENGINE_VERSION = "financial-intelligence-v1"

# EV/EBITDA reference multiples by CNAE section (INFERRED — not market-observed).
# Documented as low-confidence reference until real market/transaction multiples are connected.
_SECTION_EV_EBITDA = {
    "C": 7.5, "G": 6.0, "J": 9.5, "M": 8.0, "F": 5.5, "I": 6.5, "H": 6.0,
    "K": 9.0, "Q": 8.5, "A": 6.0, "L": 7.0,
}
_DEFAULT_EV_EBITDA = 6.5
_DEFAULT_EV_REVENUE = 0.9


def _pct_change(new, old):
    if new is None or old in (None, 0):
        return None
    return round((new - old) / abs(old), 4)


def _cagr(series_vals: List):
    vals = [v for v in series_vals if v not in (None, 0)]
    if len(vals) < 2:
        return None
    first, last = vals[-1], vals[0]   # series is newest-first
    n = len(vals) - 1
    if first <= 0 or last <= 0:
        return None
    return round((last / first) ** (1 / n) - 1, 4)


def _financial_narrative(quality: Dict, kpis: Dict, evolution: Dict,
                         strengths: list, weaknesses: list, risks: list) -> Dict:
    """Deterministic Corporate-Finance prose for the 'Lectura financiera de ARROBA'
    (`assessment`) and the 'Veredicto de ARROBA' (`verdict`). No AI. Real data only."""
    score = quality.get("score") or 0
    label = ("Sólida" if score >= 75 else "Aceptable" if score >= 55
             else "Frágil" if score >= 35 else "Débil")

    def pct(x):
        return f"{round(x * 100, 1)}%" if isinstance(x, (int, float)) else None

    parts = [f"Calidad financiera {label.lower()} ({score}/100)."]
    m = kpis.get("ebitda_margin")
    if m is not None:
        tone = "holgado" if m > 0.15 else "ajustado" if m < 0.05 else "moderado"
        parts.append(f"Margen EBITDA {tone} del {pct(m)}.")
    g = kpis.get("revenue_growth_yoy")
    if g is not None:
        parts.append(f"Ingresos {'al alza' if g >= 0 else 'a la baja'} ({pct(g)}) interanual.")
    s = kpis.get("solvency")
    if s is not None:
        parts.append(f"Autonomía financiera (PN/Activo) del {pct(s)}.")
    assessment = " ".join(parts)

    if score >= 75 and not risks:
        verdict = "Perfil financiero sólido y consistente; candidato atractivo para operaciones corporativas."
    elif score >= 55:
        head = strengths[0] if strengths else "fundamentales razonables"
        tail = f" Vigilar: {risks[0].lower()}." if risks else ""
        verdict = f"Perfil aceptable apoyado en {head.lower()}.{tail}"
    else:
        main = (risks or weaknesses or ["información financiera limitada"])[0]
        verdict = f"Perfil {label.lower()}: {main.lower()}. Requiere análisis y due diligence adicionales."

    return {"label": label, "assessment": assessment, "verdict": verdict,
            "strengths": strengths, "weaknesses": weaknesses, "risks": risks}


def compute_kpis(series: List[Dict], employees: Optional[int]) -> Dict:
    latest = series[0]
    prev = series[1] if len(series) > 1 else {}
    return {
        "revenue": latest.get("revenue"), "ebitda": latest.get("ebitda"),
        "ebit": latest.get("ebit"), "net_income": latest.get("net_income"),
        "revenue_growth_yoy": _pct_change(latest.get("revenue"), prev.get("revenue")),
        "ebitda_growth_yoy": _pct_change(latest.get("ebitda"), prev.get("ebitda")),
        "revenue_cagr": _cagr([s.get("revenue") for s in series]),
        "ebitda_margin": R._safe_div(latest.get("ebitda"), latest.get("revenue")),
        "net_margin": R._safe_div(latest.get("net_income"), latest.get("revenue")),
        "roe": R._safe_div(latest.get("net_income"), latest.get("equity")),
        "roa": R._safe_div(latest.get("net_income"), latest.get("total_assets")),
        "solvency": R._safe_div(latest.get("equity"), latest.get("total_assets")),
        "current_ratio": R._safe_div(latest.get("current_assets"), latest.get("current_liabilities")),
        "debt_to_equity": R._safe_div(latest.get("financial_debt"), latest.get("equity")),
        "revenue_per_employee": R._safe_div(latest.get("revenue"), employees),
        "capital_intensity": R._safe_div(latest.get("total_assets"), latest.get("revenue")),
    }


def compute_evolution(series: List[Dict]) -> Dict:
    if len(series) < 2:
        return {"trend": "insufficient_history", "years": len(series), "points": []}
    rev_growth = _pct_change(series[0].get("revenue"), series[1].get("revenue"))
    ebitda_growth = _pct_change(series[0].get("ebitda"), series[1].get("ebitda"))
    trend = "stable"
    if rev_growth is not None:
        if rev_growth > 0.1:
            trend = "growth"
        elif rev_growth < -0.1:
            trend = "deterioration"
    anomaly = bool(rev_growth is not None and abs(rev_growth) > 0.5)
    return {
        "trend": trend, "years": len(series), "anomaly": anomaly,
        "revenue_growth_yoy": rev_growth, "ebitda_growth_yoy": ebitda_growth,
        "points": [{"year": s.get("year"), "revenue": s.get("revenue"),
                    "ebitda": s.get("ebitda"), "net_income": s.get("net_income"),
                    "gross_margin": (R._safe_div((s.get("revenue") - s.get("supplies")), s.get("revenue"))
                                     if (s.get("revenue") is not None and s.get("supplies") is not None) else None),
                    "ebitda_margin": R._safe_div(s.get("ebitda"), s.get("revenue")),
                    "personnel_costs": s.get("personnel_costs"),
                    "personnel_pct": R._safe_div(s.get("personnel_costs"), s.get("revenue")),
                    # Fondo de maniobra = activo corriente − pasivo corriente.
                    "working_capital": (round(s["current_assets"] - s["current_liabilities"], 2)
                                        if (s.get("current_assets") is not None and s.get("current_liabilities") is not None) else None),
                    # Posición financiera neta = deuda financiera (c/p + l/p) − tesorería.
                    "net_financial_position": (round((s.get("financial_debt") or 0) - s["cash"], 2)
                                               if (s.get("cash") is not None and s.get("financial_debt") is not None) else None),
                    "employees": None} for s in series],
    }


def financial_quality(series: List[Dict], audited: Optional[str]) -> Dict:
    """Rules-based, fully explainable financial_quality_score (0-100). No AI."""
    latest = series[0]
    rules = []

    def add(cond, pts, reason):
        rules.append({"rule": reason, "points": pts if cond else 0, "max": pts, "passed": bool(cond)})

    add(latest.get("revenue") is not None, 20, "Estados financieros disponibles")
    add(len(series) >= 2, 15, "Histórico ≥ 2 ejercicios")
    add(bool(audited) and str(audited).upper() not in ("", "NO", "N"), 10, "Cuentas auditadas")
    add((latest.get("ebitda") or 0) > 0, 15, "EBITDA positivo")
    add((latest.get("net_income") or 0) > 0, 10, "Beneficio neto positivo")
    eq, ta = latest.get("equity"), latest.get("total_assets")
    add(eq is not None and ta not in (None, 0) and 0 < eq <= ta, 15, "Balance consistente (0<PN≤Activo)")
    add((latest.get("revenue") or 0) > 0, 5, "Ingresos positivos")
    stable = True
    if len(series) >= 2:
        g = _pct_change(series[0].get("revenue"), series[1].get("revenue"))
        stable = g is None or abs(g) <= 0.5
    add(stable, 10, "Sin saltos anómalos de ingresos (>50%)")

    score = sum(r["points"] for r in rules)
    return {"score": score, "max": 100, "rules": rules,
            "method": "rules_based", "ai_used": False}


async def financial_comparables(master: Dict, latest: Dict, limit: int = 8) -> Dict:
    """Peers by sector (CNAE section) + size band + geography. NO embeddings."""
    section = (master.get("classification") or {}).get("cnae_section")
    revenue = latest.get("revenue")
    province = (master.get("location") or {}).get("provincia")
    q: Dict = {"master_id": {"$ne": master["master_id"]},
               "classification.cnae_section": section,
               "financials.latest.revenue": {"$ne": None}}
    if revenue:
        q["financials.latest.revenue"] = {"$gte": revenue * 0.3, "$lte": revenue * 3.0}
    peers = []
    async for p in db.master_companies.find(q, {"_id": 0, "master_id": 1, "identity.legal_name": 1,
                                                "classification.cnae_code": 1, "location.provincia": 1,
                                                "financials.latest": 1}).limit(limit * 3):
        fl = (p.get("financials") or {}).get("latest") or {}
        peers.append({"master_id": p["master_id"],
                      "name": (p.get("identity") or {}).get("legal_name"),
                      "cnae_code": (p.get("classification") or {}).get("cnae_code"),
                      "provincia": (p.get("location") or {}).get("provincia"),
                      "revenue": fl.get("revenue"), "ebitda": fl.get("ebitda"),
                      "ebitda_margin": fl.get("ebitda_margin"),
                      "same_province": (p.get("location") or {}).get("provincia") == province})
    # prefer same province, then closeness in revenue
    peers.sort(key=lambda x: (not x["same_province"],
                              abs((x["revenue"] or 0) - (revenue or 0))))
    peers = peers[:limit]
    margins = sorted([p["ebitda_margin"] for p in peers if p["ebitda_margin"] is not None])
    subj_m = latest.get("ebitda") / latest.get("revenue") if (latest.get("ebitda") and latest.get("revenue")) else None
    pct = None
    if margins and subj_m is not None:
        below = sum(1 for x in margins if x <= subj_m)
        pct = round(below / len(margins), 2)
    return {"criteria": {"cnae_section": section, "size_band": "0.3x–3x revenue", "geography": province},
            "count": len(peers), "peers": peers, "subject_ebitda_margin_percentile": pct,
            "method": "structural (sector+size+geo)", "embeddings_used": False}


async def ranking(master: Dict, latest: Optional[Dict] = None) -> Dict:
    """Relative position of THIS company (arroba.v2, additive). Real-data-only:
      • sector_revenue_percentile ← % of same-CNAE-section companies below its revenue.
      • market_position {rank,total} ← ordinal by revenue within the Peer Universe
        (same CNAE section + size band 0.3x–3x revenue).
      • locality_position {rank,total,scope} ← ordinal by revenue within the same sector
        in its municipality (fallback: province).
    Every sub-block is OMITTED when it cannot be computed honestly (no revenue, or the
    universe is too small). Uses count_documents only (no in-memory scans)."""
    section = (master.get("classification") or {}).get("cnae_section")
    revenue = (latest or {}).get("revenue")
    if revenue is None:
        revenue = ((master.get("financials") or {}).get("latest") or {}).get("revenue")
    if revenue is None or not section:
        return {}

    loc = master.get("location") or {}
    provincia = loc.get("provincia")
    municipio = loc.get("municipio")
    out: Dict = {}

    # 1. Sector revenue percentile (whole CNAE section, national)
    sector_q = {"classification.cnae_section": section, "financials.latest.revenue": {"$ne": None}}
    sector_total = await db.master_companies.count_documents(sector_q)
    if sector_total >= 5:
        below = await db.master_companies.count_documents(
            {"classification.cnae_section": section, "financials.latest.revenue": {"$lt": revenue}})
        out["sector_revenue_percentile"] = round(below / sector_total * 100)

    # 2. Market position within the Peer Universe (sector + size band 0.3x–3x)
    lo, hi = revenue * 0.3, revenue * 3.0
    market_total = await db.master_companies.count_documents(
        {"classification.cnae_section": section, "financials.latest.revenue": {"$gte": lo, "$lte": hi}})
    if market_total >= 3:
        higher = await db.master_companies.count_documents(
            {"classification.cnae_section": section, "financials.latest.revenue": {"$gt": revenue, "$lte": hi}})
        out["market_position"] = {"rank": higher + 1, "total": market_total,
                                  "scope": "sector CNAE + banda de tamaño (0,3x–3x ingresos)"}

    # 3. Locality position (same sector, within municipality; fallback province)
    loc_filter, scope = None, None
    if municipio:
        loc_filter, scope = {"location.municipio": municipio}, "municipio"
    elif provincia:
        loc_filter, scope = {"location.provincia": provincia}, "provincia"
    if loc_filter:
        base = {**loc_filter, "classification.cnae_section": section,
                "financials.latest.revenue": {"$ne": None}}
        loc_total = await db.master_companies.count_documents(base)
        if loc_total >= 3:
            loc_higher = await db.master_companies.count_documents(
                {**loc_filter, "classification.cnae_section": section,
                 "financials.latest.revenue": {"$gt": revenue}})
            out["locality_position"] = {"rank": loc_higher + 1, "total": loc_total, "scope": scope}

    # Human-readable phrases (subject-less, ready for Beta's hero). Only for computed blocks.
    if out:
        place = (municipio or provincia or "").title() or None
        explain = []
        pct = out.get("sector_revenue_percentile")
        if pct is not None:
            explain.append(f"En el percentil {pct} por ingresos de su sector")
        mp = out.get("market_position")
        if mp:
            explain.append(f"{mp['rank']}ª de {mp['total']} en su universo de comparables (sector y tamaño)")
        lp = out.get("locality_position")
        if lp and place:
            explain.append(f"{lp['rank']}ª de {lp['total']} en {place} por ingresos de su sector")
        if explain:
            out["explain"] = explain

    return out


async def valuation(master: Dict, latest: Dict) -> Dict:
    """EV/EBITDA → EV/revenue → book value → insufficient_data. Consumes Master Layer.

    Q6: for companies in the marketing-agency CNAE set (Division 73), tries a REAL,
    market-observed multiple from the M&A Radar first (`market_multiples.py`). Every
    other sector — and marketing agencies when the M&A Radar sample is still too
    small — keeps the inferred CNAE-section reference exactly as before. Never
    silently claims real-market coverage it doesn't have.
    """
    section = (master.get("classification") or {}).get("cnae_section")
    cnae_code = (master.get("classification") or {}).get("cnae_code")
    revenue, ebitda = latest.get("revenue"), latest.get("ebitda")
    equity = latest.get("equity")
    net_debt = (latest.get("financial_debt") or 0) - (latest.get("cash") or 0)
    hypotheses, lineage = [], {"financials_source": "master_companies.financials.latest",
                               "basis": latest.get("basis"), "year": latest.get("year")}

    if ebitda and ebitda > 0:
        real = await MM.real_multiple_for_company(cnae_code)
        if real:
            mult = real["ev_ebitda_median"]
            ev = ebitda * mult
            equity_value = ev - net_debt
            hypotheses = [f"Múltiplo EV/EBITDA REAL del M&A Radar (agencias de publicidad, "
                          f"{real['sample_size']} transacciones) = {mult}x (mediana observada)",
                          f"Deuda neta = deuda financiera - caja = {round(net_debt,0)}"]
            return {"method": "ev_ebitda", "multiple": mult, "multiple_basis": "market_observed",
                    "enterprise_value": round(ev, 0), "equity_value": round(equity_value, 0),
                    "range": {"low": round(ebitda * real.get("ev_ebitda_p25", mult), 0),
                              "high": round(ebitda * real.get("ev_ebitda_p75", mult), 0)},
                    "confidence": 0.8, "hypotheses": hypotheses, "lineage": {**lineage, "source": real}}
        mult = _SECTION_EV_EBITDA.get(section, _DEFAULT_EV_EBITDA)
        ev = ebitda * mult
        equity_value = ev - net_debt
        hypotheses = [f"Múltiplo EV/EBITDA sectorial (sección {section}) = {mult}x (REFERENCIA inferida)",
                      f"Deuda neta = deuda financiera - caja = {round(net_debt,0)}"]
        return {"method": "ev_ebitda", "multiple": mult, "multiple_basis": "inferred_reference",
                "enterprise_value": round(ev, 0), "equity_value": round(equity_value, 0),
                "range": {"low": round(ev * 0.85, 0), "high": round(ev * 1.15, 0)},
                "confidence": 0.6, "hypotheses": hypotheses, "lineage": lineage}
    if revenue and revenue > 0:
        mult = _DEFAULT_EV_REVENUE
        ev = revenue * mult
        hypotheses = [f"Múltiplo EV/Ingresos = {mult}x (REFERENCIA inferida; EBITDA no disponible/≤0)"]
        return {"method": "ev_revenue", "multiple": mult, "multiple_basis": "inferred_reference",
                "enterprise_value": round(ev, 0), "equity_value": round(ev - net_debt, 0),
                "range": {"low": round(ev * 0.7, 0), "high": round(ev * 1.3, 0)},
                "confidence": 0.4, "hypotheses": hypotheses, "lineage": lineage}
    if equity and equity > 0:
        return {"method": "book_value", "equity_value": round(equity, 0),
                "confidence": 0.3, "hypotheses": ["Valor en libros (patrimonio neto)"],
                "lineage": lineage}
    return {"method": "insufficient_data", "confidence": 0.0,
            "hypotheses": ["Sin EBITDA, ingresos ni patrimonio utilizables"], "lineage": lineage}


def _identity_descriptors(master: Dict) -> Dict:
    """Real-data-only descriptors for the identity block (arroba.v2). Keys are OMITTED
    when there is no genuine value — never fabricated. Additive to the contract.
      • objeto_social  ← master_companies.objeto_social (raw registry text)
      • description     ← master_companies.web_description.description (web enrichment)
      • activity        ← normalized activity, only if present
    """
    out: Dict = {}
    obj = (master.get("objeto_social") or "").strip()
    if obj:
        out["objeto_social"] = obj
    wd = master.get("web_description")
    desc = ""
    if isinstance(wd, dict):
        desc = (wd.get("description") or "").strip()
    elif isinstance(wd, str):
        desc = wd.strip()
    if desc:
        out["description"] = desc
    act = master.get("activity") or master.get("activity_normalized")
    if isinstance(act, str) and act.strip():
        out["activity"] = act.strip()
    return out


def _ratios_with_trend(series: List[Dict], employees: Optional[int]) -> Dict[str, Dict]:
    """Ratios of the latest year + per-ratio trend (▲/▼/▬) vs the previous year (I-1 #3).
    Additive: adds `trend`, `prev_value`, `delta` only when a prior comparable exists."""
    ratios = R.compute_all(series[0], employees)
    if len(series) >= 2:
        prev = R.compute_all(series[1], employees)
        for key, r in ratios.items():
            v, pv = r.get("value"), (prev.get(key) or {}).get("value")
            if v is not None and pv is not None:
                diff = v - pv
                eps = abs(pv) * 0.01
                r["prev_value"] = pv
                r["delta"] = round(diff, 4)
                r["trend"] = "▲" if diff > eps else ("▼" if diff < -eps else "▬")
    return ratios


def _valuation_full(val: Dict, latest: Dict, comparables: Dict) -> Dict:
    """Additive valuation surface (arroba.v2): scenarios (conservador/base/optimista con
    label+multiple+EV+equity), benchmark (lista empresa vs mediana categoría) y methodology.
    Solo dato real."""
    import statistics
    out: Dict = {}
    method = val.get("method")
    ev = val.get("enterprise_value")
    mult = val.get("multiple")
    rng = val.get("range") or {}
    lo, hi = rng.get("low"), rng.get("high")
    net_debt = (latest.get("financial_debt") or 0) - (latest.get("cash") or 0)

    def _mult_for(x):
        return round(mult * x / ev, 2) if (mult and ev) else None

    if method in ("ev_ebitda", "ev_revenue") and None not in (ev, lo, hi):
        out["scenarios"] = [
            {"label": "conservador", "multiple": _mult_for(lo),
             "enterprise_value": lo, "equity_value": round(lo - net_debt, 0)},
            {"label": "base", "multiple": mult,
             "enterprise_value": ev, "equity_value": round(ev - net_debt, 0)},
            {"label": "optimista", "multiple": _mult_for(hi),
             "enterprise_value": hi, "equity_value": round(hi - net_debt, 0)},
        ]

    peers = (comparables or {}).get("peers") or []
    pmargins = sorted([p["ebitda_margin"] for p in peers if p.get("ebitda_margin") is not None])
    prevs = sorted([p["revenue"] for p in peers if p.get("revenue") is not None])
    subj_margin = R._safe_div(latest.get("ebitda"), latest.get("revenue"))
    benchmark = []
    if pmargins:
        benchmark.append({"metric": "Margen EBITDA", "company": round(subj_margin, 4) if subj_margin is not None else None,
                          "category": round(statistics.median(pmargins), 4), "format": "percent"})
    if prevs:
        benchmark.append({"metric": "Ingresos", "company": latest.get("revenue"),
                          "category": round(statistics.median(prevs), 0), "format": "currency"})
    if benchmark:
        out["benchmark"] = benchmark
        out["benchmark_scope"] = "sector CNAE + banda de tamaño"
        if (comparables or {}).get("subject_ebitda_margin_percentile") is not None:
            out["ebitda_margin_percentile"] = round(comparables["subject_ebitda_margin_percentile"] * 100)

    texts = {
        "ev_ebitda": "Valoración por múltiplo EV/EBITDA (referencia sectorial/mercado según calidad), "
                     "aplicado al EBITDA del último ejercicio; puente a equity restando la deuda financiera neta.",
        "ev_revenue": "Valoración por múltiplo EV/Ingresos de referencia sectorial, aplicado a los ingresos "
                      "del último ejercicio; puente a equity restando la deuda financiera neta.",
        "book_value": "Valoración por valor en libros (patrimonio neto), ante la ausencia de EBITDA o "
                      "ingresos utilizables para un enfoque por múltiplos.",
        "insufficient_data": "Datos insuficientes para una valoración por múltiplos sobre este perfil.",
    }
    if method in texts:
        out["methodology"] = texts[method]
    return out


# Ratios computable from the denormalized `financials.latest` (used for sector percentiles).
_PCT_RATIOS = {
    "ebitda_margin": lambda l: R._safe_div(l.get("ebitda"), l.get("revenue")),
    "ebit_margin": lambda l: R._safe_div(l.get("operating_income"), l.get("revenue")),
    "net_margin": lambda l: R._safe_div(l.get("net_income"), l.get("revenue")),
    "roa": lambda l: R._safe_div(l.get("net_income"), l.get("total_assets")),
    "roe": lambda l: R._safe_div(l.get("net_income"), l.get("equity")),
    "solvency": lambda l: R._safe_div(l.get("equity"), l.get("total_assets")),
    "capital_intensity": lambda l: R._safe_div(l.get("total_assets"), l.get("revenue")),
}


async def _ratio_sector_percentiles(section: Optional[str], ratios: Dict) -> None:
    """Add `percentile` (sector, national) to EVERY ratio for which the sector has a
    sufficient sample (arroba.v2 #3). Primary source: the denormalized
    `financials.latest.ratios` of sector peers (covers liquidity/working-capital once
    backfilled). Falls back to computing margins/returns from `financials.latest` line
    items for peers not yet backfilled. Real-data-only: percentile only when sample ≥20."""
    if not section:
        return
    peers = await db.master_companies.find(
        {"classification.cnae_section": section, "financials.latest.revenue": {"$ne": None}},
        {"_id": 0, "financials.latest": 1}).to_list(6000)
    dists: Dict[str, list] = {}
    for p in peers:
        lat = (p.get("financials") or {}).get("latest") or {}
        pr = lat.get("ratios")
        if isinstance(pr, dict) and pr:
            for k, v in pr.items():
                if v is not None:
                    dists.setdefault(k, []).append(v)
        else:  # fallback for docs not yet backfilled
            for k, fn in _PCT_RATIOS.items():
                v = fn(lat)
                if v is not None:
                    dists.setdefault(k, []).append(v)
    for k, r in ratios.items():
        subj = (r or {}).get("value")
        vals = dists.get(k) or []
        if subj is not None and len(vals) >= 20:
            below = sum(1 for x in vals if x < subj)
            r["percentile"] = round(below / len(vals) * 100)
            r["percentile_sample"] = len(vals)


async def analyze(identifier: str) -> Optional[Dict]:
    """Full financial intelligence profile. identifier = master_id or cif_normalized."""
    master = await db.master_companies.find_one(
        {"$or": [{"master_id": identifier}, {"cif_normalized": identifier}]}, {"_id": 0})
    if not master:
        return None
    cif = master["cif_normalized"]
    norm = await db.norm_financials.find({"cif_normalized": cif}, {"_id": 0}).to_list(50)
    nc = await db.norm_company.find_one({"cif_normalized": cif}, {"_id": 0, "audited": 1, "employees_total": 1})
    employees = (master.get("size") or {}).get("employees_total") or (nc or {}).get("employees_total")
    audited = (nc or {}).get("audited")

    series = M.build_series(norm)
    if not series:
        return {
            "master_id": master["master_id"], "cif_normalized": cif,
            "identity": {"name": (master.get("identity") or {}).get("legal_name"),
                         "cnae_code": (master.get("classification") or {}).get("cnae_code"),
                         "cnae_section": (master.get("classification") or {}).get("cnae_section"),
                         **_identity_descriptors(master)},
            "has_financials": False,
            "ranking": await ranking(master, {}),
            "valuation": {"method": "insufficient_data", "confidence": 0.0,
                          "hypotheses": ["Sin estados financieros normalizados"], "lineage": {}},
            "engine_version": ENGINE_VERSION, "generated_at": now_iso(), "confidence": 0.0,
        }

    latest = series[0]
    kpis = compute_kpis(series, employees)
    ratios = _ratios_with_trend(series, employees)
    await _ratio_sector_percentiles((master.get("classification") or {}).get("cnae_section"), ratios)
    evolution = compute_evolution(series)
    quality = financial_quality(series, audited)
    comparables = await financial_comparables(master, latest)
    val = await valuation(master, latest)
    val = {**val, **_valuation_full(val, latest, comparables)}

    statements = M.statements(latest, employees)
    _cf = M.cashflow_statement(series)
    if _cf:
        statements["cash_flow"] = _cf
    else:
        statements["cash_flow"] = None
        statements["cash_flow_note"] = ("No disponible: la empresa presenta cuentas abreviadas/PYME, "
                                        "que no incluyen Estado de Flujos de Efectivo (EFE).")

    # rules-based strengths / weaknesses / risks (explainable)
    strengths, weaknesses, risks = [], [], []
    if (kpis.get("ebitda_margin") or 0) > 0.15:
        strengths.append("Margen EBITDA sólido (>15%)")
    if (kpis.get("revenue_growth_yoy") or 0) > 0.1:
        strengths.append("Crecimiento de ingresos >10% interanual")
    if (kpis.get("solvency") or 1) < 0.2:
        weaknesses.append("Baja autonomía financiera (PN/Activo <20%)")
    if kpis.get("current_ratio") is not None and kpis["current_ratio"] < 1:
        risks.append("Liquidez ajustada (ratio corriente <1)")
    if (kpis.get("net_income") or 0) < 0:
        risks.append("Resultado neto negativo")
    if evolution.get("trend") == "deterioration":
        risks.append("Tendencia de ingresos a la baja")

    quality.update(_financial_narrative(quality, kpis, evolution, strengths, weaknesses, risks))

    overall_conf = round(min(1.0, 0.3 + 0.5 * (quality["score"] / 100) + (0.2 if len(series) >= 2 else 0)), 2)
    return {
        "master_id": master["master_id"], "cif_normalized": cif,
        "identity": {"name": (master.get("identity") or {}).get("legal_name"),
                     "cnae_code": (master.get("classification") or {}).get("cnae_code"),
                     "cnae_section": (master.get("classification") or {}).get("cnae_section"),
                     "provincia": (master.get("location") or {}).get("provincia"),
                     **_identity_descriptors(master)},
        "has_financials": True,
        "ranking": await ranking(master, latest),
        "statements": statements,
        "kpis": kpis,
        "ratios": ratios,
        "evolution": evolution,
        "financial_quality": quality,
        "comparables": comparables,
        "valuation": val,
        "assessment": {"strengths": strengths, "weaknesses": weaknesses, "risks": risks},
        "explainability": {
            "data_source": "master_companies + norm_financials (Iberinform)",
            "source_version": master.get("sources", [{}])[-1].get("source_version"),
            "basis": latest.get("basis"), "year": latest.get("year"),
            "rules_applied": "KPIs/ratios/quality deterministas; valoración por múltiplos inferidos",
            "ai_used": False,
        },
        "engine_version": ENGINE_VERSION, "generated_at": now_iso(), "confidence": overall_conf,
    }
