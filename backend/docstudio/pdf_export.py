"""PDF Export Engine — Renders documents to PDF via HTML+CSS+WeasyPrint.

Controlled by templates and brand — AI never decides layout.
Each block type has its own HTML renderer.
"""

import logging
from typing import Dict
from io import BytesIO

logger = logging.getLogger(__name__)


def render_document_html(doc: Dict, brand: Dict) -> str:
    """Render a full document to HTML string."""
    primary = brand.get("primary_color", "#1a56db")
    secondary = brand.get("secondary_color", "#0e1629")
    accent = brand.get("accent_color", "#3b82f6")
    font = brand.get("font_family", "Inter, system-ui, sans-serif")

    sections_html = ""
    for section in doc.get("sections", []):
        sections_html += _render_section(section, brand)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: {font}; color: #1f2937; background: #fff; font-size: 11pt; line-height: 1.6; }}
.page {{ page-break-after: always; padding: 48px; min-height: 100vh; position: relative; }}
.page:last-child {{ page-break-after: auto; }}
.cover {{ background: {secondary}; color: white; display: flex; flex-direction: column; justify-content: center; align-items: flex-start; padding: 80px 64px; }}
.cover h1 {{ font-size: 32pt; font-weight: 700; margin-bottom: 12px; color: white; }}
.cover h2 {{ font-size: 14pt; font-weight: 400; color: {accent}; opacity: 0.9; }}
.cover .brand-line {{ margin-top: 48px; padding-top: 24px; border-top: 2px solid {accent}; font-size: 10pt; color: rgba(255,255,255,0.6); }}
.section-title {{ font-size: 16pt; font-weight: 700; color: {primary}; margin-bottom: 20px; padding-bottom: 8px; border-bottom: 2px solid {accent}; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }}
.kpi-card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
.kpi-card .label {{ font-size: 8pt; text-transform: uppercase; letter-spacing: 0.1em; color: #6b7280; margin-bottom: 4px; }}
.kpi-card .value {{ font-size: 18pt; font-weight: 700; color: {primary}; }}
.kpi-card .unit {{ font-size: 8pt; color: #9ca3af; }}
.kpi-card .variation {{ font-size: 9pt; color: #059669; margin-top: 4px; }}
.kpi-card .commentary {{ font-size: 8pt; color: #6b7280; margin-top: 4px; }}
.text-block {{ margin-bottom: 20px; font-size: 10.5pt; color: #374151; }}
.text-block.executive_summary {{ font-size: 11pt; color: #111827; background: #f0f9ff; border-left: 4px solid {accent}; padding: 16px 20px; border-radius: 4px; }}
.text-block.conclusion {{ font-style: italic; color: #1f2937; }}
.insight-card {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; }}
.insight-card .title {{ font-size: 9pt; font-weight: 600; color: #92400e; margin-bottom: 4px; }}
.insight-card .summary {{ font-size: 10pt; color: #78350f; }}
.insight-card .source {{ font-size: 7pt; color: #b45309; margin-top: 6px; }}
.insight-card.high {{ border-color: #f87171; background: #fef2f2; }}
.insight-card.high .title {{ color: #991b1b; }}
.insight-card.high .summary {{ color: #7f1d1d; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 9pt; }}
table th {{ background: {primary}; color: white; padding: 8px 12px; text-align: left; font-weight: 600; font-size: 8pt; text-transform: uppercase; letter-spacing: 0.05em; }}
table td {{ padding: 8px 12px; border-bottom: 1px solid #e5e7eb; color: #374151; }}
table tr:nth-child(even) td {{ background: #f9fafb; }}
.divider {{ border-top: 1px solid #e5e7eb; margin: 24px 0; }}
.footer {{ position: absolute; bottom: 24px; left: 48px; right: 48px; font-size: 7pt; color: #9ca3af; display: flex; justify-content: space-between; border-top: 1px solid #e5e7eb; padding-top: 8px; }}
.lineage {{ font-size: 6pt; color: #d1d5db; margin-top: 4px; }}
@page {{ size: A4; margin: 0; }}
</style>
</head>
<body>
{sections_html}
</body>
</html>"""


def _render_section(section: Dict, brand: Dict) -> str:
    """Render a section with its blocks."""
    blocks_html = ""
    is_cover = False

    for block in section.get("blocks", []):
        bt = block.get("block_type", "")
        data = block.get("data", {})
        lineage = block.get("data_lineage", {})

        if bt == "cover":
            is_cover = True
            blocks_html += f"""<div class="cover">
                <h1>{data.get('title', '')}</h1>
                <h2>{data.get('subtitle', '')}</h2>
                <div class="brand-line">{brand.get('name', '')} — {brand.get('footer_text', '')}</div>
            </div>"""

        elif bt == "text":
            style = data.get("style", "body")
            blocks_html += f'<div class="text-block {style}">{data.get("content", "")}</div>'

        elif bt == "kpi":
            # KPIs are collected and rendered as grid
            pass  # handled below

        elif bt == "table":
            cols = data.get("columns", [])
            rows = data.get("rows", [])
            ths = "".join(f"<th>{c}</th>" for c in cols)
            trs = ""
            for row in rows:
                tds = "".join(f"<td>{cell}</td>" for cell in row)
                trs += f"<tr>{tds}</tr>"
            blocks_html += f"""<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"""

        elif bt == "insight":
            imp = data.get("importance", "medium")
            blocks_html += f"""<div class="insight-card {imp}">
                <div class="title">{data.get('title', '')}</div>
                <div class="summary">{data.get('summary', '')}</div>
                {'<div class="source">Fuente: ' + data.get('source_reference', '') + '</div>' if data.get('source_reference') else ''}
            </div>"""

        elif bt == "divider":
            blocks_html += '<div class="divider"></div>'

        # Lineage annotation
        if lineage.get("source") and bt != "cover":
            src = lineage.get("source", "")
            model = lineage.get("model", "")
            if src == "ai":
                blocks_html += f'<div class="lineage">Generado por IA ({model}) — {lineage.get("date", "")}</div>'

    # Render KPIs as grid
    kpis = [b for b in section.get("blocks", []) if b.get("block_type") == "kpi"]
    if kpis:
        kpi_html = '<div class="kpi-grid">'
        for k in kpis:
            d = k.get("data", {})
            kpi_html += f"""<div class="kpi-card">
                <div class="label">{d.get('title', '')}</div>
                <div class="value">{d.get('value', '')}</div>
                <div class="unit">{d.get('unit', '')}</div>
                {'<div class="variation">' + str(d.get('variation', '')) + '</div>' if d.get('variation') else ''}
                {'<div class="commentary">' + d.get('commentary', '') + '</div>' if d.get('commentary') else ''}
            </div>"""
        kpi_html += '</div>'
        blocks_html = kpi_html + blocks_html

    if is_cover:
        return f'<div class="page">{blocks_html}</div>'

    footer = brand.get("footer_text", "")
    return f"""<div class="page">
        <h2 class="section-title">{section.get('title', '')}</h2>
        {blocks_html}
        <div class="footer"><span>{footer}</span><span>{section.get('title', '')}</span></div>
    </div>"""


async def export_to_pdf(doc: Dict, brand: Dict) -> bytes:
    """Export document to PDF bytes using WeasyPrint."""
    html = render_document_html(doc, brand)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        return pdf_bytes
    except ImportError:
        logger.warning("WeasyPrint not available, trying Playwright PDF")
        return await _playwright_pdf(html)


async def _playwright_pdf(html: str) -> bytes:
    """Fallback: use Playwright to generate PDF from HTML."""
    from playwright.async_api import async_playwright
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode='w') as f:
        f.write(html)
        html_path = f.name

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"file://{html_path}", wait_until="networkidle")
            pdf_bytes = await page.pdf(format="A4", print_background=True)
            await browser.close()
        return pdf_bytes
    finally:
        os.unlink(html_path)
