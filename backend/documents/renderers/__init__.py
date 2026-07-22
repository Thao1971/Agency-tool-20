"""PDF Renderer — WeasyPrint pipeline with corporate HTML/CSS templates."""

import io
import os
import logging
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates_html"


def _is_dark_color(hex_color: str) -> bool:
    """Determine if a hex color is dark (for choosing logo variant)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return True
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5


def render_pdf(html_content: str, css_content: str = "") -> bytes:
    from weasyprint import HTML, CSS
    stylesheets = []
    if css_content:
        stylesheets.append(CSS(string=css_content))
    doc = HTML(string=html_content)
    return doc.write_pdf(stylesheets=stylesheets)


def load_template(template_name: str = "agency_report") -> tuple:
    """Load HTML and CSS from template files."""
    html_path = TEMPLATES_DIR / f"{template_name}.html"
    css_path = TEMPLATES_DIR / f"{template_name}.css"
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    return html, css


def build_agency_report(data: Dict, blocks: Dict, overrides: Dict, brand: Optional[Dict] = None) -> tuple:
    """Build final HTML and CSS for an agency report from real data."""
    html_tpl, css_tpl = load_template("agency_report")

    # Merge: overrides > blocks > data
    merged = {}
    for source in [data, blocks, overrides]:
        for k, v in (source or {}).items():
            if isinstance(v, dict) and "content" in v:
                merged[k] = v["content"]
            elif v is not None:
                merged[k] = v

    # Simple replacements
    html = html_tpl
    for key, value in merged.items():
        placeholder = "{{" + key + "}}"
        if placeholder not in html:
            continue

        if isinstance(value, list):
            # Render as styled list or tag grid depending on context
            if key in ("tags", "tags_list"):
                items = "".join(f'<span>{item}</span>' for item in value[:30])
                html = html.replace(placeholder, items)
            elif key in ("main_clients", "clients_list"):
                items = "".join(f'<span>{item}</span>' for item in value[:25])
                html = html.replace(placeholder, items)
            else:
                items = "".join(f"<li>{item}</li>" for item in value)
                html = html.replace(placeholder, f"<ul>{items}</ul>")
        elif isinstance(value, bool):
            html = html.replace(placeholder, "Yes" if value else "No")
        elif isinstance(value, (int, float)):
            html = html.replace(placeholder, str(value))
        elif isinstance(value, str):
            # Wrap plain text in paragraphs if it has newlines
            if "\n" in value:
                paras = "".join(f"<p>{p.strip()}</p>" for p in value.split("\n") if p.strip())
                html = html.replace(placeholder, paras)
            else:
                html = html.replace(placeholder, value)

    # Clean up remaining content placeholders first
    import re

    # Generate CSS with design tokens
    from documents.design_system import generate_css_tokens, get_brand_or_default
    brand_id = None
    if brand and isinstance(brand, dict):
        brand_id = brand.get("brand_id")
    brand_data = get_brand_or_default(brand_id)
    tokens_css = generate_css_tokens(brand_id, brand_data)

    # Inject brand identifiers into HTML
    logo_text = brand_data.get("logo_text", "BUD")
    brand_name = brand_data.get("name", "BUD Advisors")

    # Determine logo URL — prefer light logo on dark covers, dark logo on light covers
    cover_bg = brand_data.get("tokens", {}).get("cover", {}).get("bg", "#000000")
    is_dark_cover = _is_dark_color(cover_bg)
    logo_url = brand_data.get("logo_light") if is_dark_cover else brand_data.get("logo_dark")
    if not logo_url:
        logo_url = brand_data.get("logo_light") or brand_data.get("logo_dark") or ""

    html = html.replace("{{brand_logo_text}}", logo_text)
    html = html.replace("{{brand_name_upper}}", brand_name.upper())
    html = html.replace("{{logo_url}}", logo_url)

    # Clean remaining placeholders
    html = re.sub(r'\{\{[a-z_]+\}\}', '', html)

    # Combine: tokens + template CSS + brand-specific overrides
    css = tokens_css + "\n\n" + css_tpl

    # Arroba: The Editorial Pulse — signature overrides
    if brand_id == "brand_arroba":
        css += """
/* Editorial Pulse — Arroba brand-specific overrides */
/* Signature gradient cover (primary → primary_container at 135deg) */
.cover { background: linear-gradient(135deg, #990417 0%, #bc262c 100%) !important; }
/* Tonal layering — no hard borders, ghost borders only */
.section-header, .page-header { border-bottom-color: rgba(195,198,203,0.10) !important; }
.info-row { border-bottom-color: rgba(195,198,203,0.08) !important; }
.highlight-items li { border-bottom-color: rgba(195,198,203,0.08) !important; }
/* KPI cards — white card on warm surface (editorial lift) */
.kpi-card { border: none !important; box-shadow: 0 12px 40px rgba(27,28,28,0.06); }
/* Tags — full roundedness, lowercase */
.tags-grid span { border-radius: 9999px !important; text-transform: lowercase !important; }
/* Clients — full roundedness */
.clients-grid span { border-radius: 9999px !important; border: none !important; }
/* Section separators — crimson gradient */
.section-sep { background: linear-gradient(135deg, #990417 0%, #bc262c 100%) !important; }
.section-sep-title { color: #FFFFFF !important; }
/* Cover line — white on crimson */
.cover-line { background: rgba(255,255,255,0.4) !important; }
/* Arroba logo — blend white bg on crimson cover */
.cover-logo-img { mix-blend-mode: multiply !important; background: transparent !important; }
/* Closing — warm surface */
.closing-page { background: var(--bg-primary) !important; }
.closing-line { background: #990417 !important; }
/* Accent line in disclaimer */
.disclaimer-box { background: #FFFFFF !important; }
/* Typography — tighter letter-spacing for display */
.cover-title { letter-spacing: -0.02em !important; }
.section-sep-title { letter-spacing: -0.02em !important; }
.section-heading { letter-spacing: -0.01em !important; }
"""

    # CIS: The Editorial Ledger — signature overrides
    if brand_id == "brand_cis":
        css += """
/* Editorial Ledger — CIS brand-specific overrides */
/* Signature metallic gradient cover (primary → primary-container at 135deg) */
.cover { background: linear-gradient(135deg, #6D5E00 0%, #E1C422 100%) !important; }
/* Cover line — gold on gradient */
.cover-line { background: rgba(255,255,255,0.35) !important; }
/* Tonal layering — ghost borders only, no hard lines */
.section-header, .page-header { border-bottom-color: rgba(195,198,203,0.10) !important; }
.info-row { border-bottom-color: rgba(195,198,203,0.08) !important; }
.highlight-items li { border-bottom-color: rgba(195,198,203,0.06) !important; }
/* Section separators — metallic gold gradient */
.section-sep { background: linear-gradient(135deg, #6D5E00 0%, #E1C422 100%) !important; }
.section-sep-num { color: rgba(255,255,255,0.7) !important; }
.section-sep-title { color: #FFFFFF !important; }
/* KPI "Signature Cards" — white cards with ambient shadow, gold values */
.kpi-card { border: none !important; box-shadow: 0 12px 40px rgba(27,28,28,0.04); border-radius: 0.375rem; }
/* Tags — gold fill, medium roundedness */
.tags-grid span { border-radius: 0.25rem !important; }
/* Clients — surface-container-low, ghost borders */
.clients-grid span { border: none !important; border-radius: 0.25rem !important; }
/* Disclaimer — elevated white card with gold border */
.disclaimer-box { background: #FFFFFF !important; box-shadow: 0 8px 30px rgba(27,28,28,0.03); }
/* Closing — warm canvas */
.closing-page { background: var(--bg-primary) !important; }
.closing-line { background: #E1C422 !important; }
/* Typography — Playfair Display for editorial anchors */
.cover-title { font-family: 'Playfair Display', Georgia, serif !important; letter-spacing: -0.01em !important; }
.section-sep-title { font-family: 'Playfair Display', Georgia, serif !important; }
.section-heading { font-family: 'Playfair Display', Georgia, serif !important; }
/* Body text — softer, never pure black */
.body-text { color: #44474A !important; }
/* Subsection headings — deep gold, Inter (not Playfair) */
.subsection-heading { color: #6D5E00 !important; font-family: var(--font-body) !important; }
/* Table — near-black header (never #000), ghost row borders */
table td { border-bottom-color: rgba(195,198,203,0.08) !important; }
"""

    # Inject timestamp
    html = html.replace("{{generated_at}}", datetime.utcnow().strftime("%B %Y"))

    return html, css


def build_html_from_manifest(manifest: Dict, template_html: str, template_css: str,
                              brand: Optional[Dict] = None) -> tuple:
    """Build final HTML and CSS from manifest. Uses real template if available."""
    data = manifest.get("data_payload", {})
    blocks = manifest.get("generated_blocks", {})
    overrides = manifest.get("manual_overrides", {})

    # If template_html is None/empty, use the real file template
    if not template_html:
        return build_agency_report(data, blocks, overrides, brand)

    # Otherwise use the provided template (custom)
    html = template_html
    css = template_css or ""

    merged = {**data}
    for k, v in blocks.items():
        merged[k] = v.get("content", v) if isinstance(v, dict) else v
    for k, v in overrides.items():
        merged[k] = v

    for key, value in merged.items():
        placeholder = "{{" + key + "}}"
        if isinstance(value, str):
            html = html.replace(placeholder, value)
        elif isinstance(value, list):
            items = "".join(f"<li>{item}</li>" for item in value)
            html = html.replace(placeholder, f"<ul>{items}</ul>")

    if brand:
        css = css.replace("{{primary_color}}", brand.get("primary_color", "#1a1a2e"))
        css = css.replace("{{secondary_color}}", brand.get("secondary_color", "#3b82f6"))

    import re
    html = re.sub(r'\{\{[a-z_]+\}\}', '', html)
    html = html.replace("{{generated_at}}", datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC"))

    return html, css
