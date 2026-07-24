"""Document Composer — Assembles documents from the MODERN intelligence layer + AI.

Fase 2 (DOCUMENT_STUDIO_UNIFICATION_PLAN): company documents are composed from
`docstudio/data_access.py` (real Financial + Signal engines over `master_companies`),
NOT the legacy `companies_master`/`iberinform_financials`. Sector context still comes
from Economic/Sector Intelligence. Narrative = Claude. Valuation = the real engine's
honest `valuation()` (market_observed vs inferred_reference), never a heuristic.
"""

import logging
from typing import Dict
from database import db
from models import now_iso
from docstudio import (
    new_document, new_section, cover_block, text_block, kpi_block,
    table_block, chart_block, insight_block, divider_block,
)
from docstudio.model_provider import generate_summary
from docstudio import data_access as DA

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════
# BLOCK HELPERS from the modern intelligence bundle (Fase 2)
# Build blocks from data_access.company_intelligence() — real Financial + Signal
# engines over master_companies. No legacy companies_master / financial_engine.py.
# ══════════════════════════════════════════

_FIN = "financial-intelligence-v1"


def _company_kpi_blocks(bundle: Dict) -> list:
    """KPI blocks from the real Financial Engine bundle (kpis are ratios 0-1)."""
    kpis = bundle.get("kpis", {}) or {}
    out = []
    rev = kpis.get("revenue")
    if rev:
        b = kpi_block("Facturación", f"{rev:,.0f}", "EUR")
        b["data_lineage"] = {"source": _FIN, "calculation": "revenue", "date": now_iso()}
        out.append(b)
    m = kpis.get("ebitda_margin")
    if m is not None:
        b = kpi_block("Margen EBITDA", f"{m*100:.1f}%", "")
        b["data_lineage"] = {"source": _FIN, "calculation": "ebitda_margin", "date": now_iso()}
        out.append(b)
    emp = (bundle.get("statements") or {}).get("employees")
    if emp:
        out.append(kpi_block("Plantilla", str(emp), "empleados"))
    g = kpis.get("revenue_growth_yoy")
    if g is not None:
        b = kpi_block("Crecimiento YoY", f"{g*100:+.1f}%", "")
        b["data_lineage"] = {"source": _FIN, "calculation": "revenue_growth_yoy", "date": now_iso()}
        out.append(b)
    cagr = kpis.get("revenue_cagr")
    if cagr is not None:
        b = kpi_block("CAGR ingresos", f"{cagr*100:+.1f}%", "")
        b["data_lineage"] = {"source": _FIN, "calculation": "revenue_cagr", "date": now_iso()}
        out.append(b)
    rpe = kpis.get("revenue_per_employee")
    if rpe:
        b = kpi_block("Ingresos/empleado", f"{rpe:,.0f}", "EUR")
        b["data_lineage"] = {"source": _FIN, "calculation": "revenue_per_employee", "date": now_iso()}
        out.append(b)
    return out


def _signal_insight_blocks(bundle: Dict, limit: int = 6) -> list:
    """Insight blocks from the company's real active signals (Signal Engine)."""
    out = []
    for sig in (bundle.get("signals") or [])[:limit]:
        sev = sig.get("severity", "")
        importance = "high" if sev in ("opportunity", "risk") else "medium"
        b = insight_block(
            title=sig.get("signal_type", ""),
            summary=sig.get("explanation", ""),
            importance=importance,
        )
        b["data_lineage"] = {"source": "signal-intelligence-v1",
                             "signal_id": sig.get("signal_id"), "date": now_iso()}
        out.append(b)
    return out


def _valuation_block(bundle: Dict):
    """A KPI block with the REAL, honest valuation (market_observed vs inferred_reference).
    Returns None when the engine reports insufficient data — never fabricates a number."""
    val = bundle.get("valuation", {}) or {}
    method = val.get("method")
    if not method or method == "insufficient_data":
        return None
    ev = val.get("enterprise_value") or val.get("equity_value") or val.get("ev")
    if not ev:
        return None
    basis = val.get("multiple_basis", "")
    basis_label = "múltiplo de mercado real" if basis == "market_observed" else "múltiplo de referencia inferido"
    b = kpi_block("Valoración orientativa (EV)", f"{ev:,.0f}", "EUR",
                  commentary=f"Método: {method} · {basis_label}")
    b["data_lineage"] = {"source": _FIN, "calculation": "valuation",
                         "multiple_basis": basis, "confidence": val.get("confidence"), "date": now_iso()}
    return b


async def compose_sector_report(cnae_code: str, brand_id: str = "brand_bud",
                                user: str = None) -> Dict:
    """Compose a full sector report from platform data."""
    from services.cnae_catalog import CNAE_DIVISIONS, get_section_for_division

    cnae_label = CNAE_DIVISIONS.get(cnae_code, {}).get("label", cnae_code)
    section_code = get_section_for_division(cnae_code)

    # Gather data from all sources
    econ = await _get_economic_profile(cnae_code)
    await _get_sector_intelligence(cnae_code)  # warm cache
    brand = await _get_brand(brand_id)

    doc = new_document(
        title=f"Informe Sectorial — CNAE {cnae_code}: {cnae_label}",
        template_id="tpl_sector_report",
        brand_id=brand_id,
        created_by=user,
        description=f"Informe de inteligencia sectorial para CNAE {cnae_code}",
    )

    # Section 1: Cover
    s1 = new_section("Portada", 1, [
        cover_block(
            title=cnae_label,
            subtitle=f"Informe Sectorial CNAE {cnae_code} — Seccion {section_code}",
            logo=brand.get("logo"),
        ),
    ])

    # Section 2: KPIs
    kpis = []
    if econ.get("revenue"):
        kpis.append(kpi_block("Revenue medio", f"{econ['revenue']['value']:,.0f}", "EUR",
                              variation=f"{econ.get('revenue_growth',{}).get('yoy_pct','')}% YoY" if econ.get('revenue_growth') else None))
    if econ.get("employment"):
        kpis.append(kpi_block("Empleados medio", f"{econ['employment']['value']:.0f}", "personas"))
    if econ.get("active_companies_national"):
        kpis.append(kpi_block("Empresas activas", f"{econ['active_companies_national']['value']:,.0f}", "empresas"))
    if econ.get("exports_eur"):
        kpis.append(kpi_block("Exportaciones", f"{econ['exports_eur']['value']:,.0f}", "EUR"))
    if econ.get("borme_events"):
        kpis.append(kpi_block("Eventos BORME", f"{econ['borme_events']['value']}", "actos mercantiles"))
    if econ.get("procurement_contracts"):
        kpis.append(kpi_block("Contratos publicos", f"{econ['procurement_contracts']['value']}", "contratos"))

    s3 = new_section("KPIs del Sector", 3, kpis)

    # Section 3: Trade
    trade_kpis = []
    if econ.get("exports_eur"):
        trade_kpis.append(kpi_block("Exportaciones", f"{econ['exports_eur']['value']:,.0f}", "EUR"))
    if econ.get("imports_eur"):
        trade_kpis.append(kpi_block("Importaciones", f"{econ['imports_eur']['value']:,.0f}", "EUR"))
    if econ.get("trade_balance_eur"):
        val = econ['trade_balance_eur']['value']
        trade_kpis.append(kpi_block("Saldo comercial", f"{val:,.0f}", "EUR",
                                    commentary="Superavit" if val > 0 else "Deficit"))
    s6 = new_section("Comercio Exterior", 6, trade_kpis) if trade_kpis else None

    # Section 4: Procurement
    proc_blocks = []
    if econ.get("procurement_contracts"):
        proc_blocks.append(kpi_block("Contratos adjudicados", f"{econ['procurement_contracts']['value']}", "contratos"))
    if econ.get("procurement_amount_eur"):
        proc_blocks.append(kpi_block("Importe adjudicado", f"{econ['procurement_amount_eur']['value']:,.0f}", "EUR"))
    s7 = new_section("Contratacion Publica", 7, proc_blocks) if proc_blocks else None

    # Section 5: Signals
    signal_blocks = []
    for sig in econ.get("signals", []):
        signal_blocks.append(insight_block(
            title=sig.get("signal_type", ""),
            summary=sig.get("description", ""),
            importance="high" if sig.get("confidence", 0) > 0.85 else "medium",
            source_ref=", ".join(sig.get("sources_used", [])),
        ))
    s8 = new_section("Tendencias y Senales", 8, signal_blocks) if signal_blocks else None

    # Section 6: AI-generated Executive Summary + Conclusions
    ai_context = {
        "cnae_code": cnae_code, "cnae_label": cnae_label,
        "revenue": econ.get("revenue"), "employment": econ.get("employment"),
        "exports": econ.get("exports_eur"), "imports": econ.get("imports_eur"),
        "active_companies": econ.get("active_companies_national"),
        "trend": econ.get("trend"), "signals": [s.get("signal_type") for s in econ.get("signals", [])],
    }

    ai_result = await generate_summary(ai_context, doc_type="sector_report", document_id=doc["document_id"])

    exec_summary = ai_result.get("executive_summary", "")
    key_findings = ai_result.get("key_findings", [])
    conclusion = ai_result.get("conclusion", "")

    s2_blocks = []
    if exec_summary:
        s2_blocks.append(text_block(exec_summary, style="executive_summary"))
        s2_blocks[-1]["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "executive_summary", "date": now_iso()}
    for finding in key_findings:
        s2_blocks.append(insight_block("Hallazgo clave", finding, importance="high"))
        s2_blocks[-1]["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "key_findings", "date": now_iso()}
    s2 = new_section("Resumen Ejecutivo", 2, s2_blocks)

    s9_blocks = []
    if conclusion:
        s9_blocks.append(text_block(conclusion, style="conclusion"))
        s9_blocks[-1]["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "conclusion", "date": now_iso()}
    for rec in ai_result.get("recommendations", []):
        s9_blocks.append(insight_block("Recomendacion", rec, importance="medium"))
    s9 = new_section("Conclusiones", 9, s9_blocks)

    # Assemble
    doc["sections"] = [s for s in [s1, s2, s3, s6, s7, s8, s9] if s]
    doc["metadata"] = {
        "cnae_code": cnae_code, "cnae_label": cnae_label, "section": section_code,
        "sources_used": econ.get("sources_available", []),
        "ai_models_used": ["gpt-5.2"],
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()

    # Persist
    await db.docstudio_documents.insert_one(doc)

    return doc


async def compose_company_profile(company_id: str = None, cif: str = None,
                                  brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Compose a full company profile document. Fase 2: modern schema + real engines."""
    from services.cnae_catalog import CNAE_DIVISIONS

    bundle = await DA.company_intelligence(company_id or cif)
    if not bundle.get("found"):
        return {"error": "Company not found"}

    ident = bundle["identity"]
    name = ident.get("name", "Empresa")
    cnae = ident.get("cnae_code", "")
    cif_norm = bundle.get("cif_normalized", "—")

    # Sector economic context (already modern via economic_intelligence)
    econ = await _get_economic_profile(cnae) if cnae else {}

    doc = new_document(
        title=f"Ficha de Compañía — {name}",
        template_id="tpl_company_profile",
        brand_id=brand_id,
        created_by=user,
        description=f"Perfil de {name}",
    )

    # Cover
    s1 = new_section("Portada", 1, [
        cover_block(title=name, subtitle=f"CIF: {cif_norm} — CNAE {cnae}"),
    ])

    # Company KPIs from the real Financial Engine
    company_kpis = _company_kpi_blocks(bundle)
    if cnae:
        company_kpis.append(kpi_block("Sector", CNAE_DIVISIONS.get(cnae, {}).get("label", cnae), f"CNAE {cnae}"))
    if ident.get("provincia"):
        company_kpis.append(kpi_block("Provincia", ident["provincia"], ""))
    s3 = new_section("Datos Generales", 3, company_kpis)

    # General info table
    info_rows = [["CIF", cif_norm], ["Razón social", name]]
    if cnae:
        info_rows.append(["Sector CNAE", f"{cnae} — {CNAE_DIVISIONS.get(cnae, {}).get('label', '')}"])
    if ident.get("provincia"):
        info_rows.append(["Provincia", ident["provincia"]])
    s3["blocks"].append(table_block("Información general", ["Campo", "Valor"], info_rows))

    # Active signals (Signal Engine) — real, not sector-generic
    signal_blocks = _signal_insight_blocks(bundle)
    s4 = new_section("Señales Activas", 4, signal_blocks) if signal_blocks else None

    # AI summary (Claude)
    kpis = bundle.get("kpis", {})
    ai_context = {
        "company_name": name, "cif": cif_norm, "cnae": cnae,
        "revenue": kpis.get("revenue"), "employees": (bundle.get("statements") or {}).get("employees"),
        "ebitda_margin": kpis.get("ebitda_margin"), "growth": kpis.get("revenue_growth_yoy"),
        "assessment": bundle.get("assessment"),
        "sector_trend": econ.get("trend"),
        "active_signals": [s.get("signal_type") for s in bundle.get("signals", [])],
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s2_blocks = []
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "company_summary", "date": now_iso()}
        s2_blocks.append(b)
    s2 = new_section("Resumen", 2, s2_blocks)

    s7_blocks = []
    if ai_result.get("conclusion"):
        s7_blocks.append(text_block(ai_result["conclusion"], style="conclusion"))
    s7 = new_section("Conclusión", 7, s7_blocks)

    doc["sections"] = [s for s in [s1, s2, s3, s4, s7] if s]
    doc["metadata"] = {
        "master_id": bundle["master_id"], "cif": cif_norm, "cnae": cnae,
        "type": "company_profile", "financial_engine_used": True, "fact_locked": True, "schema": "modern",
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()

    await db.docstudio_documents.insert_one(doc)
    return doc


# ══════════════════════════════════════════
# DATA FETCHERS
# ══════════════════════════════════════════

async def _get_economic_profile(cnae_code: str) -> Dict:
    from services.economic_intelligence import get_cnae_economic_profile
    try:
        return await get_cnae_economic_profile(cnae_code)
    except Exception:
        return {}


async def _get_sector_intelligence(cnae_code: str) -> Dict:
    sector = await db.sector_intelligence.find_one(
        {"cnae_code": cnae_code}, {"_id": 0}
    )
    return sector or {}


async def _get_brand(brand_id: str) -> Dict:
    brand = await db.docstudio_brands.find_one({"brand_id": brand_id}, {"_id": 0})
    if brand:
        return brand
    from docstudio.templates import BRANDS
    return BRANDS.get("bud_advisors", {})


async def compose_benchmark_report(cnae_code: str, brand_id: str = "brand_bud",
                                   user: str = None) -> Dict:
    """Compose a sector benchmark report with Financial Engine data."""
    from services.cnae_catalog import CNAE_DIVISIONS
    from docstudio.financial_engine import analyze_sector_benchmark

    cnae_label = CNAE_DIVISIONS.get(cnae_code, {}).get("label", cnae_code)
    econ = await _get_economic_profile(cnae_code)
    benchmark = await analyze_sector_benchmark(cnae_code)

    doc = new_document(
        title=f"Benchmark Report — CNAE {cnae_code}: {cnae_label}",
        template_id="tpl_benchmark", brand_id=brand_id, created_by=user,
    )

    s1 = new_section("Portada", 1, [
        cover_block(title="Benchmark Sectorial", subtitle=f"CNAE {cnae_code}: {cnae_label}"),
    ])

    # Benchmark KPIs from Financial Engine (deterministic)
    bm_kpis = []
    bm_kpis.append(kpi_block("Empresas comparables", str(benchmark.get("peers", 0)), "peers"))
    for metric, label, unit in [
        ("revenue", "Revenue mediana", "EUR"),
        ("ebitda", "EBITDA mediana", "EUR"),
        ("ebitda_margin", "Margen EBITDA mediana", "%"),
        ("employees", "Empleados mediana", "personas"),
        ("revenue_per_employee", "Revenue/empleado mediana", "EUR"),
    ]:
        q = benchmark.get(metric, {})
        if q and q.get("median") is not None:
            val = q["median"]
            display = f"{val:,.0f}" if unit == "EUR" else f"{val*100:.1f}" if metric == "ebitda_margin" else f"{val:,.0f}"
            b = kpi_block(label, display, unit)
            b["data_lineage"] = {"source": "financial_engine", "calculation": f"percentile_50({metric})", "date": now_iso()}
            bm_kpis.append(b)
    s3 = new_section("Benchmark del Sector", 3, bm_kpis)

    # Quartiles table
    quartile_rows = []
    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("ebitda_margin", "Margen EBITDA"), ("employees", "Empleados")]:
        q = benchmark.get(metric, {})
        if q:
            def fmt_val(v, m=metric):
                return f"{v*100:.1f}%" if m == "ebitda_margin" else f"{v:,.0f}"
            quartile_rows.append([label, fmt_val(q.get("min", 0)), fmt_val(q.get("q1", 0)), fmt_val(q.get("median", 0)), fmt_val(q.get("q3", 0)), fmt_val(q.get("max", 0))])
    s4 = new_section("Distribucion Estadistica", 4, [
        table_block("Cuartiles sectoriales", ["Metrica", "Min", "Q1", "Mediana", "Q3", "Max"], quartile_rows),
    ]) if quartile_rows else None

    # AI summary
    ai_context = {"cnae_code": cnae_code, "cnae_label": cnae_label, "benchmark": benchmark,
                  "trend": econ.get("trend"), "sources": econ.get("sources_available", [])}
    ai_result = await generate_summary(ai_context, doc_type="sector_report", document_id=doc["document_id"])

    s2 = new_section("Resumen Ejecutivo", 2, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "benchmark_summary", "date": now_iso()}
        s2["blocks"].append(b)

    s5 = new_section("Conclusiones", 5, [])
    if ai_result.get("conclusion"):
        b = text_block(ai_result["conclusion"], style="conclusion")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "benchmark_conclusion", "date": now_iso()}
        s5["blocks"].append(b)

    doc["sections"] = [s for s in [s1, s2, s3, s4, s5] if s]
    doc["metadata"] = {"cnae_code": cnae_code, "type": "benchmark", "peers": benchmark.get("peers", 0)}
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_investment_memo(company_id: str = None, cif: str = None,
                                  brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Compose an Investment Memo. Fase 2: modern schema + real engines + real valuation."""
    from docstudio.financial_engine import analyze_sector_benchmark
    from services.cnae_catalog import CNAE_DIVISIONS

    bundle = await DA.company_intelligence(company_id or cif)
    if not bundle.get("found"):
        return {"error": "Company not found"}

    ident = bundle["identity"]
    name = ident.get("name", "Empresa")
    cnae = ident.get("cnae_code", "")
    cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")
    kpis = bundle.get("kpis", {})
    benchmark = await analyze_sector_benchmark(cnae) if cnae else {}

    doc = new_document(
        title=f"Investment Memo — {name}",
        template_id="tpl_investment_memo", brand_id=brand_id, created_by=user,
    )

    s1 = new_section("Portada", 1, [
        cover_block(title=name, subtitle=f"Investment Memo — CNAE {cnae}: {cnae_label}"),
    ])

    # Company KPIs from the real Financial Engine
    s3_blocks = _company_kpi_blocks(bundle)
    vb = _valuation_block(bundle)
    if vb:
        s3_blocks.append(vb)
    s3 = new_section("Métricas Financieras", 3, s3_blocks)

    # Sector positioning table (modern benchmark)
    pos_rows = []
    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("ebitda_margin", "Margen EBITDA")]:
        q = benchmark.get(metric, {})
        if q and q.get("median"):
            med = f"{q['median']*100:.1f}%" if metric == "ebitda_margin" else f"{q['median']:,.0f}"
            pos_rows.append([label, f"Mediana sector: {med}", f"Peers: {benchmark.get('peers', 0)}"])
    s4 = new_section("Posicionamiento Sectorial", 4, [
        table_block("Comparación vs sector", ["Métrica", "Benchmark", "Peers"], pos_rows),
    ]) if pos_rows else None

    # Active signals (real)
    sig_blocks = _signal_insight_blocks(bundle)
    s6 = new_section("Señales Activas", 6, sig_blocks) if sig_blocks else None

    # AI-generated investment thesis (Claude)
    ai_context = {
        "company_name": name, "cnae": cnae, "cnae_label": cnae_label,
        "revenue": kpis.get("revenue"), "ebitda_margin": kpis.get("ebitda_margin"),
        "revenue_yoy": kpis.get("revenue_growth_yoy"), "cagr": kpis.get("revenue_cagr"),
        "valuation": bundle.get("valuation"), "assessment": bundle.get("assessment"),
        "sector_peers": benchmark.get("peers", 0),
        "active_signals": [s.get("signal_type") for s in bundle.get("signals", [])],
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s2 = new_section("Tesis de Inversión", 2, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "investment_thesis", "date": now_iso()}
        s2["blocks"].append(b)
    for f in ai_result.get("key_findings", [])[:3]:
        s2["blocks"].append(insight_block("Punto clave", f, importance="high"))

    s5 = new_section("Conclusión y Recomendación", 5, [])
    if ai_result.get("conclusion"):
        s5["blocks"].append(text_block(ai_result["conclusion"], style="conclusion"))

    doc["sections"] = [s for s in [s1, s2, s3, s4, s6, s5] if s]
    doc["metadata"] = {
        "master_id": bundle["master_id"], "type": "investment_memo",
        "financial_engine_used": True, "fact_locked": True, "schema": "modern",
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_teaser(company_id: str = None, cif: str = None,
                         brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Compose a Teaser (blind profile) for a company. Fase 2: modern schema + real engines."""
    from services.cnae_catalog import CNAE_DIVISIONS

    bundle = await DA.company_intelligence(company_id or cif)
    if not bundle.get("found"):
        return {"error": "Company not found"}

    ident = bundle["identity"]
    name = ident.get("name", "Empresa")
    cnae = ident.get("cnae_code", "")
    cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")

    doc = new_document(
        title=f"Teaser — {name}",
        template_id="tpl_teaser", brand_id=brand_id, created_by=user,
    )

    s1 = new_section("Portada", 1, [
        cover_block(title="Oportunidad de Inversión", subtitle=f"Sector: {cnae_label} — Proyecto confidencial"),
    ])

    # Key metrics from the real Financial Engine
    s2 = new_section("Métricas Clave", 2, _company_kpi_blocks(bundle))

    # AI teaser narrative (Claude, fact-locked)
    kpis = bundle.get("kpis", {})
    ai_context = {
        "sector": cnae_label, "revenue": kpis.get("revenue"),
        "ebitda_margin": kpis.get("ebitda_margin"),
        "growth": kpis.get("revenue_growth_yoy"),
        "signals": [s.get("signal_type") for s in bundle.get("signals", [])],
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s3 = new_section("Descripción de la Oportunidad", 3, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "teaser_narrative", "date": now_iso()}
        s3["blocks"].append(b)

    doc["sections"] = [s1, s2, s3]
    doc["metadata"] = {
        "master_id": bundle["master_id"], "cif": bundle["cif_normalized"], "type": "teaser",
        "financial_engine_used": True, "fact_locked": True, "schema": "modern",
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_information_memorandum(company_id: str = None, cif: str = None,
                                         brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Full Information Memorandum. Fase 2: modern schema + real engines + REAL valuation.

    The old 'valoración preliminar' was a heuristic (sector_revenue_median * 1.5). It is
    replaced by the real Financial Intelligence Engine `valuation()` (honest: market_observed
    vs inferred_reference, or nothing when insufficient). Risks/opportunities now come from
    the engine's real assessment + active signals, not a blind AI call.
    """
    from docstudio.financial_engine import analyze_sector_benchmark
    from services.cnae_catalog import CNAE_DIVISIONS

    bundle = await DA.company_intelligence(company_id or cif)
    if not bundle.get("found"):
        return {"error": "Company not found"}

    ident = bundle["identity"]
    name = ident.get("name", "Empresa")
    cnae = ident.get("cnae_code", "")
    cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")
    cif_norm = bundle.get("cif_normalized", "—")
    kpis = bundle.get("kpis", {})
    assessment = bundle.get("assessment", {}) or {}
    benchmark = await analyze_sector_benchmark(cnae) if cnae else {}
    econ = await _get_economic_profile(cnae) if cnae else {}

    doc = new_document(
        title=f"Information Memorandum — {name}",
        template_id="tpl_im", brand_id=brand_id, created_by=user,
        description=f"Memorándum informativo completo de {name}",
    )

    # 1. Cover
    s1 = new_section("Portada", 1, [
        cover_block(title=name, subtitle="Information Memorandum — Confidencial"),
    ])

    # 2. Executive Summary (Claude, fact-locked over real data)
    ai_context = {
        "company_name": name, "cnae": cnae, "cnae_label": cnae_label,
        "revenue": kpis.get("revenue"), "ebitda_margin": kpis.get("ebitda_margin"),
        "revenue_yoy": kpis.get("revenue_growth_yoy"), "cagr": kpis.get("revenue_cagr"),
        "valuation": bundle.get("valuation"), "assessment": assessment,
        "sector_peers": benchmark.get("peers", 0),
        "sector_revenue_median": benchmark.get("revenue", {}).get("median"),
        "active_signals": [s.get("signal_type") for s in bundle.get("signals", [])],
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s2 = new_section("Resumen Ejecutivo", 2, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "im_executive_summary", "date": now_iso()}
        s2["blocks"].append(b)

    # 3. Company Overview
    info_rows = [["Razón social", name], ["CIF", cif_norm]]
    if ident.get("provincia"):
        info_rows.append(["Provincia", ident["provincia"]])
    if cnae_label:
        info_rows.append(["Sector CNAE", f"{cnae} — {cnae_label}"])
    s3 = new_section("Descripción de la Compañía", 3, [
        table_block("Información general", ["Campo", "Valor"], info_rows),
    ])

    # 4. Financial Highlights (real Financial Engine) + revenue history from evolution
    s4_blocks = _company_kpi_blocks(bundle)
    rev_rows = []
    for p in (bundle.get("evolution", {}) or {}).get("points", []):
        rev_rows.append([str(p.get("year", "")), f"{(p.get('revenue') or 0):,.0f}",
                         f"{(p.get('ebitda') or 0):,.0f}"])
    if rev_rows:
        s4_blocks.append(table_block("Evolución histórica", ["Año", "Ingresos (EUR)", "EBITDA (EUR)"], rev_rows))
    s4 = new_section("Análisis Financiero", 4, s4_blocks)

    # 5. Sector & Benchmark (modern benchmark)
    bm_rows = []
    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"),
                          ("ebitda_margin", "Margen EBITDA"), ("employees", "Empleados")]:
        q = benchmark.get(metric, {})
        if q and q.get("median") is not None:
            def fmt_val(v, m=metric):
                return f"{v*100:.1f}%" if m == "ebitda_margin" else f"{v:,.0f}"
            bm_rows.append([label, fmt_val(q.get("q1", 0)), fmt_val(q["median"]),
                           fmt_val(q.get("q3", 0)), str(benchmark.get("peers", 0))])
    s5 = new_section("Posicionamiento Sectorial", 5,
                     [table_block("Benchmark sectorial", ["Métrica", "Q1", "Mediana", "Q3", "Peers"], bm_rows)]) if bm_rows else None

    # 6. Market Context — Economic Intelligence
    s6_market = new_section("Contexto de Mercado", 6, [])
    if econ.get("active_companies_national"):
        s6_market["blocks"].append(kpi_block("Empresas activas en sector",
            f"{econ['active_companies_national']['value']:,.0f}", "empresas"))
    if econ.get("exports_eur"):
        b = kpi_block("Exportaciones sector", f"{econ['exports_eur']['value']:,.0f}", "EUR")
        b["data_lineage"] = {"source": "economic_intelligence", "date": now_iso()}
        s6_market["blocks"].append(b)
    if econ.get("procurement_contracts"):
        s6_market["blocks"].append(kpi_block("Contratos públicos", f"{econ['procurement_contracts']['value']}", "contratos"))

    # 7. Risks & Opportunities — REAL assessment + active signals (no blind AI)
    s7_risks = new_section("Riesgos y Oportunidades", 7, [])
    for risk in (assessment.get("risks", []) + assessment.get("weaknesses", []))[:4]:
        b = insight_block("Riesgo", risk, importance="high")
        b["data_lineage"] = {"source": _FIN, "task": "assessment_risk", "date": now_iso()}
        s7_risks["blocks"].append(b)
    for sig in bundle.get("signals", []):
        if sig.get("severity") == "opportunity":
            b = insight_block("Oportunidad", sig.get("explanation", sig.get("signal_type", "")), importance="medium")
            b["data_lineage"] = {"source": "signal-intelligence-v1", "signal_id": sig.get("signal_id"), "date": now_iso()}
            s7_risks["blocks"].append(b)
    for strength in assessment.get("strengths", [])[:3]:
        s7_risks["blocks"].append(insight_block("Fortaleza", strength, importance="medium"))

    # 8. Valuation — REAL Financial Engine valuation (honest), not a heuristic
    s8_val = new_section("Valoración", 8, [])
    vb = _valuation_block(bundle)
    if vb:
        s8_val["blocks"].append(vb)
        val = bundle.get("valuation", {})
        rng = val.get("range") or {}
        if rng.get("low") and rng.get("high"):
            s8_val["blocks"].append(text_block(
                f"Rango orientativo: {rng['low']:,.0f} € – {rng['high']:,.0f} € "
                f"(confianza {val.get('confidence', '—')}). "
                + " ".join(val.get("hypotheses", [])), style="body"))
    else:
        s8_val["blocks"].append(text_block(
            "Datos insuficientes para una valoración fiable. Se requiere información financiera adicional.", style="body"))

    # 9. Key Findings (Claude)
    s9 = new_section("Hallazgos Clave", 9, [])
    for f in ai_result.get("key_findings", []):
        b = insight_block("Hallazgo", f, importance="high")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "im_findings", "date": now_iso()}
        s9["blocks"].append(b)

    # 10. Conclusion & Recommendations (Claude)
    s10 = new_section("Conclusión y Recomendaciones", 10, [])
    if ai_result.get("conclusion"):
        b = text_block(ai_result["conclusion"], style="conclusion")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "im_conclusion", "date": now_iso()}
        s10["blocks"].append(b)
    for rec in ai_result.get("recommendations", []):
        s10["blocks"].append(insight_block("Recomendación", rec, importance="medium"))

    doc["sections"] = [s for s in [s1, s2, s3, s4, s5, s6_market, s7_risks, s8_val, s9, s10] if s]
    doc["metadata"] = {
        "master_id": bundle["master_id"], "cif": cif_norm,
        "cnae_code": cnae, "type": "information_memorandum",
        "financial_engine_used": True, "fact_locked": True, "schema": "modern",
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_company_snapshot(company_id: str = None, cif: str = None,
                                    brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Company Snapshot — minimal intelligence unit. Fase 2: modern schema + real engines."""
    from docstudio.financial_engine import analyze_sector_benchmark, compute_sector_positioning
    from services.cnae_catalog import CNAE_DIVISIONS

    bundle = await DA.company_intelligence(company_id or cif)
    if not bundle.get("found"):
        return {"error": "Company not found"}

    ident = bundle["identity"]
    name = ident.get("name", "Empresa")
    cnae = ident.get("cnae_code", "")
    cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")
    kpis = bundle.get("kpis", {})
    benchmark = await analyze_sector_benchmark(cnae) if cnae else {}

    # Comparables come REAL from the Financial Engine bundle (sector+size+geo)
    comparables = (bundle.get("comparables", {}) or {}).get("peers", [])

    # Sector positioning (deterministic percentiles) over real KPIs
    company_metrics = {
        "revenue": kpis.get("revenue"), "ebitda": kpis.get("ebitda"),
        "employees": (bundle.get("statements") or {}).get("employees"),
        "ebitda_margin": kpis.get("ebitda_margin"),
    }
    positioning = compute_sector_positioning(company_metrics, benchmark) if benchmark.get("peers") else {}

    doc = new_document(
        title=f"Company Snapshot — {name}",
        template_id="tpl_snapshot", brand_id=brand_id, created_by=user,
    )

    s1 = new_section("Portada", 1, [
        cover_block(title=name, subtitle=f"Company Snapshot — CNAE {cnae}: {cnae_label}"),
    ])

    # 2. KPIs (real Financial Engine)
    s2 = new_section("KPIs", 2, _company_kpi_blocks(bundle))

    # 3. Positioning (deterministic percentiles)
    pos_blocks = []
    if positioning:
        pos_rows = []
        for metric, data in positioning.items():
            v = data["value"]
            v_str = f"{v*100:.1f}%" if (v and abs(v) < 1) else f"{v:,.0f}"
            pos_rows.append([data["label"], v_str, f"P{data['percentile']:.0f}",
                             data["position"].replace("_", " ").title()])
        b = table_block("Posicionamiento sectorial", ["Métrica", "Valor", "Percentil", "Posición"], pos_rows)
        b["data_lineage"] = {"source": _FIN, "calculation": "sector_positioning", "date": now_iso()}
        pos_blocks.append(b)
    s3 = new_section("Posicionamiento", 3, pos_blocks) if pos_blocks else None

    # 4. Comparables (real, from Financial Engine)
    comp_blocks = []
    if comparables:
        comp_rows = []
        for c in comparables[:5]:
            m = c.get("ebitda_margin")
            comp_rows.append([
                (c.get("name") or "")[:35],
                f"{c['revenue']:,.0f}" if c.get("revenue") else "—",
                f"{m*100:.1f}%" if m is not None else "—",
                c.get("provincia", "—"),
            ])
        b = table_block("Comparables (sector+tamaño+geografía)", ["Empresa", "Revenue (EUR)", "Margen", "Provincia"], comp_rows)
        b["data_lineage"] = {"source": _FIN, "calculation": "financial_comparables", "date": now_iso()}
        comp_blocks.append(b)
    s4 = new_section("Comparables", 4, comp_blocks) if comp_blocks else None

    # 5. AI Conclusion (Claude, fact-locked, short)
    ai_context = {
        "company_name": name, "cnae": cnae, "cnae_label": cnae_label,
        "revenue": kpis.get("revenue"), "ebitda_margin": kpis.get("ebitda_margin"),
        "cagr": kpis.get("revenue_cagr"), "yoy": kpis.get("revenue_growth_yoy"),
        "positioning": positioning, "comparables_count": len(comparables),
        "active_signals": [s.get("signal_type") for s in bundle.get("signals", [])],
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s5 = new_section("Conclusión", 5, [])
    conclusion_text = ai_result.get("conclusion", ai_result.get("executive_summary", ""))
    if conclusion_text:
        sentences = conclusion_text.split(". ")
        short = ". ".join(sentences[:5]) + ("." if sentences and not sentences[-1].endswith(".") else "")
        b = text_block(short, style="conclusion")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "snapshot_conclusion", "date": now_iso()}
        s5["blocks"].append(b)

    doc["sections"] = [s for s in [s1, s2, s3, s4, s5] if s]
    doc["metadata"] = {
        "master_id": bundle["master_id"], "cnae_code": cnae, "type": "company_snapshot",
        "financial_engine_used": True, "fact_locked": True, "schema": "modern",
        "comparables_found": len(comparables), "sector_peers": benchmark.get("peers", 0),
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_benchmark_advanced(cnae_code: str, company_id: str = None,
                                      brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Advanced Benchmark Report with comparables, positioning, and SWOT. <60 seconds."""
    from docstudio.financial_engine import analyze_sector_benchmark, compute_sector_positioning
    from services.cnae_catalog import CNAE_DIVISIONS

    cnae_label = CNAE_DIVISIONS.get(cnae_code, {}).get("label", cnae_code)
    await _get_economic_profile(cnae_code)  # available for AI context
    benchmark = await analyze_sector_benchmark(cnae_code)

    # If company provided, compute positioning + comparables from the real engine
    bundle = None
    company_name = None
    positioning = {}
    comparables = []
    if company_id:
        bundle = await DA.company_intelligence(company_id)
        if bundle.get("found"):
            company_name = bundle["identity"].get("name")
            kpis = bundle.get("kpis", {})
            company_metrics = {
                "revenue": kpis.get("revenue"), "ebitda": kpis.get("ebitda"),
                "employees": (bundle.get("statements") or {}).get("employees"),
                "ebitda_margin": kpis.get("ebitda_margin"),
            }
            positioning = compute_sector_positioning(company_metrics, benchmark)
            comparables = (bundle.get("comparables", {}) or {}).get("peers", [])

    doc = new_document(
        title=f"Benchmark Report — CNAE {cnae_code}: {cnae_label}",
        template_id="tpl_bud_benchmark", brand_id=brand_id, created_by=user,
    )

    # 1. Cover
    title_suffix = f" vs {company_name}" if company_name else ""
    s1 = new_section("Portada", 1, [
        cover_block(title=f"Benchmark Sectorial{title_suffix}", subtitle=f"CNAE {cnae_code}: {cnae_label}"),
    ])

    # 2. Sector KPIs (Financial Engine)
    bm_kpis = []
    bm_kpis.append(kpi_block("Empresas analizadas", str(benchmark.get("peers", 0)), "peers"))
    for metric, label, unit in [
        ("revenue", "Revenue mediana", "EUR"), ("ebitda", "EBITDA mediana", "EUR"),
        ("ebitda_margin", "Margen EBITDA med.", "%"), ("employees", "Empleados mediana", ""),
        ("revenue_per_employee", "Rev/empleado med.", "EUR"),
    ]:
        q = benchmark.get(metric, {})
        if q and q.get("median") is not None:
            val = q["median"]
            display = f"{val*100:.1f}" if metric == "ebitda_margin" else f"{val:,.0f}"
            b = kpi_block(label, display, unit)
            b["data_lineage"] = {"source": "financial_engine", "calculation": f"percentile_50({metric})", "date": now_iso()}
            bm_kpis.append(b)
    s3 = new_section("Benchmark del Sector", 3, bm_kpis)

    # 3. Distribution table (quartiles)
    quartile_rows = []
    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"),
                          ("ebitda_margin", "Margen EBITDA"), ("employees", "Empleados"),
                          ("revenue_per_employee", "Rev/empleado")]:
        q = benchmark.get(metric, {})
        if q:
            def fmt_val(v, m=metric):
                return f"{v*100:.1f}%" if m == "ebitda_margin" else f"{v:,.0f}"
            quartile_rows.append([label, fmt_val(q.get("min", 0)), fmt_val(q.get("q1", 0)),
                                 fmt_val(q["median"]), fmt_val(q.get("q3", 0)), fmt_val(q.get("max", 0))])
    s4 = new_section("Distribucion Estadistica", 4, [
        table_block("Cuartiles sectoriales", ["Metrica", "Min", "Q1", "Mediana", "Q3", "Max"], quartile_rows),
    ]) if quartile_rows else None

    # 4. Company positioning (if company provided)
    s5 = None
    if positioning:
        pos_rows = []
        for metric, data in positioning.items():
            val_str = f"{data['value']*100:.1f}%" if metric == "ebitda_margin" else f"{data['value']:,.0f}"
            med_str = f"{data['median']*100:.1f}%" if metric == "ebitda_margin" else f"{data['median']:,.0f}"
            gap = data.get("gap_vs_median_pct")
            gap_str = f"{gap:+.1f}%" if gap is not None else "—"
            pos_rows.append([data["label"], val_str, med_str, gap_str,
                           f"P{data['percentile']:.0f}", data["position"].replace("_", " ").title()])
        b = table_block("Empresa vs Sector", ["Metrica", "Empresa", "Mediana", "Gap", "Percentil", "Posicion"], pos_rows)
        b["data_lineage"] = {"source": "financial_engine", "calculation": "sector_positioning", "date": now_iso()}
        s5 = new_section("Posicionamiento Competitivo", 5, [b])

    # 5. Comparables (real, from Financial Engine bundle)
    s6 = None
    if comparables:
        comp_rows = []
        for c in comparables[:8]:
            m = c.get("ebitda_margin")
            comp_rows.append([(c.get("name") or "")[:30], f"{c.get('revenue', 0):,.0f}",
                              f"{m*100:.1f}%" if m is not None else "—", c.get("provincia", "—")])
        b = table_block("Comparables (sector+tamaño+geografía)", ["Empresa", "Revenue", "Margen", "Provincia"], comp_rows)
        b["data_lineage"] = {"source": _FIN, "calculation": "financial_comparables", "date": now_iso()}
        s6 = new_section("Comparables", 6, [b])

    # 6. AI SWOT (Claude, fact-locked)
    ai_context = {
        "cnae_code": cnae_code, "cnae_label": cnae_label,
        "benchmark_peers": benchmark.get("peers", 0),
        "revenue_median": benchmark.get("revenue", {}).get("median"),
        "ebitda_margin_median": benchmark.get("ebitda_margin", {}).get("median"),
        "positioning": positioning if positioning else None,
        "comparables_count": len(comparables),
    }
    if bundle and bundle.get("found"):
        ai_context["company_name"] = company_name
        ai_context["company_revenue"] = bundle.get("kpis", {}).get("revenue")
        ai_context["company_margin"] = bundle.get("kpis", {}).get("ebitda_margin")

    ai_result = await generate_summary(ai_context, doc_type="sector_report", document_id=doc["document_id"])

    s2 = new_section("Resumen Ejecutivo", 2, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "benchmark_summary", "date": now_iso()}
        s2["blocks"].append(b)

    s7_blocks = []
    for f in ai_result.get("key_findings", []):
        s7_blocks.append(insight_block("Hallazgo", f, importance="high"))
    if ai_result.get("conclusion"):
        b = text_block(ai_result["conclusion"], style="conclusion")
        b["data_lineage"] = {"source": "ai", "model": "claude", "task": "benchmark_conclusion", "date": now_iso()}
        s7_blocks.append(b)
    s7 = new_section("Conclusiones", 7, s7_blocks) if s7_blocks else None

    doc["sections"] = [s for s in [s1, s2, s3, s4, s5, s6, s7] if s]
    doc["metadata"] = {
        "cnae_code": cnae_code, "type": "benchmark_advanced",
        "master_id": bundle["master_id"] if (bundle and bundle.get("found")) else None,
        "financial_engine_used": True, "fact_locked": True, "schema": "modern",
        "comparables_found": len(comparables), "sector_peers": benchmark.get("peers", 0),
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc

def compute_quality_score(doc: Dict) -> Dict:
    """Compute a quality score for a document. Deterministic, no AI."""
    scores = {}
    sections = doc.get("sections", [])
    all_blocks = [b for s in sections for b in s.get("blocks", [])]

    # 1. Data completeness (are sections populated?)
    total_sections = len(sections)
    populated = sum(1 for s in sections if s.get("blocks"))
    scores["data_completeness"] = round(populated / max(total_sections, 1) * 100)

    # 2. Financial coverage (KPI blocks with Financial Engine lineage)
    kpi_blocks = [b for b in all_blocks if b.get("block_type") == "kpi"]
    _fin_sources = {"financial_engine", "financial-intelligence-v1"}
    fin_engine_blocks = [b for b in all_blocks if b.get("data_lineage", {}).get("source") in _fin_sources]
    scores["financial_coverage"] = round(len(fin_engine_blocks) / max(len(kpi_blocks), 1) * 100)

    # 3. Missing sections
    expected_types = {"cover", "text", "kpi", "insight"}
    present_types = set(b.get("block_type") for b in all_blocks)
    scores["block_variety"] = round(len(present_types & expected_types) / len(expected_types) * 100)

    # 4. AI confidence (check if AI blocks exist and have lineage)
    ai_blocks = [b for b in all_blocks if b.get("data_lineage", {}).get("source") == "ai"]
    scores["ai_coverage"] = min(100, len(ai_blocks) * 20)  # 5+ AI blocks = 100%

    # 5. Fact-lock compliance
    fact_locked = doc.get("metadata", {}).get("fact_locked", False)
    no_untraced = all(b.get("data_lineage") for b in all_blocks if b.get("block_type") not in ("divider", "cover"))
    scores["fact_lock_compliance"] = 100 if fact_locked and no_untraced else 60 if no_untraced else 30

    # Global score
    weights = {"data_completeness": 0.25, "financial_coverage": 0.20, "block_variety": 0.15,
               "ai_coverage": 0.15, "fact_lock_compliance": 0.25}
    global_score = round(sum(scores[k] * weights[k] for k in weights))

    return {
        "global_score": global_score,
        "scores": scores,
        "total_blocks": len(all_blocks),
        "total_sections": total_sections,
        "ai_blocks": len(ai_blocks),
        "financial_engine_blocks": len(fin_engine_blocks),
        "grade": "A" if global_score >= 85 else "B" if global_score >= 70 else "C" if global_score >= 50 else "D",
    }


# ══════════════════════════════════════════
# GENERIC TEMPLATE COMPOSER
# ══════════════════════════════════════════

async def compose_from_template(template_id: str, company_id: str = None, cif: str = None,
                                 cnae_code: str = None, brand_id: str = "brand_bud",
                                 user: str = None) -> Dict:
    """Compose a document from ANY user-created template. No hardcoded logic per template.
    
    Reads the template's section definitions, resolves data sources, and populates blocks.
    """
    from docstudio.financial_engine import analyze_sector_benchmark
    from services.cnae_catalog import CNAE_DIVISIONS

    template = await db.docstudio_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not template:
        return {"error": f"Template {template_id} not found"}

    # Resolve company (modern schema + real engines) if provided
    bundle = None
    company_name = None
    kpis = {}
    if company_id or cif:
        bundle = await DA.company_intelligence(company_id or cif)
        if bundle.get("found"):
            company_name = bundle["identity"].get("name")
            cnae_code = cnae_code or bundle["identity"].get("cnae_code")
            kpis = bundle.get("kpis", {})

    cnae_label = CNAE_DIVISIONS.get(cnae_code, {}).get("label", "") if cnae_code else ""
    benchmark = await analyze_sector_benchmark(cnae_code) if cnae_code else {}
    econ = await _get_economic_profile(cnae_code) if cnae_code else {}

    # Build document
    title_entity = company_name or cnae_label
    doc = new_document(
        title=f"{template.get('name', 'Documento')} — {title_entity}",
        template_id=template_id,
        brand_id=brand_id or template.get("brand_id", "brand_bud"),
        created_by=user,
    )

    sections = []
    now = now_iso()

    for tpl_section in template.get("sections", []):
        blocks = []
        title = tpl_section.get("title", "")
        block_types = tpl_section.get("block_types", [])
        data_source = tpl_section.get("data_source", "")

        # Cover block
        if "cover" in block_types:
            blocks.append(cover_block(
                title=title_entity,
                subtitle=f"{template.get('name', '')} — CNAE {cnae_code}: {cnae_label}" if cnae_code else template.get("name", ""),
            ))

        # KPI blocks from data sources
        if "kpi" in block_types:
            if data_source in ("financial_engine", "") and bundle and bundle.get("found"):
                blocks.extend(_company_kpi_blocks(bundle))
            elif data_source == "economic_intelligence" and econ:
                if econ.get("active_companies_national"):
                    blocks.append(kpi_block("Empresas activas", f"{econ['active_companies_national']['value']:,.0f}", ""))
                if econ.get("exports_eur"):
                    blocks.append(kpi_block("Exportaciones", f"{econ['exports_eur']['value']:,.0f}", "EUR"))

        # Table blocks
        if "table" in block_types:
            if bundle and bundle.get("found"):
                ident = bundle["identity"]
                info_rows = [["Razón social", company_name or ""], ["CIF", bundle.get("cif_normalized", "—")]]
                if ident.get("provincia"):
                    info_rows.append(["Provincia", ident["provincia"]])
                if cnae_label:
                    info_rows.append(["Sector", f"CNAE {cnae_code}: {cnae_label}"])
                blocks.append(table_block("Información", ["Campo", "Valor"], info_rows))

            if benchmark.get("peers"):
                bm_rows = []
                for m, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("ebitda_margin", "Margen")]:
                    q = benchmark.get(m, {})
                    if q and q.get("median") is not None:
                        def fmt(v, metric=m):
                            return f"{v*100:.1f}%" if metric == "ebitda_margin" else f"{v:,.0f}"
                        bm_rows.append([label, fmt(q.get("q1", 0)), fmt(q["median"]), fmt(q.get("q3", 0))])
                if bm_rows:
                    b = table_block("Benchmark", ["Métrica", "Q1", "Mediana", "Q3"], bm_rows)
                    b["data_lineage"] = {"source": _FIN, "calculation": "quartiles", "date": now}
                    blocks.append(b)

        # Signal insight blocks (real) when the section wants insights and we have a company
        if "insight" in block_types and data_source in ("signal", "signals") and bundle and bundle.get("found"):
            blocks.extend(_signal_insight_blocks(bundle))

        # AI text/insight blocks — data_source 'ai' OR text/insight without another source
        needs_ai = data_source == "ai" or (("text" in block_types or "insight" in block_types)
                    and data_source not in ("financial_engine", "economic_intelligence", "signal", "signals"))
        if needs_ai:
            ai_context = {
                "section_title": title, "company_name": company_name,
                "cnae": cnae_code, "cnae_label": cnae_label,
                "revenue": kpis.get("revenue"), "ebitda_margin": kpis.get("ebitda_margin"),
                "growth": kpis.get("revenue_growth_yoy"), "sector_peers": benchmark.get("peers", 0),
                "active_signals": [s.get("signal_type") for s in (bundle.get("signals", []) if bundle else [])],
            }
            ai_result = await generate_summary(ai_context, document_id=doc["document_id"])

            if "text" in block_types and ai_result.get("executive_summary"):
                b = text_block(ai_result["executive_summary"], style="executive_summary")
                b["data_lineage"] = {"source": "ai", "model": "claude", "task": f"generic_{title[:20]}", "date": now}
                blocks.append(b)
            if "insight" in block_types:
                for finding in ai_result.get("key_findings", [])[:3]:
                    b = insight_block("Hallazgo", finding, importance="high")
                    b["data_lineage"] = {"source": "ai", "model": "claude", "task": "findings", "date": now}
                    blocks.append(b)

        sections.append(new_section(title, tpl_section.get("order", len(sections) + 1), blocks))

    doc["sections"] = sections
    doc["metadata"] = {
        "template_id": template_id, "template_name": template.get("name"),
        "master_id": bundle["master_id"] if (bundle and bundle.get("found")) else None,
        "cnae_code": cnae_code, "type": "custom_template",
        "financial_engine_used": True, "fact_locked": True, "schema": "modern",
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


def generate_template_preview(template: Dict, brand: Dict) -> Dict:
    """Generate a preview document with sample data. No DB, no AI, instant."""
    now = now_iso()

    doc = {
        "document_id": "preview",
        "title": f"Preview — {template.get('name', 'Plantilla')}",
        "template_id": template.get("template_id"),
        "brand_id": brand.get("brand_id", "brand_bud"),
        "version": 0,
        "status": "preview",
        "sections": [],
        "metadata": {"preview": True},
        "created_at": now,
    }

    SAMPLE = {
        "company": "Empresa Ejemplo SL",
        "revenue": "1.250.000",
        "ebitda_margin": "14.2%",
        "employees": "42",
        "cagr": "+8.3%",
        "yoy": "+5.1%",
        "rev_per_emp": "29.762",
        "sector": "Tecnologia y Software",
    }

    for tpl_section in template.get("sections", []):
        blocks = []
        block_types = tpl_section.get("block_types", [])

        if "cover" in block_types:
            blocks.append(cover_block(title=SAMPLE["company"], subtitle=f"Preview — {template.get('name', '')}"))

        if "kpi" in block_types:
            blocks.append(kpi_block("Facturacion", SAMPLE["revenue"], "EUR"))
            blocks.append(kpi_block("Margen EBITDA", SAMPLE["ebitda_margin"], ""))
            blocks.append(kpi_block("Empleados", SAMPLE["employees"], ""))
            blocks.append(kpi_block("CAGR", SAMPLE["cagr"], ""))

        if "table" in block_types:
            blocks.append(table_block("Datos ejemplo", ["Campo", "Valor"], [
                ["Empresa", SAMPLE["company"]], ["Sector", SAMPLE["sector"]],
                ["Revenue", SAMPLE["revenue"]], ["Empleados", SAMPLE["employees"]],
            ]))

        if "text" in block_types:
            blocks.append(text_block(
                "Esta seccion contendra texto narrativo generado automaticamente por IA. "
                "El contenido se basara en los datos reales de la empresa y del sector.",
                style="executive_summary" if "resumen" in tpl_section.get("title", "").lower() else "body",
            ))

        if "insight" in block_types:
            blocks.append(insight_block("Hallazgo ejemplo", "Este bloque contendra insights generados por IA basados en datos reales.", importance="high"))
            blocks.append(insight_block("Recomendacion ejemplo", "Las recomendaciones se generaran automaticamente.", importance="medium"))

        if "chart" in block_types:
            blocks.append(text_block("[Grafico: se generara con datos reales]", style="body"))

        doc["sections"].append(new_section(
            tpl_section.get("title", "Seccion"),
            tpl_section.get("order", len(doc["sections"]) + 1),
            blocks,
        ))

    return doc
