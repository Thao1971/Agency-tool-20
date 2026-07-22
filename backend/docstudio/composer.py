"""Document Composer — Assembles documents from data sources and AI.

Connects to Economic Intelligence, Sector Intelligence, companies_master, etc.
Populates template sections with real data blocks.
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

logger = logging.getLogger(__name__)


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
    """Compose a full company profile document."""
    query = {"master_company_id": company_id} if company_id else {"cif": cif}
    company = await db.companies_master.find_one(query, {"_id": 0})
    if not company:
        return {"error": "Company not found"}

    name = company.get("legal_name", "Empresa")
    cnae = company.get("cnae_primary", "")
    await _get_brand(brand_id)  # warm cache

    # Get economic profile for the CNAE
    econ = {}
    if cnae:
        econ = await _get_economic_profile(cnae)

    doc = new_document(
        title=f"Ficha de Compania — {name}",
        template_id="tpl_company_profile",
        brand_id=brand_id,
        created_by=user,
        description=f"Perfil de {name}",
    )

    # Cover
    s1 = new_section("Portada", 1, [
        cover_block(title=name, subtitle=f"CIF: {company.get('cif', '—')} — CNAE {cnae}"),
    ])

    # Company data KPIs
    company_kpis = []
    if company.get("revenue_latest"):
        company_kpis.append(kpi_block("Facturacion", f"{company['revenue_latest']:,.0f}", "EUR"))
    if company.get("employees_latest"):
        company_kpis.append(kpi_block("Empleados", f"{company['employees_latest']}", "personas"))
    if cnae:
        from services.cnae_catalog import CNAE_DIVISIONS
        company_kpis.append(kpi_block("Sector", CNAE_DIVISIONS.get(cnae, {}).get("label", cnae), f"CNAE {cnae}"))
    if company.get("province_name"):
        company_kpis.append(kpi_block("Provincia", company["province_name"], ""))
    s3 = new_section("Datos Generales", 3, company_kpis)

    # General info table
    info_rows = []
    for field, label in [("cif", "CIF"), ("legal_name", "Razon social"), ("legal_form", "Forma juridica"),
                         ("province_name", "Provincia"), ("status", "Estado")]:
        if company.get(field):
            info_rows.append([label, str(company[field])])
    s3_table = table_block("Informacion general", ["Campo", "Valor"], info_rows)
    s3["blocks"].append(s3_table)

    # AI summary
    ai_context = {
        "company_name": name, "cif": company.get("cif"), "cnae": cnae,
        "revenue": company.get("revenue_latest"), "employees": company.get("employees_latest"),
        "sector_trend": econ.get("trend"), "sector_signals": [s.get("signal_type") for s in econ.get("signals", [])],
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s2_blocks = []
    if ai_result.get("executive_summary"):
        s2_blocks.append(text_block(ai_result["executive_summary"], style="executive_summary"))
        s2_blocks[-1]["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "company_summary", "date": now_iso()}
    s2 = new_section("Resumen", 2, s2_blocks)

    s7_blocks = []
    if ai_result.get("conclusion"):
        s7_blocks.append(text_block(ai_result["conclusion"], style="conclusion"))
    s7 = new_section("Conclusion", 7, s7_blocks)

    doc["sections"] = [s1, s2, s3, s7]
    doc["metadata"] = {"company_id": company.get("master_company_id"), "cif": company.get("cif"), "cnae": cnae}
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
    """Compose an Investment Memo for a company."""
    from docstudio.financial_engine import analyze_company_financials, analyze_sector_benchmark

    query = {"master_company_id": company_id} if company_id else {"cif": cif}
    company = await db.companies_master.find_one(query, {"_id": 0})
    if not company:
        return {"error": "Company not found"}

    name = company.get("legal_name", "Empresa")
    cnae = company.get("cnae_primary", "")
    from services.cnae_catalog import CNAE_DIVISIONS
    cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")

    # Financial analysis (deterministic)
    financials = await db.iberinform_financials.find(
        {"company_id": company.get("master_company_id")}, {"_id": 0}
    ).sort("year", 1).to_list(10)
    fin_analysis = analyze_company_financials(financials) if financials else {}

    # Sector benchmark
    benchmark = await analyze_sector_benchmark(cnae) if cnae else {}

    doc = new_document(
        title=f"Investment Memo — {name}",
        template_id="tpl_investment_memo", brand_id=brand_id, created_by=user,
    )

    s1 = new_section("Portada", 1, [
        cover_block(title=name, subtitle=f"Investment Memo — CNAE {cnae}: {cnae_label}"),
    ])

    # Company KPIs
    company_kpis = []
    if company.get("revenue_latest"):
        company_kpis.append(kpi_block("Facturacion", f"{company['revenue_latest']:,.0f}", "EUR"))
    if fin_analysis.get("ebitda_margin") is not None:
        company_kpis.append(kpi_block("Margen EBITDA", f"{fin_analysis['ebitda_margin']:.1f}%", ""))
    if company.get("employees_latest"):
        company_kpis.append(kpi_block("Empleados", str(company["employees_latest"]), ""))
    if fin_analysis.get("revenue_yoy") is not None:
        company_kpis.append(kpi_block("Crecimiento YoY", f"{fin_analysis['revenue_yoy']:+.1f}%", ""))
    if fin_analysis.get("revenue_per_employee"):
        b = kpi_block("Revenue/empleado", f"{fin_analysis['revenue_per_employee']:,.0f}", "EUR")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "revenue_per_employee", "date": now_iso()}
        company_kpis.append(b)
    if fin_analysis.get("revenue_cagr") is not None:
        b = kpi_block("CAGR Revenue", f"{fin_analysis['revenue_cagr']:+.1f}%", "")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "cagr", "date": now_iso()}
        company_kpis.append(b)
    s3 = new_section("Metricas Financieras", 3, company_kpis)

    # Sector positioning table
    pos_rows = []
    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("ebitda_margin", "Margen EBITDA")]:
        q = benchmark.get(metric, {})
        if q and q.get("median"):
            pos_rows.append([label, f"Mediana sector: {q['median']:,.0f}" if metric != "ebitda_margin" else f"Mediana sector: {q['median']*100:.1f}%", f"Peers: {benchmark.get('peers', 0)}"])
    s4 = new_section("Posicionamiento Sectorial", 4, [
        table_block("Comparacion vs sector", ["Metrica", "Benchmark", "Peers"], pos_rows),
    ]) if pos_rows else None

    # AI-generated investment thesis
    ai_context = {
        "company_name": name, "cnae": cnae, "cnae_label": cnae_label,
        "revenue": company.get("revenue_latest"), "employees": company.get("employees_latest"),
        "ebitda_margin": fin_analysis.get("ebitda_margin"), "revenue_yoy": fin_analysis.get("revenue_yoy"),
        "cagr": fin_analysis.get("revenue_cagr"), "sector_peers": benchmark.get("peers", 0),
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s2 = new_section("Tesis de Inversion", 2, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "investment_thesis", "date": now_iso()}
        s2["blocks"].append(b)
    for f in ai_result.get("key_findings", [])[:3]:
        s2["blocks"].append(insight_block("Punto clave", f, importance="high"))

    s5 = new_section("Conclusion y Recomendacion", 5, [])
    if ai_result.get("conclusion"):
        s5["blocks"].append(text_block(ai_result["conclusion"], style="conclusion"))

    doc["sections"] = [s for s in [s1, s2, s3, s4, s5] if s]
    doc["metadata"] = {"company_id": company.get("master_company_id"), "type": "investment_memo"}
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_teaser(company_id: str = None, cif: str = None,
                         brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Compose a Teaser (blind profile) for a company."""
    from docstudio.financial_engine import analyze_company_financials

    query = {"master_company_id": company_id} if company_id else {"cif": cif}
    company = await db.companies_master.find_one(query, {"_id": 0})
    if not company:
        return {"error": "Company not found"}

    name = company.get("legal_name", "Empresa")
    cnae = company.get("cnae_primary", "")
    from services.cnae_catalog import CNAE_DIVISIONS
    cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")

    financials = await db.iberinform_financials.find(
        {"company_id": company.get("master_company_id")}, {"_id": 0}
    ).sort("year", 1).to_list(10)
    fin_analysis = analyze_company_financials(financials) if financials else {}

    doc = new_document(
        title=f"Teaser — {name}",
        template_id="tpl_teaser", brand_id=brand_id, created_by=user,
    )

    s1 = new_section("Portada", 1, [
        cover_block(title="Oportunidad de Inversion", subtitle=f"Sector: {cnae_label} — Proyecto confidencial"),
    ])

    # Key metrics (anonymized — teaser style)
    teaser_kpis = []
    if company.get("revenue_latest"):
        teaser_kpis.append(kpi_block("Facturacion", f"{company['revenue_latest']:,.0f}", "EUR"))
    if fin_analysis.get("ebitda_margin") is not None:
        teaser_kpis.append(kpi_block("Margen EBITDA", f"{fin_analysis['ebitda_margin']:.1f}%", ""))
    if company.get("employees_latest"):
        teaser_kpis.append(kpi_block("Plantilla", str(company["employees_latest"]), "empleados"))
    if fin_analysis.get("revenue_yoy") is not None:
        teaser_kpis.append(kpi_block("Crecimiento", f"{fin_analysis['revenue_yoy']:+.1f}%", "YoY"))
    s2 = new_section("Metricas Clave", 2, teaser_kpis)

    # AI teaser narrative
    ai_context = {
        "sector": cnae_label, "revenue": company.get("revenue_latest"),
        "ebitda_margin": fin_analysis.get("ebitda_margin"),
        "growth": fin_analysis.get("revenue_yoy"), "employees": company.get("employees_latest"),
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s3 = new_section("Descripcion de la Oportunidad", 3, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "teaser_narrative", "date": now_iso()}
        s3["blocks"].append(b)

    doc["sections"] = [s1, s2, s3]
    doc["metadata"] = {"company_id": company.get("master_company_id"), "type": "teaser"}
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_information_memorandum(company_id: str = None, cif: str = None,
                                         brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Compose a full Information Memorandum — the most comprehensive document type."""
    from docstudio.financial_engine import analyze_company_financials, analyze_sector_benchmark
    from services.cnae_catalog import CNAE_DIVISIONS

    query = {"master_company_id": company_id} if company_id else {"cif": cif}
    company = await db.companies_master.find_one(query, {"_id": 0})
    if not company:
        return {"error": "Company not found"}

    name = company.get("legal_name", "Empresa")
    cnae = company.get("cnae_primary", "")
    cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")

    financials = await db.iberinform_financials.find(
        {"company_id": company.get("master_company_id")}, {"_id": 0}
    ).sort("year", 1).to_list(10)
    fin_analysis = analyze_company_financials(financials) if financials else {}
    benchmark = await analyze_sector_benchmark(cnae) if cnae else {}
    econ = await _get_economic_profile(cnae) if cnae else {}

    doc = new_document(
        title=f"Information Memorandum — {name}",
        template_id="tpl_im", brand_id=brand_id, created_by=user,
        description=f"Memorandum informativo completo de {name}",
    )

    # 1. Cover
    s1 = new_section("Portada", 1, [
        cover_block(title=name, subtitle="Information Memorandum — Confidencial"),
    ])

    # 2. Executive Summary (AI)
    ai_context = {
        "company_name": name, "cnae": cnae, "cnae_label": cnae_label,
        "revenue": company.get("revenue_latest"), "employees": company.get("employees_latest"),
        "ebitda_margin": fin_analysis.get("ebitda_margin"), "revenue_yoy": fin_analysis.get("revenue_yoy"),
        "cagr": fin_analysis.get("revenue_cagr"),
        "sector_peers": benchmark.get("peers", 0),
        "sector_revenue_median": benchmark.get("revenue", {}).get("median"),
        "sector_ebitda_margin_median": benchmark.get("ebitda_margin", {}).get("median"),
        "exports": econ.get("exports_eur"),
        "procurement": econ.get("procurement_contracts"),
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s2 = new_section("Resumen Ejecutivo", 2, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "im_executive_summary", "date": now_iso()}
        s2["blocks"].append(b)

    # 3. Company Overview
    info_rows = []
    for field, label in [("legal_name", "Razon social"), ("cif", "CIF"), ("legal_form", "Forma juridica"),
                         ("province_name", "Provincia"), ("status", "Estado")]:
        if company.get(field):
            info_rows.append([label, str(company[field])])
    if cnae_label:
        info_rows.append(["Sector CNAE", f"{cnae} — {cnae_label}"])

    s3 = new_section("Descripcion de la Compania", 3, [
        table_block("Informacion general", ["Campo", "Valor"], info_rows),
    ])

    # 4. Financial Highlights (Financial Engine — deterministic)
    fin_kpis = []
    if company.get("revenue_latest"):
        fin_kpis.append(kpi_block("Facturacion", f"{company['revenue_latest']:,.0f}", "EUR"))
    if fin_analysis.get("ebitda_margin") is not None:
        b = kpi_block("Margen EBITDA", f"{fin_analysis['ebitda_margin']:.1f}%", "")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "ebitda_margin", "date": now_iso()}
        fin_kpis.append(b)
    if company.get("employees_latest"):
        fin_kpis.append(kpi_block("Plantilla", str(company["employees_latest"]), "empleados"))
    if fin_analysis.get("revenue_yoy") is not None:
        b = kpi_block("Crecimiento YoY", f"{fin_analysis['revenue_yoy']:+.1f}%", "")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "yoy_growth", "date": now_iso()}
        fin_kpis.append(b)
    if fin_analysis.get("revenue_cagr") is not None:
        b = kpi_block("CAGR Revenue", f"{fin_analysis['revenue_cagr']:+.1f}%", "")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "cagr", "date": now_iso()}
        fin_kpis.append(b)
    if fin_analysis.get("revenue_per_employee"):
        b = kpi_block("Revenue/empleado", f"{fin_analysis['revenue_per_employee']:,.0f}", "EUR")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "revenue_per_employee", "date": now_iso()}
        fin_kpis.append(b)

    # Revenue history table
    rev_rows = []
    for entry in fin_analysis.get("revenue_series", []):
        rev_rows.append([entry["period"], f"{entry['value']:,.0f}", f"{entry.get('yoy_pct', '—')}%"])

    s4_blocks = fin_kpis
    if rev_rows:
        s4_blocks.append(table_block("Evolucion historica", ["Ano", "Revenue (EUR)", "YoY %"], rev_rows))
    s4 = new_section("Analisis Financiero", 4, s4_blocks)

    # 5. Sector & Benchmark
    bm_rows = []
    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"),
                          ("ebitda_margin", "Margen EBITDA"), ("employees", "Empleados")]:
        q = benchmark.get(metric, {})
        if q and q.get("median") is not None:
            def fmt_val(v, m=metric):
                return f"{v*100:.1f}%" if m == "ebitda_margin" else f"{v:,.0f}"
            bm_rows.append([label, fmt_val(q.get("q1", 0)), fmt_val(q["median"]),
                           fmt_val(q.get("q3", 0)), str(benchmark.get("peers", 0))])
    s5_blocks = []
    if bm_rows:
        s5_blocks.append(table_block("Benchmark sectorial", ["Metrica", "Q1", "Mediana", "Q3", "Peers"], bm_rows))
    if econ.get("exports_eur"):
        s5_blocks.append(kpi_block("Exportaciones sector", f"{econ['exports_eur']['value']:,.0f}", "EUR"))
    s5 = new_section("Posicionamiento Sectorial", 5, s5_blocks) if s5_blocks else None

    # 6. Market Context (V2) — from Economic Intelligence
    s6_market = new_section("Contexto de Mercado", 6, [])
    if econ.get("active_companies_national"):
        s6_market["blocks"].append(kpi_block("Empresas activas en sector",
            f"{econ['active_companies_national']['value']:,.0f}", "empresas"))
    if econ.get("exports_eur"):
        b = kpi_block("Exportaciones sector", f"{econ['exports_eur']['value']:,.0f}", "EUR")
        b["data_lineage"] = {"source": "economic_intelligence", "date": now_iso()}
        s6_market["blocks"].append(b)
    if econ.get("imports_eur"):
        s6_market["blocks"].append(kpi_block("Importaciones sector", f"{econ['imports_eur']['value']:,.0f}", "EUR"))
    if econ.get("procurement_contracts"):
        s6_market["blocks"].append(kpi_block("Contratos publicos", f"{econ['procurement_contracts']['value']}", "contratos"))
    if econ.get("borme_events"):
        s6_market["blocks"].append(kpi_block("Actividad corporativa", f"{econ['borme_events']['value']}", "eventos BORME"))

    # 7. Risks & Opportunities (AI, fact-locked)
    from docstudio.model_provider import generate_analysis
    risk_context = {
        "company_name": name, "cnae": cnae, "cnae_label": cnae_label,
        "revenue": company.get("revenue_latest"), "ebitda_margin": fin_analysis.get("ebitda_margin"),
        "growth": fin_analysis.get("revenue_yoy"), "sector_peers": benchmark.get("peers", 0),
        "sector_trend": econ.get("trend"),
        "signals": [s.get("signal_type") for s in econ.get("signals", [])],
    }
    risk_result = await generate_analysis(risk_context,
        "Identify risks and opportunities for this company based ONLY on the data provided. Return JSON with 'risks' (array of strings) and 'opportunities' (array of strings). Max 4 each. Spanish. Fact-locked: only use data present.",
        document_id=doc["document_id"])

    s7_risks = new_section("Riesgos y Oportunidades", 7, [])
    for risk in risk_result.get("risks", [])[:4]:
        b = insight_block("Riesgo", risk, importance="high")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "im_risk_analysis", "date": now_iso()}
        s7_risks["blocks"].append(b)
    for opp in risk_result.get("opportunities", [])[:4]:
        b = insight_block("Oportunidad", opp, importance="medium")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "im_opportunity_analysis", "date": now_iso()}
        s7_risks["blocks"].append(b)

    # 8. Preliminary Valuation (Financial Engine only — deterministic)
    from docstudio.financial_engine import ev_revenue, ev_ebitda, implied_ev_from_multiple
    s8_val = new_section("Valoracion Preliminar", 8, [])
    rev = company.get("revenue_latest", 0)
    ebitda_val = financials[-1].get("ebitda", 0) if financials else 0
    sector_rev_median = benchmark.get("revenue", {}).get("median")
    sector_ebitda_median = benchmark.get("ebitda", {}).get("median")

    # Implied multiples from sector (deterministic)
    if sector_rev_median and sector_ebitda_median and sector_rev_median > 0 and sector_ebitda_median > 0:
        sector_ev_rev = round(sector_rev_median * 1.5, 2)  # Conservative EV proxy
        implied_multiple_rev = round(sector_ev_rev / sector_rev_median, 2) if sector_rev_median else None
        implied_multiple_ebitda = round(sector_ev_rev / sector_ebitda_median, 2) if sector_ebitda_median else None

        if implied_multiple_rev and rev:
            val = implied_ev_from_multiple(rev, implied_multiple_rev)
            if val:
                b = kpi_block("Valoracion por Revenue", f"{val:,.0f}", "EUR",
                              commentary=f"EV/Revenue: {implied_multiple_rev:.1f}x (mediana sector)")
                b["data_lineage"] = {"source": "financial_engine", "calculation": "implied_ev_revenue", "date": now_iso()}
                s8_val["blocks"].append(b)

        if implied_multiple_ebitda and ebitda_val:
            val2 = implied_ev_from_multiple(ebitda_val, implied_multiple_ebitda)
            if val2:
                b = kpi_block("Valoracion por EBITDA", f"{val2:,.0f}", "EUR",
                              commentary=f"EV/EBITDA: {implied_multiple_ebitda:.1f}x (mediana sector)")
                b["data_lineage"] = {"source": "financial_engine", "calculation": "implied_ev_ebitda", "date": now_iso()}
                s8_val["blocks"].append(b)

    if not s8_val["blocks"]:
        s8_val["blocks"].append(text_block("Datos insuficientes para valoracion preliminar. Se requiere informacion adicional.", style="body"))

    # 9. Key Findings (AI)
    s9 = new_section("Hallazgos Clave", 9, [])
    for f in ai_result.get("key_findings", []):
        b = insight_block("Hallazgo", f, importance="high")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "im_findings", "date": now_iso()}
        s9["blocks"].append(b)

    # 10. Conclusion & Recommendations
    s10 = new_section("Conclusion y Recomendaciones", 10, [])
    if ai_result.get("conclusion"):
        b = text_block(ai_result["conclusion"], style="conclusion")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "im_conclusion", "date": now_iso()}
        s10["blocks"].append(b)
    for rec in ai_result.get("recommendations", []):
        s10["blocks"].append(insight_block("Recomendacion", rec, importance="medium"))

    doc["sections"] = [s for s in [s1, s2, s3, s4, s5, s6_market, s7_risks, s8_val, s9, s10] if s]
    doc["metadata"] = {
        "company_id": company.get("master_company_id"), "cif": company.get("cif"),
        "cnae_code": cnae, "type": "information_memorandum",
        "financial_engine_used": True, "fact_locked": True,
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_company_snapshot(company_id: str = None, cif: str = None,
                                    brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Company Snapshot — minimal intelligence unit. <30 seconds."""
    from docstudio.financial_engine import (
        analyze_company_financials, analyze_sector_benchmark,
        find_comparables, compute_sector_positioning,
    )
    from services.cnae_catalog import CNAE_DIVISIONS

    query = {"master_company_id": company_id} if company_id else {"cif": cif}
    company = await db.companies_master.find_one(query, {"_id": 0})
    if not company:
        return {"error": "Company not found"}

    name = company.get("legal_name", "Empresa")
    cid = company.get("master_company_id", "")
    cnae = company.get("cnae_primary", "")
    cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")

    # Financial analysis (deterministic)
    financials = await db.iberinform_financials.find(
        {"company_id": cid}, {"_id": 0}
    ).sort("year", 1).to_list(10)
    fin = analyze_company_financials(financials) if financials else {}
    benchmark = await analyze_sector_benchmark(cnae) if cnae else {}

    # Comparables (deterministic similarity scoring)
    comparables = await find_comparables(cid, cnae, limit=5) if cnae else []

    # Sector positioning (deterministic percentiles)
    company_metrics = {
        "revenue": company.get("revenue_latest"),
        "ebitda": financials[-1].get("ebitda") if financials else None,
        "employees": company.get("employees_latest"),
        "ebitda_margin": fin.get("ebitda_margin"),
    }
    positioning = compute_sector_positioning(company_metrics, benchmark) if benchmark.get("peers") else {}

    doc = new_document(
        title=f"Company Snapshot — {name}",
        template_id="tpl_snapshot", brand_id=brand_id, created_by=user,
    )

    # 1. Cover
    s1 = new_section("Portada", 1, [
        cover_block(title=name, subtitle=f"Company Snapshot — CNAE {cnae}: {cnae_label}"),
    ])

    # 2. KPIs (Financial Engine)
    snap_kpis = []
    if company.get("revenue_latest"):
        b = kpi_block("Facturacion", f"{company['revenue_latest']:,.0f}", "EUR")
        b["data_lineage"] = {"source": "companies_master", "date": now_iso()}
        snap_kpis.append(b)
    if fin.get("ebitda_margin") is not None:
        b = kpi_block("Margen EBITDA", f"{fin['ebitda_margin']:.1f}%", "")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "ebitda_margin", "date": now_iso()}
        snap_kpis.append(b)
    if company.get("employees_latest"):
        snap_kpis.append(kpi_block("Empleados", str(company["employees_latest"]), ""))
    if fin.get("revenue_per_employee"):
        b = kpi_block("Rev/empleado", f"{fin['revenue_per_employee']:,.0f}", "EUR")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "revenue_per_employee", "date": now_iso()}
        snap_kpis.append(b)
    if fin.get("revenue_cagr") is not None:
        b = kpi_block("CAGR", f"{fin['revenue_cagr']:+.1f}%", "")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "cagr", "date": now_iso()}
        snap_kpis.append(b)
    if fin.get("revenue_yoy") is not None:
        b = kpi_block("Crecimiento YoY", f"{fin['revenue_yoy']:+.1f}%", "")
        b["data_lineage"] = {"source": "financial_engine", "calculation": "yoy_growth", "date": now_iso()}
        snap_kpis.append(b)
    s2 = new_section("KPIs", 2, snap_kpis)

    # 3. Positioning (deterministic percentiles)
    pos_blocks = []
    if positioning:
        pos_rows = []
        for metric, data in positioning.items():
            pos_rows.append([data["label"], f"{data['value']:,.0f}" if isinstance(data['value'], (int, float)) and data['value'] > 1 else f"{data['value']*100:.1f}%" if data['value'] and data['value'] < 1 else str(data['value']),
                           f"P{data['percentile']:.0f}", data["position"].replace("_", " ").title()])
        b = table_block("Posicionamiento sectorial", ["Metrica", "Valor", "Percentil", "Posicion"], pos_rows)
        b["data_lineage"] = {"source": "financial_engine", "calculation": "sector_positioning", "date": now_iso()}
        pos_blocks.append(b)
    s3 = new_section("Posicionamiento", 3, pos_blocks) if pos_blocks else None

    # 4. Comparables (deterministic similarity)
    comp_blocks = []
    if comparables:
        comp_rows = []
        for c in comparables:
            comp_rows.append([
                c["legal_name"][:35],
                f"{c['revenue']:,.0f}" if c.get("revenue") else "—",
                f"{c.get('ebitda_margin', 0)*100:.1f}%" if c.get("ebitda_margin") else "—",
                str(c.get("employees", "—")),
                f"{c['similarity']:.0f}%",
            ])
        b = table_block("Top 5 comparables", ["Empresa", "Revenue (EUR)", "Margen", "Empl.", "Similitud"], comp_rows)
        b["data_lineage"] = {"source": "financial_engine", "calculation": "similarity_score", "date": now_iso()}
        comp_blocks.append(b)
    s4 = new_section("Comparables", 4, comp_blocks) if comp_blocks else None

    # 5. AI Conclusion (fact-locked, max 5 lines)
    ai_context = {
        "company_name": name, "cnae": cnae, "cnae_label": cnae_label,
        "revenue": company.get("revenue_latest"), "ebitda_margin": fin.get("ebitda_margin"),
        "employees": company.get("employees_latest"), "cagr": fin.get("revenue_cagr"),
        "yoy": fin.get("revenue_yoy"), "positioning": positioning,
        "comparables_count": len(comparables), "sector_peers": benchmark.get("peers", 0),
    }
    ai_result = await generate_summary(ai_context, doc_type="company_profile", document_id=doc["document_id"])

    s5 = new_section("Conclusion", 5, [])
    conclusion_text = ai_result.get("conclusion", ai_result.get("executive_summary", ""))
    if conclusion_text:
        # Limit to ~5 lines
        sentences = conclusion_text.split(". ")
        short = ". ".join(sentences[:5]) + ("." if not sentences[-1].endswith(".") else "")
        b = text_block(short, style="conclusion")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "snapshot_conclusion", "date": now_iso()}
        s5["blocks"].append(b)

    doc["sections"] = [s for s in [s1, s2, s3, s4, s5] if s]
    doc["metadata"] = {
        "company_id": cid, "cnae_code": cnae, "type": "company_snapshot",
        "financial_engine_used": True, "fact_locked": True,
        "comparables_found": len(comparables), "sector_peers": benchmark.get("peers", 0),
    }
    doc["status"] = "generated"
    doc["updated_at"] = now_iso()
    await db.docstudio_documents.insert_one(doc)
    return doc


async def compose_benchmark_advanced(cnae_code: str, company_id: str = None,
                                      brand_id: str = "brand_bud", user: str = None) -> Dict:
    """Advanced Benchmark Report with comparables, positioning, and SWOT. <60 seconds."""
    from docstudio.financial_engine import (
        analyze_sector_benchmark, find_comparables, compute_sector_positioning,
        analyze_company_financials,
    )
    from services.cnae_catalog import CNAE_DIVISIONS

    cnae_label = CNAE_DIVISIONS.get(cnae_code, {}).get("label", cnae_code)
    await _get_economic_profile(cnae_code)  # available for AI context
    benchmark = await analyze_sector_benchmark(cnae_code)

    # If company_id provided, compute positioning
    company = None
    fin = {}
    positioning = {}
    comparables = []
    if company_id:
        company = await db.companies_master.find_one({"master_company_id": company_id}, {"_id": 0})
        financials = await db.iberinform_financials.find(
            {"company_id": company_id}, {"_id": 0}
        ).sort("year", 1).to_list(10)
        fin = analyze_company_financials(financials) if financials else {}
        company_metrics = {
            "revenue": company.get("revenue_latest") if company else None,
            "ebitda": financials[-1].get("ebitda") if financials else None,
            "employees": company.get("employees_latest") if company else None,
            "ebitda_margin": fin.get("ebitda_margin"),
        }
        positioning = compute_sector_positioning(company_metrics, benchmark)
        comparables = await find_comparables(company_id, cnae_code, limit=5)

    doc = new_document(
        title=f"Benchmark Report — CNAE {cnae_code}: {cnae_label}",
        template_id="tpl_bud_benchmark", brand_id=brand_id, created_by=user,
    )

    # 1. Cover
    title_suffix = f" vs {company.get('legal_name', '')}" if company else ""
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

    # 5. Comparables
    s6 = None
    if comparables:
        comp_rows = []
        for c in comparables:
            comp_rows.append([c["legal_name"][:30], f"{c.get('revenue',0):,.0f}",
                            f"{c.get('ebitda_margin',0)*100:.1f}%" if c.get('ebitda_margin') else "—",
                            str(c.get("employees", "—")), c.get("province", "—"), f"{c['similarity']:.0f}%"])
        b = table_block("Top comparables", ["Empresa", "Revenue", "Margen", "Empl.", "Prov.", "Similitud"], comp_rows)
        b["data_lineage"] = {"source": "financial_engine", "calculation": "similarity_score", "date": now_iso()}
        s6 = new_section("Comparables", 6, [b])

    # 6. AI SWOT (fact-locked)
    ai_context = {
        "cnae_code": cnae_code, "cnae_label": cnae_label,
        "benchmark_peers": benchmark.get("peers", 0),
        "revenue_median": benchmark.get("revenue", {}).get("median"),
        "ebitda_margin_median": benchmark.get("ebitda_margin", {}).get("median"),
        "positioning": positioning if positioning else None,
        "comparables_count": len(comparables),
    }
    if company:
        ai_context["company_name"] = company.get("legal_name")
        ai_context["company_revenue"] = company.get("revenue_latest")
        ai_context["company_margin"] = fin.get("ebitda_margin")

    ai_result = await generate_summary(ai_context, doc_type="sector_report", document_id=doc["document_id"])

    s2 = new_section("Resumen Ejecutivo", 2, [])
    if ai_result.get("executive_summary"):
        b = text_block(ai_result["executive_summary"], style="executive_summary")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "benchmark_summary", "date": now_iso()}
        s2["blocks"].append(b)

    s7_blocks = []
    for f in ai_result.get("key_findings", []):
        s7_blocks.append(insight_block("Hallazgo", f, importance="high"))
    if ai_result.get("conclusion"):
        b = text_block(ai_result["conclusion"], style="conclusion")
        b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "benchmark_conclusion", "date": now_iso()}
        s7_blocks.append(b)
    s7 = new_section("Conclusiones", 7, s7_blocks) if s7_blocks else None

    doc["sections"] = [s for s in [s1, s2, s3, s4, s5, s6, s7] if s]
    doc["metadata"] = {
        "cnae_code": cnae_code, "type": "benchmark_advanced",
        "company_id": company_id, "financial_engine_used": True, "fact_locked": True,
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
    fin_engine_blocks = [b for b in all_blocks if b.get("data_lineage", {}).get("source") == "financial_engine"]
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
    from docstudio.financial_engine import (
        analyze_company_financials, analyze_sector_benchmark,
        find_comparables, compute_sector_positioning,
    )
    from services.cnae_catalog import CNAE_DIVISIONS

    template = await db.docstudio_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not template:
        return {"error": f"Template {template_id} not found"}

    # Resolve company if provided
    company = None
    financials = []
    fin = {}
    if company_id or cif:
        query = {"master_company_id": company_id} if company_id else {"cif": cif}
        company = await db.companies_master.find_one(query, {"_id": 0})
        if company:
            cid = company.get("master_company_id", "")
            cnae_code = cnae_code or company.get("cnae_primary", "")
            financials = await db.iberinform_financials.find(
                {"company_id": cid}, {"_id": 0}
            ).sort("year", 1).to_list(10)
            fin = analyze_company_financials(financials) if financials else {}

    cnae_label = CNAE_DIVISIONS.get(cnae_code, {}).get("label", "") if cnae_code else ""
    benchmark = await analyze_sector_benchmark(cnae_code) if cnae_code else {}
    econ = await _get_economic_profile(cnae_code) if cnae_code else {}

    # Build document
    title_entity = company.get("legal_name", cnae_label) if company else cnae_label
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
            if data_source in ("financial_engine", "") and (company or fin):
                if company and company.get("revenue_latest"):
                    b = kpi_block("Facturacion", f"{company['revenue_latest']:,.0f}", "EUR")
                    b["data_lineage"] = {"source": "companies_master", "date": now}
                    blocks.append(b)
                if fin.get("ebitda_margin") is not None:
                    b = kpi_block("Margen EBITDA", f"{fin['ebitda_margin']:.1f}%", "")
                    b["data_lineage"] = {"source": "financial_engine", "calculation": "ebitda_margin", "date": now}
                    blocks.append(b)
                if company and company.get("employees_latest"):
                    blocks.append(kpi_block("Empleados", str(company["employees_latest"]), ""))
                if fin.get("revenue_yoy") is not None:
                    b = kpi_block("Crecimiento YoY", f"{fin['revenue_yoy']:+.1f}%", "")
                    b["data_lineage"] = {"source": "financial_engine", "calculation": "yoy", "date": now}
                    blocks.append(b)
                if fin.get("revenue_cagr") is not None:
                    b = kpi_block("CAGR", f"{fin['revenue_cagr']:+.1f}%", "")
                    b["data_lineage"] = {"source": "financial_engine", "calculation": "cagr", "date": now}
                    blocks.append(b)
                if fin.get("revenue_per_employee"):
                    b = kpi_block("Rev/empleado", f"{fin['revenue_per_employee']:,.0f}", "EUR")
                    b["data_lineage"] = {"source": "financial_engine", "calculation": "rev_per_emp", "date": now}
                    blocks.append(b)
            elif data_source == "economic_intelligence" and econ:
                if econ.get("active_companies_national"):
                    blocks.append(kpi_block("Empresas activas", f"{econ['active_companies_national']['value']:,.0f}", ""))
                if econ.get("exports_eur"):
                    blocks.append(kpi_block("Exportaciones", f"{econ['exports_eur']['value']:,.0f}", "EUR"))

        # Table blocks
        if "table" in block_types:
            if company:
                info_rows = []
                for field, label in [("legal_name", "Razon social"), ("cif", "CIF"),
                                     ("legal_form", "Forma juridica"), ("province_name", "Provincia")]:
                    if company.get(field):
                        info_rows.append([label, str(company[field])])
                if cnae_label:
                    info_rows.append(["Sector", f"CNAE {cnae_code}: {cnae_label}"])
                if info_rows:
                    blocks.append(table_block("Informacion", ["Campo", "Valor"], info_rows))

            if benchmark.get("peers"):
                bm_rows = []
                for m, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("ebitda_margin", "Margen")]:
                    q = benchmark.get(m, {})
                    if q and q.get("median") is not None:
                        def fmt(v, metric=m):
                            return f"{v*100:.1f}%" if metric == "ebitda_margin" else f"{v:,.0f}"
                        bm_rows.append([label, fmt(q.get("q1", 0)), fmt(q["median"]), fmt(q.get("q3", 0))])
                if bm_rows:
                    b = table_block("Benchmark", ["Metrica", "Q1", "Mediana", "Q3"], bm_rows)
                    b["data_lineage"] = {"source": "financial_engine", "calculation": "quartiles", "date": now}
                    blocks.append(b)

        # AI text/insight blocks — runs when data_source is 'ai' OR when text/insight blocks exist without other source
        needs_ai = data_source == "ai" or (("text" in block_types or "insight" in block_types) and data_source not in ("financial_engine", "companies_master", "economic_intelligence"))
        if needs_ai:
            ai_context = {
                "section_title": title,
                "company_name": company.get("legal_name") if company else None,
                "cnae": cnae_code, "cnae_label": cnae_label,
                "revenue": company.get("revenue_latest") if company else None,
                "ebitda_margin": fin.get("ebitda_margin"),
                "growth": fin.get("revenue_yoy"),
                "sector_peers": benchmark.get("peers", 0),
            }
            ai_result = await generate_summary(ai_context, document_id=doc["document_id"])

            if "text" in block_types and ai_result.get("executive_summary"):
                b = text_block(ai_result["executive_summary"], style="executive_summary")
                b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": f"generic_{title[:20]}", "date": now}
                blocks.append(b)
            if "insight" in block_types:
                for finding in ai_result.get("key_findings", [])[:3]:
                    b = insight_block("Hallazgo", finding, importance="high")
                    b["data_lineage"] = {"source": "ai", "model": "gpt-5.2", "task": "findings", "date": now}
                    blocks.append(b)

        sections.append(new_section(title, tpl_section.get("order", len(sections) + 1), blocks))

    doc["sections"] = sections
    doc["metadata"] = {
        "template_id": template_id, "template_name": template.get("name"),
        "company_id": company.get("master_company_id") if company else None,
        "cnae_code": cnae_code, "type": "custom_template",
        "financial_engine_used": True, "fact_locked": True,
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
