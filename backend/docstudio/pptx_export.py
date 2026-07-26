"""PPTX Export Engine — Generates fully editable PowerPoint presentations.

Every element is native PPTX (no images of slides). Tables, charts, text — all editable.
Brand colors, fonts, and layout controlled by brand config.
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from io import BytesIO
from typing import Dict, List


def _hex_to_rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip('#')
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


async def export_to_pptx(doc: Dict, brand: Dict) -> bytes:
    """Export a PPTX. Para documentos tipo presentación (infomemo, teaser, etc.) rasteriza cada
    diapositiva del MISMO renderizador de la vista previa (`render_html`, con todos los gráficos)
    vía Chromium y la inserta a pantalla completa en un PPTX 16:9 — así el PPT respeta EXACTAMENTE
    el layout generado. Los documentos en 'flujo' usan el generador PPTX nativo clásico."""
    try:
        from docstudio.pdf_export import _layout_is_slides, _pdfize_slides_html
        if _layout_is_slides(doc):
            from docstudio.html_render import render_html
            html = _pdfize_slides_html(render_html(doc, brand))
            return await _slides_to_pptx(html)
    except Exception as e:  # ante cualquier fallo, cae al PPTX nativo (no romper la descarga)
        import logging; logging.getLogger(__name__).warning("PPTX slides render failed: %s", e)
    return _native_pptx(doc, brand)


async def _slides_to_pptx(html: str) -> bytes:
    """Captura cada `.slide` (1280×720) con Chromium y monta un PPTX 16:9, una imagen por slide."""
    from playwright.async_api import async_playwright
    shots: List[bytes] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 720},
                                          device_scale_factor=2)
            await page.set_content(html, wait_until="networkidle")
            for el in await page.query_selector_all(".slide"):
                shots.append(await el.screenshot(type="png"))
        finally:
            await browser.close()
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    for png in shots:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(BytesIO(png), 0, 0, width=prs.slide_width, height=prs.slide_height)
    buf = BytesIO(); prs.save(buf)
    return buf.getvalue()


def _native_pptx(doc: Dict, brand: Dict) -> bytes:
    """Export document to PPTX bytes. Fully editable, branded (solo documentos en flujo vertical)."""
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    primary = _hex_to_rgb(brand.get("primary_color", "#1a56db"))
    secondary = _hex_to_rgb(brand.get("secondary_color", "#0e1629"))
    accent = _hex_to_rgb(brand.get("accent_color", "#3b82f6"))
    font_name = brand.get("font_family", "Calibri").split(",")[0].strip()
    footer_text = brand.get("footer_text", "")

    for section in doc.get("sections", []):
        blocks = section.get("blocks", [])
        if not blocks:
            continue

        # Check if this section is a cover
        has_cover = any(b.get("block_type") == "cover" for b in blocks)

        if has_cover:
            _add_cover_slide(prs, blocks, secondary, accent, font_name, brand.get("name", ""))
        else:
            _add_content_slide(prs, section, blocks, primary, secondary, accent, font_name, footer_text)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _add_cover_slide(prs, blocks, secondary, accent, font_name, brand_name):
    """Add a cover/title slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout

    # Background
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = secondary

    cover_data = next((b["data"] for b in blocks if b["block_type"] == "cover"), {})

    # Title
    txBox = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(11), Inches(2))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = cover_data.get("title", "")
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = RGBColor(255, 255, 255)
    p.font.name = font_name

    # Subtitle
    p2 = tf.add_paragraph()
    p2.text = cover_data.get("subtitle", "")
    p2.font.size = Pt(16)
    p2.font.color.rgb = accent
    p2.font.name = font_name
    p2.space_before = Pt(12)

    # Brand line
    txBrand = slide.shapes.add_textbox(Inches(1), Inches(5.5), Inches(11), Inches(0.5))
    tf2 = txBrand.text_frame
    p3 = tf2.paragraphs[0]
    p3.text = brand_name
    p3.font.size = Pt(10)
    p3.font.color.rgb = RGBColor(150, 150, 150)
    p3.font.name = font_name


def _add_content_slide(prs, section, blocks, primary, secondary, accent, font_name, footer_text):
    """Add a content slide with section title and blocks."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Section title bar
    title_shape = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(13.33), Inches(0.8))
    title_shape.fill.solid()
    title_shape.fill.fore_color.rgb = primary
    title_shape.line.fill.background()

    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.1), Inches(12), Inches(0.6))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = section.get("title", "")
    p.font.size = Pt(20)
    p.font.bold = True
    p.font.color.rgb = RGBColor(255, 255, 255)
    p.font.name = font_name

    y_pos = 1.1  # Start content below title bar

    # Collect KPIs for grid rendering
    kpis = [b for b in blocks if b.get("block_type") == "kpi"]
    other_blocks = [b for b in blocks if b.get("block_type") != "kpi"]

    # Render KPIs as a row
    if kpis:
        cols = min(len(kpis), 4)
        col_width = 12 / cols
        for i, kpi in enumerate(kpis):
            d = kpi.get("data", {})
            x = 0.5 + i * col_width
            _add_kpi_shape(slide, x, y_pos, col_width - 0.3, d, primary, accent, font_name)
        y_pos += 1.4

    # Render other blocks
    for block in other_blocks:
        bt = block.get("block_type", "")
        data = block.get("data", {})

        if bt == "text":
            y_pos = _add_text_block(slide, y_pos, data, font_name, data.get("style", ""))

        elif bt == "insight":
            y_pos = _add_insight_block(slide, y_pos, data, accent, font_name)

        elif bt == "table":
            y_pos = _add_table_block(slide, y_pos, data, primary, font_name)

        elif bt == "divider":
            y_pos += 0.2

        if y_pos > 6.5:
            break  # Prevent overflow

    # Footer
    if footer_text:
        txFooter = slide.shapes.add_textbox(Inches(0.5), Inches(7), Inches(12), Inches(0.3))
        tf = txFooter.text_frame
        p = tf.paragraphs[0]
        p.text = footer_text
        p.font.size = Pt(7)
        p.font.color.rgb = RGBColor(150, 150, 150)
        p.font.name = font_name


def _add_kpi_shape(slide, x, y, w, data, primary, accent, font_name):
    """Add a KPI card shape."""
    shape = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(1.2))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(245, 245, 245)
    shape.line.color.rgb = RGBColor(230, 230, 230)

    # Label
    txBox = slide.shapes.add_textbox(Inches(x + 0.15), Inches(y + 0.1), Inches(w - 0.3), Inches(0.25))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = str(data.get("title", ""))
    p.font.size = Pt(8)
    p.font.color.rgb = RGBColor(130, 130, 130)
    p.font.name = font_name

    # Value
    txVal = slide.shapes.add_textbox(Inches(x + 0.15), Inches(y + 0.35), Inches(w - 0.3), Inches(0.5))
    tf2 = txVal.text_frame
    p2 = tf2.paragraphs[0]
    p2.text = str(data.get("value", ""))
    p2.font.size = Pt(22)
    p2.font.bold = True
    p2.font.color.rgb = primary
    p2.font.name = font_name

    # Unit + variation
    unit = data.get("unit", "")
    variation = data.get("variation", "")
    if unit or variation:
        txSub = slide.shapes.add_textbox(Inches(x + 0.15), Inches(y + 0.85), Inches(w - 0.3), Inches(0.25))
        tf3 = txSub.text_frame
        p3 = tf3.paragraphs[0]
        p3.text = f"{unit}  {variation}".strip()
        p3.font.size = Pt(8)
        p3.font.color.rgb = RGBColor(100, 100, 100)
        p3.font.name = font_name


def _add_text_block(slide, y, data, font_name, style=""):
    """Add a text block. Returns new y position."""
    content = data.get("content", "")
    if not content:
        return y

    # Estimate height (rough: 1 inch per 300 chars)
    height = max(0.5, min(3.5, len(content) / 300))

    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(y), Inches(12), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = content
    p.font.size = Pt(11)
    p.font.color.rgb = RGBColor(60, 60, 60)
    p.font.name = font_name

    if style == "executive_summary":
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(30, 30, 30)
    elif style == "conclusion":
        p.font.italic = True

    return y + height + 0.2


def _add_insight_block(slide, y, data, accent, font_name):
    """Add an insight card."""
    title = data.get("title", "")
    summary = data.get("summary", "")

    height = max(0.5, min(1.5, len(summary) / 400 + 0.4))

    shape = slide.shapes.add_shape(1, Inches(0.5), Inches(y), Inches(12), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(255, 251, 235)
    shape.line.color.rgb = RGBColor(253, 230, 138)

    # Title
    txBox = slide.shapes.add_textbox(Inches(0.7), Inches(y + 0.08), Inches(11.5), Inches(0.25))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(9)
    p.font.bold = True
    p.font.color.rgb = RGBColor(146, 64, 14)
    p.font.name = font_name

    # Summary
    txSummary = slide.shapes.add_textbox(Inches(0.7), Inches(y + 0.3), Inches(11.5), Inches(height - 0.35))
    tf2 = txSummary.text_frame
    tf2.word_wrap = True
    p2 = tf2.paragraphs[0]
    p2.text = summary
    p2.font.size = Pt(10)
    p2.font.color.rgb = RGBColor(120, 53, 15)
    p2.font.name = font_name

    return y + height + 0.15


def _add_table_block(slide, y, data, primary, font_name):
    """Add a native PPTX table (fully editable)."""
    columns = data.get("columns", [])
    rows_data = data.get("rows", [])
    if not columns or not rows_data:
        return y

    num_rows = min(len(rows_data) + 1, 12)  # Header + data, max 12
    num_cols = len(columns)
    col_width = min(12 / num_cols, 4)
    table_width = col_width * num_cols
    row_height = 0.3
    table_height = num_rows * row_height

    table_shape = slide.shapes.add_table(num_rows, num_cols, Inches(0.5), Inches(y), Inches(table_width), Inches(table_height))
    table = table_shape.table

    # Header row
    for ci, col_name in enumerate(columns):
        cell = table.cell(0, ci)
        cell.text = str(col_name)
        for paragraph in cell.text_frame.paragraphs:
            paragraph.font.size = Pt(8)
            paragraph.font.bold = True
            paragraph.font.color.rgb = RGBColor(255, 255, 255)
            paragraph.font.name = font_name
        cell.fill.solid()
        cell.fill.fore_color.rgb = primary

    # Data rows
    for ri, row in enumerate(rows_data[:num_rows - 1]):
        for ci, val in enumerate(row[:num_cols]):
            cell = table.cell(ri + 1, ci)
            cell.text = str(val)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = Pt(9)
                paragraph.font.color.rgb = RGBColor(60, 60, 60)
                paragraph.font.name = font_name

    return y + table_height + 0.3
