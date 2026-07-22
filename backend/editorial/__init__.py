"""Editorial Intelligence Agent — Pydantic models."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from models import new_id, now_iso


# ── Source ──
class SourceCreate(BaseModel):
    name: str
    url: str
    rss_url: Optional[str] = None
    html_url: Optional[str] = None
    domain: Optional[str] = None
    source_type: str = "rss"
    source_group: str = "marketing_advertising_media"
    ingestion_mode: str = "rss_preferred_html_fallback"  # rss_only, html_only, rss_preferred_html_fallback
    country: str = "ES"
    language: str = "es"
    crawl_frequency: str = "12h"
    target_sections: List[str] = []
    priority: int = 5
    notes: Optional[str] = None

class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[str] = None
    crawl_frequency: Optional[str] = None
    target_sections: Optional[List[str]] = None
    priority: Optional[int] = None
    notes: Optional[str] = None

# ── Editorial Item ──
class ItemUpdate(BaseModel):
    title_clean: Optional[str] = None
    section_primary: Optional[str] = None
    section_secondary: Optional[List[str]] = None
    editorial_category: Optional[str] = None
    editorial_bullet: Optional[str] = None
    anchor_text: Optional[str] = None
    status: Optional[str] = None

# ── Digest ──
class DigestCreate(BaseModel):
    week_label: str  # e.g. "W16 2026"
    title: str
    intro_text: Optional[str] = None

class DigestUpdate(BaseModel):
    title: Optional[str] = None
    intro_text: Optional[str] = None
    selected_item_ids: Optional[List[str]] = None
    section_order: Optional[List[str]] = None
    manual_blocks: Optional[Dict[str, str]] = None  # e.g. {"palabra_de_dani": "text...", "mirada_control": "text..."}

# ── Constants ──
EDITORIAL_SECTIONS = [
    "cifras_resultados",
    "indies",
    "noticias_semana",
    "ma_vc_pe_alianzas",
    "podcasts_entrevistas",
    "lecturas_interesantes",
    "mirada_control",
    "palabra_de_dani",
    "nombramientos_reconocimientos",
    "eventos",
]

SECTION_LABELS = {
    "cifras_resultados": "Cifras y Resultados",
    "indies": "Indies",
    "noticias_semana": "Noticias de la semana",
    "ma_vc_pe_alianzas": "Actividad de M&A, VC, PE y alianzas estrategicas",
    "podcasts_entrevistas": "Podcasts y entrevistas",
    "lecturas_interesantes": "Lecturas interesantes",
    "mirada_control": "La mirada de Control",
    "palabra_de_dani": "Palabra de Dani",
    "nombramientos_reconocimientos": "Nombramientos y reconocimientos",
    "eventos": "Eventos nacionales e internacionales",
}

SECTION_EMOJIS = {
    "cifras_resultados": "💰💹",
    "indies": "🎸✨",
    "noticias_semana": "💡",
    "ma_vc_pe_alianzas": "🚀",
    "podcasts_entrevistas": "🎧",
    "lecturas_interesantes": "🤓",
    "mirada_control": "🧭",
    "palabra_de_dani": "💬",
    "nombramientos_reconocimientos": "🏅👤",
    "eventos": "🕰🎉🇪🇸",
}

MANUAL_SECTIONS = {"mirada_control", "palabra_de_dani"}

ADCEO_DEFAULT_INTRO = """Bienvenid@ a AdCeo,

El resumen semanal para entender, con criterio y contexto, que esta pasando en el ecosistema espanol de madtech: marketing, publicidad y tecnologia.

Soy Daniel Casal, managing partner en BUD Advisors, firma especializada en M&A para companias de marketing digital, publicidad y tecnologia publicitaria. Trabajo a diario analizando agencias, acompanando procesos de compra y venta y ayudando a equipos directivos a tomar mejores decisiones de crecimiento.

En AdCeo comparto datos, operaciones, tendencias y reflexiones pensadas para quienes lideran, invierten o construyen companias en esta industria.

Si quieres ponerte en contacto conmigo, puedes escribirme a daniel@wearebudadvisors.com

Gracias por leerme.

Espero que esta edicion te aporte contexto, perspectiva y alguna buena pregunta para la semana."""

CONTENT_TYPES = ["article", "press_release", "podcast_episode", "event", "report", "interview", "newsletter"]
SIGNAL_TYPES = ["result", "acquisition", "appointment", "launch", "award", "partnership", "fundraise", "event", "expansion", "restructuring", "other"]
ITEM_STATUSES = ["new", "candidate", "reviewed", "approved", "discarded", "added_to_digest", "published"]


SOURCE_GROUPS = {
    "marketing_advertising_media": "Marketing, Advertising & Media",
    "technology_startups_adtech": "Technology, Startups & AdTech",
    "ma_pe_vc_corporate_finance": "M&A, PE, VC & Corporate Finance",
    "newsletters_substack_independent_analysis": "Newsletters & Independent Analysis",
    "events_sources": "Events & Conferences",
    "awards_design_creativity": "Awards, Design & Creativity",
    "needs_review": "Needs Review",
}
