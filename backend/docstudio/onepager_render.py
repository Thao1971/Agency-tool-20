"""Investment One Pager — dedicated A4-portrait renderer.

Single self-contained A4 page, fully blind (no company identity), built to be read in
under 3 minutes: the INVESTMENT THESIS is the hero ("why is this worth it?"), followed by
key KPIs, investment highlights and the standard bud advisors Deal Snapshot. Brand colors,
typography and logo come from the resolved document brand (same tokens as the rest of the
studio). Rendered to HTML → Chromium for PDF (A4 portrait) and PPTX (one image per A4 page).
"""

from typing import Dict, List


def _esc(s) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _colors(brand: Dict) -> Dict:
    return ((brand or {}).get("tokens") or {}).get("colors") or {}


def _fonts(brand: Dict) -> Dict:
    return ((brand or {}).get("tokens") or {}).get("fonts") or {}


def render_onepager_html(doc: Dict, brand: Dict) -> str:
    op = doc.get("onepager") or {}
    c = _colors(brand)
    f = _fonts(brand)
    accent = c.get("accent", "#F3D200")
    ink = c.get("text_primary", "#12201b")
    muted = c.get("text_muted", "#6f7b76")
    surface = c.get("bg_surface", "#f1f5f3")
    cover_bg = ((brand.get("tokens") or {}).get("cover") or {}).get("bg") or c.get("text_primary", "#12201b")
    hf = f.get("heading", "'Inter', Helvetica, Arial, sans-serif")
    bf = f.get("body", "'Inter', Helvetica, Arial, sans-serif")
    accent_text = c.get("accent_text", "#111111")
    brand_name = brand.get("name") or "bud advisors"

    # KPI strip
    kpi_html = ""
    for k in (op.get("kpis") or [])[:4]:
        note = k.get("note")
        note_html = (f'<div style="font:400 8px {bf};color:{muted};margin-top:3px;">{_esc(note)}</div>'
                     if note else "")
        kpi_html += (
            f'<div style="flex:1;background:{surface};border-radius:8px;padding:12px 14px;min-width:0;">'
            f'<div style="font:600 8.5px {bf};letter-spacing:.08em;text-transform:uppercase;color:{muted};margin-bottom:3px;">{_esc(k.get("label"))}</div>'
            f'<div style="font:700 19px {hf};color:{ink};line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_esc(k.get("value"))}'
            f'<span style="font:600 10px {bf};color:{muted};">&nbsp;{_esc(k.get("unit"))}</span></div>'
            f'{note_html}'
            f'</div>')
    kpi_strip = f'<div style="display:flex;gap:10px;margin:0 0 14px;">{kpi_html}</div>' if kpi_html else ""

    # Highlights (2-column cards)
    hl_html = ""
    for h in (op.get("highlights") or [])[:4]:
        hl_html += (
            f'<div style="background:#fff;border:1px solid {c.get("border","#e2e4e8")};border-left:3px solid {accent};'
            f'border-radius:7px;padding:10px 12px;">'
            f'<div style="font:700 11px {hf};color:{ink};margin-bottom:3px;">{_esc(h.get("title"))}</div>'
            f'<div style="font:400 9.5px {bf};color:{muted};line-height:1.45;">{_esc(h.get("summary"))}</div>'
            f'</div>')
    hl_block = (f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:0 0 14px;">{hl_html}</div>'
                if hl_html else "")

    # Deal snapshot (6-item grid)
    ds_html = ""
    for it in (op.get("deal_snapshot") or [])[:6]:
        ds_html += (
            f'<div style="background:{surface};border-radius:7px;padding:9px 11px;">'
            f'<div style="font:700 8px {bf};letter-spacing:.1em;text-transform:uppercase;color:{accent if _dark(accent) else ink};margin-bottom:3px;">{_esc(it.get("label"))}</div>'
            f'<div style="font:400 9px {bf};color:{ink};line-height:1.4;">{_esc(it.get("text"))}</div>'
            f'</div>')
    ds_block = (
        f'<div style="margin:0 0 6px;font:700 12px {hf};color:{ink};border-bottom:2px solid {accent};'
        f'padding-bottom:4px;display:inline-block;">Deal Snapshot</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:6px 0 0;">{ds_html}</div>'
        if ds_html else "")

    thesis = op.get("thesis") or ""
    thesis_title = op.get("thesis_title") or "¿Por qué merece la pena esta oportunidad?"

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Playfair+Display:wght@700&family=Montserrat:wght@400;600;700&family=Lora:wght@400;700&display=swap" rel="stylesheet">
<style>
@page {{ size: A4 portrait; margin: 0; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html,body {{ background:#fff; }}
.page {{ width:794px; height:1123px; margin:0 auto; background:#fff; position:relative;
         display:flex; flex-direction:column; font-family:{bf}; color:{ink}; }}
</style></head>
<body>
<div class="page">
  <!-- Header band -->
  <div style="background:{cover_bg};color:#fff;padding:18px 40px 16px;">
    <div style="font:700 9px {bf};letter-spacing:.22em;color:{accent};text-transform:uppercase;">{_esc(op.get('header'))}</div>
    <div style="display:flex;justify-content:space-between;align-items:flex-end;margin-top:8px;">
      <div>
        <div style="font:700 27px {hf};color:#fff;line-height:1.05;">{_esc(op.get('title'))}</div>
        <div style="font:400 12px {bf};color:rgba(255,255,255,.72);margin-top:4px;">{_esc(op.get('subtitle'))}</div>
      </div>
      <div style="text-align:right;font:600 11px {bf};color:rgba(255,255,255,.85);">{_esc(brand_name)}<br>
        <span style="font:400 9px {bf};color:rgba(255,255,255,.5);">{_esc(op.get('date'))}</span></div>
    </div>
  </div>

  <!-- Body -->
  <div style="flex:1;padding:18px 40px 0;display:flex;flex-direction:column;">
    <div style="font:400 10px {bf};color:{muted};margin-bottom:12px;line-height:1.5;">{_esc(op.get('profile'))}</div>

    <!-- HERO: Investment Thesis -->
    <div style="background:{surface};border-left:5px solid {accent};border-radius:10px;padding:16px 20px;margin-bottom:16px;">
      <div style="font:700 15px {hf};color:{ink};margin-bottom:8px;">{_esc(thesis_title)}</div>
      <div style="font:400 12px {bf};color:{ink};line-height:1.62;">{_esc(thesis)}</div>
    </div>

    {kpi_strip}
    {hl_block}
    {ds_block}
  </div>

  <!-- Footer / CTA -->
  <div style="background:{cover_bg};color:#fff;padding:14px 40px;margin-top:12px;">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:20px;">
      <div style="flex:1;">
        <div style="font:700 12px {hf};color:{accent};">{_esc(op.get('cta'))}</div>
        <div style="font:400 8px {bf};color:rgba(255,255,255,.55);margin-top:5px;line-height:1.45;">{_esc(op.get('confidentiality'))}</div>
      </div>
      <div style="text-align:right;font:600 10px {bf};color:rgba(255,255,255,.85);white-space:nowrap;">{_esc(op.get('advisor'))}</div>
    </div>
  </div>
</div>
</body></html>"""


def _dark(hex_color: str) -> bool:
    """True if the color is dark enough that using it as text on white is legible."""
    try:
        h = str(hex_color).lstrip('#')
        if len(h) != 6:
            return True
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) < 150
    except Exception:
        return True


def is_onepager(doc: Dict) -> bool:
    return (doc.get("metadata") or {}).get("type") == "one_pager" or bool(doc.get("onepager"))
