"""Template Library — Predefined document structures with versioning.

Templates define structure, blocks, order, and behavior.
Each template specifies which AI models to use for analysis vs narrative.
"""

from typing import Dict, List
from models import new_id, now_iso


TEMPLATES = {
    "sector_report": {
        "template_id": "tpl_sector_report",
        "name": "Informe Sectorial",
        "description": "Informe de inteligencia sectorial basado en CNAE con datos de Economic Intelligence, Sector Intelligence y fuentes oficiales.",
        "version": 1,
        "category": "intelligence",
        "analysis_model": "openai",
        "narrative_model": "openai",
        "sections": [
            {"title": "Portada", "order": 1, "block_types": ["cover"]},
            {"title": "Resumen Ejecutivo", "order": 2, "block_types": ["text", "insight"]},
            {"title": "KPIs del Sector", "order": 3, "block_types": ["kpi"]},
            {"title": "Evolucion del Mercado", "order": 4, "block_types": ["chart", "text"]},
            {"title": "Actividad Empresarial", "order": 5, "block_types": ["table", "kpi"]},
            {"title": "Comercio Exterior", "order": 6, "block_types": ["kpi", "chart"]},
            {"title": "Contratacion Publica", "order": 7, "block_types": ["kpi", "table"]},
            {"title": "Tendencias y Senales", "order": 8, "block_types": ["insight"]},
            {"title": "Conclusiones", "order": 9, "block_types": ["text"]},
        ],
        "data_sources": ["economic_intelligence", "sector_intelligence", "datacomex", "procurement", "borme"],
    },
    "company_profile": {
        "template_id": "tpl_company_profile",
        "name": "Ficha de Compania",
        "description": "Perfil completo de empresa con datos financieros, posicionamiento sectorial y actividad corporativa.",
        "version": 1,
        "category": "company",
        "analysis_model": "openai",
        "narrative_model": "openai",
        "sections": [
            {"title": "Portada", "order": 1, "block_types": ["cover"]},
            {"title": "Resumen", "order": 2, "block_types": ["text", "insight"]},
            {"title": "Datos Generales", "order": 3, "block_types": ["kpi", "table"]},
            {"title": "Evolucion Financiera", "order": 4, "block_types": ["kpi", "chart"]},
            {"title": "Posicionamiento Sectorial", "order": 5, "block_types": ["text", "chart"]},
            {"title": "Actividad Corporativa", "order": 6, "block_types": ["table"]},
            {"title": "Conclusion", "order": 7, "block_types": ["text"]},
        ],
        "data_sources": ["companies_master", "economic_intelligence", "borme", "procurement"],
    },
    "bud_benchmark": {
        "template_id": "tpl_bud_benchmark",
        "name": "BUD Benchmark Report",
        "description": "Benchmark sectorial BUD Advisors: cuartiles, percentiles, ranking, comparables y posicionamiento. Incluye Financial Engine determinista.",
        "version": 1,
        "category": "intelligence",
        "provider": "BUD Advisors",
        "analysis_model": "openai",
        "narrative_model": "openai",
        "sections": [
            {"title": "Portada", "order": 1, "block_types": ["cover"]},
            {"title": "Resumen Ejecutivo", "order": 2, "block_types": ["text"]},
            {"title": "Benchmark del Sector", "order": 3, "block_types": ["kpi"]},
            {"title": "Distribucion Estadistica", "order": 4, "block_types": ["table"]},
            {"title": "Conclusiones", "order": 5, "block_types": ["text", "insight"]},
        ],
        "data_sources": ["financial_engine", "economic_intelligence"],
    },
    "bud_teaser": {
        "template_id": "tpl_bud_teaser",
        "name": "BUD Teaser",
        "description": "Teaser confidencial BUD Advisors para presentacion de oportunidad de inversion a potenciales compradores.",
        "version": 1,
        "category": "mna",
        "provider": "BUD Advisors",
        "analysis_model": "openai",
        "narrative_model": "openai",
        "sections": [
            {"title": "Portada", "order": 1, "block_types": ["cover"]},
            {"title": "Metricas Clave", "order": 2, "block_types": ["kpi"]},
            {"title": "Descripcion de la Oportunidad", "order": 3, "block_types": ["text"]},
        ],
        "data_sources": ["companies_master", "financial_engine"],
    },
    "bud_im": {
        "template_id": "tpl_bud_im",
        "name": "BUD Information Memorandum",
        "description": "Information Memorandum completo BUD Advisors: descripcion compania, analisis financiero, benchmark sectorial, hallazgos y recomendaciones.",
        "version": 1,
        "category": "mna",
        "provider": "BUD Advisors",
        "analysis_model": "openai",
        "narrative_model": "openai",
        "sections": [
            {"title": "Portada", "order": 1, "block_types": ["cover"]},
            {"title": "Resumen Ejecutivo", "order": 2, "block_types": ["text"]},
            {"title": "Descripcion de la Compania", "order": 3, "block_types": ["table"]},
            {"title": "Analisis Financiero", "order": 4, "block_types": ["kpi", "table"]},
            {"title": "Posicionamiento Sectorial", "order": 5, "block_types": ["table", "kpi"]},
            {"title": "Hallazgos Clave", "order": 6, "block_types": ["insight"]},
            {"title": "Conclusion y Recomendaciones", "order": 7, "block_types": ["text", "insight"]},
        ],
        "data_sources": ["companies_master", "financial_engine", "economic_intelligence", "sector_intelligence"],
    },
}


BRANDS = {
    "bud_advisors": {
        "brand_id": "brand_bud",
        "name": "BUD Advisors",
        "primary_color": "#1a56db",
        "secondary_color": "#0e1629",
        "accent_color": "#3b82f6",
        "font_family": "Inter, system-ui, sans-serif",
        "footer_text": "BUD Advisors — Confidencial",
        "language": "es",
    },
    "valuo": {
        "brand_id": "brand_valuo",
        "name": "Valuo.pro",
        "primary_color": "#059669",
        "secondary_color": "#064e3b",
        "accent_color": "#10b981",
        "font_family": "Inter, system-ui, sans-serif",
        "footer_text": "Valuo.pro — Documento generado automaticamente",
        "language": "es",
    },
    "arroba": {
        "brand_id": "brand_arroba",
        "name": "arroba.com",
        "primary_color": "#7c3aed",
        "secondary_color": "#1e1b4b",
        "accent_color": "#8b5cf6",
        "font_family": "Inter, system-ui, sans-serif",
        "footer_text": "arroba.com — Inteligencia economica",
        "language": "es",
    },
    "custom": {
        "brand_id": "brand_custom",
        "name": "Marca personalizada",
        "primary_color": "#374151",
        "secondary_color": "#111827",
        "accent_color": "#6b7280",
        "font_family": "Inter, system-ui, sans-serif",
        "footer_text": "",
        "language": "es",
    },
}


async def seed_templates_and_brands(db):
    """Seed templates and brands into MongoDB."""
    now = now_iso()

    for key, tpl in TEMPLATES.items():
        await db.docstudio_templates.update_one(
            {"template_id": tpl["template_id"]},
            {"$set": {**tpl, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    for key, brand in BRANDS.items():
        await db.docstudio_brands.update_one(
            {"brand_id": brand["brand_id"]},
            {"$set": {**brand, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    return {"templates": len(TEMPLATES), "brands": len(BRANDS)}
