"""PDF report generator for agency scraper results using ReportLab."""

import io
import logging
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER

logger = logging.getLogger(__name__)

# Colors
DARK_BG = colors.HexColor('#18181b')
BLUE = colors.HexColor('#3b82f6')
ZINC_700 = colors.HexColor('#3f3f46')
ZINC_400 = colors.HexColor('#a1a1aa')
ZINC_200 = colors.HexColor('#e4e4e7')
WHITE = colors.HexColor('#fafafa')
GREEN = colors.HexColor('#10b981')
AMBER = colors.HexColor('#f59e0b')
RED = colors.HexColor('#ef4444')


def _conf_color(val):
    if val >= 85: return GREEN
    if val >= 50: return AMBER
    return RED


def generate_result_pdf(result: dict, screenshot_bytes: bytes = None, logo_bytes: bytes = None) -> bytes:
    """Generate a PDF report for an agency result. Returns PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm,
                            leftMargin=2*cm, rightMargin=2*cm)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, textColor=DARK_BG,
                              spaceAfter=2*mm, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, textColor=ZINC_400,
                              spaceAfter=4*mm))
    styles.add(ParagraphStyle('SectionHeader', parent=styles['Normal'], fontSize=11,
                              textColor=BLUE, fontName='Helvetica-Bold', spaceBefore=6*mm, spaceAfter=3*mm))
    styles.add(ParagraphStyle('FieldLabel', parent=styles['Normal'], fontSize=8, textColor=ZINC_400,
                              fontName='Helvetica'))
    styles.add(ParagraphStyle('FieldValue', parent=styles['Normal'], fontSize=10, textColor=DARK_BG,
                              fontName='Helvetica', spaceAfter=2*mm))
    styles.add(ParagraphStyle('SmallGray', parent=styles['Normal'], fontSize=8, textColor=ZINC_400))

    elements = []

    # Header
    company = result.get('company_name') or 'Unknown Agency'
    elements.append(Paragraph(company, styles['Title2']))
    elements.append(Paragraph(result.get('input_url', ''), styles['Subtitle']))

    # Meta line
    meta_parts = []
    if result.get('category'):
        meta_parts.append(f"<b>Category:</b> {result['category']}")
    if result.get('subcategory'):
        meta_parts.append(f"<b>Subcategory:</b> {result['subcategory']}")
    score = result.get('confidence_overall', 0) or 0
    meta_parts.append(f"<b>Confidence:</b> {score}/100")
    date_str = result.get('created_at', '')[:10] if result.get('created_at') else 'N/A'
    meta_parts.append(f"<b>Date:</b> {date_str}")
    elements.append(Paragraph(' &nbsp;|&nbsp; '.join(meta_parts), styles['SmallGray']))
    elements.append(Spacer(1, 4*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=ZINC_700))

    # Description
    if result.get('description'):
        elements.append(Paragraph('Description', styles['SectionHeader']))
        elements.append(Paragraph(result['description'], styles['FieldValue']))

    # Tags
    if result.get('tags'):
        elements.append(Paragraph('Tags', styles['SectionHeader']))
        elements.append(Paragraph(', '.join(result['tags']), styles['FieldValue']))

    # Contact
    contact_data = []
    if result.get('main_contact_name'):
        role = f" ({result['main_contact_role']})" if result.get('main_contact_role') else ''
        contact_data.append(('Contact', f"{result['main_contact_name']}{role}"))
    if result.get('main_contact_email'):
        contact_data.append(('Email', result['main_contact_email']))
    if result.get('phone'):
        contact_data.append(('Phone', result['phone']))

    if contact_data:
        elements.append(Paragraph('Contact', styles['SectionHeader']))
        for label, val in contact_data:
            elements.append(Paragraph(f"<b>{label}:</b> {val}", styles['FieldValue']))

    # Address
    addr_parts = []
    if result.get('address_street'): addr_parts.append(result['address_street'])
    if result.get('address_city'): addr_parts.append(result['address_city'])
    if result.get('address_province'): addr_parts.append(result['address_province'])
    if result.get('postal_code'): addr_parts.append(result['postal_code'])
    if result.get('country'): addr_parts.append(result['country'])

    if addr_parts:
        elements.append(Paragraph('Address', styles['SectionHeader']))
        elements.append(Paragraph(', '.join(addr_parts), styles['FieldValue']))

    # Clients
    if result.get('main_clients'):
        elements.append(Paragraph(f"Clients ({len(result['main_clients'])})", styles['SectionHeader']))
        elements.append(Paragraph(', '.join(result['main_clients'][:20]), styles['FieldValue']))

    # Awards
    if result.get('has_awards') and result.get('awards_evidence'):
        elements.append(Paragraph('Awards', styles['SectionHeader']))
        for a in result['awards_evidence'][:10]:
            elements.append(Paragraph(f"- {a}", styles['FieldValue']))

    # Confidence scores
    elements.append(Paragraph('Confidence Scores', styles['SectionHeader']))
    conf_fields = [
        ('Overall', result.get('confidence_overall', 0) or 0),
        ('Category', result.get('confidence_category', 0) or 0),
        ('Description', result.get('confidence_description', 0) or 0),
        ('Clients', result.get('confidence_clients', 0) or 0),
        ('Contact', result.get('confidence_contact', 0) or 0),
        ('Address', result.get('confidence_address', 0) or 0),
        ('Awards', result.get('confidence_awards', 0) or 0),
    ]
    conf_table_data = [['Field', 'Score']]
    for label, val in conf_fields:
        conf_table_data.append([label, str(val)])

    conf_table = Table(conf_table_data, colWidths=[120, 60])
    conf_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR', (0, 1), (0, -1), ZINC_400),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, ZINC_700),
    ]))
    elements.append(conf_table)

    # Screenshot
    if screenshot_bytes:
        try:
            elements.append(Spacer(1, 6*mm))
            elements.append(Paragraph('Homepage Screenshot', styles['SectionHeader']))
            img_buf = io.BytesIO(screenshot_bytes)
            img = Image(img_buf, width=16*cm, height=9*cm)
            img.hAlign = 'LEFT'
            elements.append(img)
        except Exception as e:
            logger.warning(f"Failed to add screenshot to PDF: {e}")

    # Pages visited
    if result.get('visited_pages'):
        elements.append(Paragraph(f"Pages Visited ({len(result['visited_pages'])})", styles['SectionHeader']))
        for p in result['visited_pages'][:15]:
            elements.append(Paragraph(p, styles['SmallGray']))

    # Footer
    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=ZINC_700))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        f"Generated by Agency Scraper v2.0 | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        styles['SmallGray']
    ))

    doc.build(elements)
    return buf.getvalue()
