"""Document Engine models — Pydantic schemas for templates, projects, jobs, outputs."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from models import new_id, now_iso


# ── Templates ──

class TemplateCreate(BaseModel):
    name: str
    document_type: str = "report"  # report, profile, valuation, pitch
    supported_formats: List[str] = ["pdf"]
    description: Optional[str] = None
    schema_version: str = "1.0"
    allowed_components: List[str] = []
    default_brand_id: Optional[str] = None
    legal_disclaimer: Optional[str] = None
    html_template: Optional[str] = None
    css_template: Optional[str] = None
    sections: List[Dict[str, Any]] = []

class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    supported_formats: Optional[List[str]] = None
    allowed_components: Optional[List[str]] = None
    default_brand_id: Optional[str] = None
    legal_disclaimer: Optional[str] = None
    html_template: Optional[str] = None
    css_template: Optional[str] = None
    sections: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = None


# ── Brand Profiles ──

class BrandProfile(BaseModel):
    brand_id: str = Field(default_factory=new_id)
    name: str
    primary_color: str = "#1a1a2e"
    secondary_color: str = "#3b82f6"
    accent_color: str = "#10b981"
    font_heading: str = "Manrope"
    font_body: str = "IBM Plex Sans"
    logo_asset_id: Optional[str] = None
    legal_entity: Optional[str] = None


# ── Projects ──

class ProjectCreate(BaseModel):
    template_id: str
    template_version: Optional[int] = None
    brand_id: Optional[str] = None
    name: str
    output_format: str = "pdf"
    locale: str = "es"
    source_app: Optional[str] = None  # cis, arroba, manual
    source_entity_type: Optional[str] = None  # company, deal, portfolio
    source_entity_id: Optional[str] = None
    data_payload: Optional[Dict[str, Any]] = None
    manual_overrides: Optional[Dict[str, Any]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    data_payload: Optional[Dict[str, Any]] = None
    manual_overrides: Optional[Dict[str, Any]] = None
    generated_blocks: Optional[Dict[str, Any]] = None


# ── Generation ──

class GenerateRequest(BaseModel):
    project_id: Optional[str] = None
    template_id: Optional[str] = None
    template_version: Optional[int] = None
    brand_id: Optional[str] = None
    output_format: str = "pdf"
    locale: str = "es"
    source_app: Optional[str] = None
    source_entity_type: Optional[str] = None
    source_entity_id: Optional[str] = None
    data_payload: Optional[Dict[str, Any]] = None
    generated_blocks: Optional[Dict[str, Any]] = None
    manual_overrides: Optional[Dict[str, Any]] = None
    callback_url: Optional[str] = None


class AIBlockRequest(BaseModel):
    block_type: str  # executive_summary, strengths, risks, etc.
    context: Dict[str, Any]
    locale: str = "es"
    model: str = "primary"  # primary (GPT-5.2) or secondary (GPT-5-mini)
    max_tokens: int = 500

class AIRewriteRequest(BaseModel):
    text: str
    instruction: str  # shorten, rewrite, formalize, etc.
    locale: str = "es"
    model: str = "secondary"


# ── Document Manifest (canonical) ──

def new_manifest(template_id, template_version, brand_id, output_format, locale,
                 source_app, source_entity_type, source_entity_id,
                 sections, legal_footer, assets, generated_blocks, manual_overrides):
    return {
        "template_id": template_id,
        "template_version": template_version,
        "brand_id": brand_id,
        "output_format": output_format,
        "locale": locale,
        "source_app": source_app,
        "source_entity_type": source_entity_type,
        "source_entity_id": source_entity_id,
        "sections": sections,
        "legal_footer": legal_footer,
        "assets": assets,
        "generated_blocks": generated_blocks,
        "manual_overrides": manual_overrides
    }
