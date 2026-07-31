"""Live HTML preview of a document — rendered with the RICH 2-layer brand (base
platform brand + client overlay), so the editor shows the document as it will look,
not just a block list. Same block vocabulary as the composer / layout editor.

Two page layouts:
- "flow"   — vertical A4-ish column (teaser, ficha, snapshot).
- "slides" — landscape 16:9 slides, one per section (cuaderno de venta / PPT style:
             infomemo, valoración, estratégico, sectorial…). Daniel: "es en formato
             horizontal como un ppt".

Used by GET /docstudio/documents/{id}/preview. Honest: renders exactly the blocks the
document has; empty AI blocks show as empty (they populate when Claude fills them).
"""

from __future__ import annotations

import html as _html
from typing import Dict, List

from documents.brand_unified import PLATFORM_BRANDS, resolve_platform_brand, compose_brand

# Document types that read as a landscape deck (a "cuaderno de venta"/PPT), not a page.
_LANDSCAPE_TYPES = {
    "information_memorandum", "investment_memo", "strategic_analysis",
    "valuation_approx", "valuation_advanced", "comparative", "sector_report",
    "benchmark", "benchmark_advanced", "opportunities", "ranking",
    "fragmentation", "rollup", "succession",
}


def _esc(s) -> str:
    return _html.escape(str(s)) if s is not None else ""


def resolve_doc_brand(doc: Dict) -> Dict:
    """Resolve the composed brand for a document: base (by brand_id) + client overlay
    (brand_overlay) + per-document color override, all layered."""
    bid = doc.get("brand_id")
    base = PLATFORM_BRANDS.get(bid)
    base = (base and dict(base)) or resolve_platform_brand(bid)
    overlay = dict(doc.get("brand_overlay") or {})
    color_override = doc.get("color_override") or {}
    if color_override:
        tokens = dict(overlay.get("tokens") or {})
        colors = dict(tokens.get("colors") or {})
        colors.update(color_override)
        tokens["colors"] = colors
        overlay["tokens"] = tokens
    return compose_brand(base, overlay)


def _layout_for(doc: Dict) -> str:
    """Explicit doc.orientation wins; else landscape for deck-type documents."""
    o = (doc.get("orientation") or "").lower()
    if o in ("landscape", "slides"):
        return "slides"
    if o in ("portrait", "flow"):
        return "flow"
    dtype = (doc.get("metadata") or {}).get("type")
    return "slides" if dtype in _LANDSCAPE_TYPES else "flow"


def _bars(points: List[Dict], key: str, color: str, bf: str, h_max: int = 120) -> str:
    """Tiny inline bar chart (no JS) for an evolution series [{year, revenue, ebitda}]."""
    vals = [(p.get("year"), p.get(key)) for p in points if p.get(key) is not None]
    if not vals:
        return ""
    mx = max(v for _, v in vals) or 1
    bars = ""
    for yr, v in vals:
        hgt = max(4, round((v / mx) * h_max))
        bars += (f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:4px;flex:1;">'
                 f'<div style="font:600 9px {bf};color:{color};">{f"{v/1e6:.2f}".replace(".", ",")}M</div>'
                 f'<div style="width:70%;height:{hgt}px;background:{color};border-radius:3px 3px 0 0;"></div>'
                 f'<div style="font:400 9px {bf};color:#999;">{_esc(yr)}</div></div>')
    return f'<div style="display:flex;align-items:flex-end;gap:6px;height:{h_max+30}px;margin-top:8px;">{bars}</div>'


def _kpi_grid_html(blocks: List[Dict], c, hf, bf) -> str:
    def col(k, d="#000"):
        return c.get(k, d)
    kpis = [b for b in blocks if b.get("block_type") == "kpi"]
    if not kpis:
        return ""
    # Equal-size cards (CSS grid), pure white background with a defined border.
    card_bg = "#FFFFFF"
    cards = ""
    for b in kpis:
        d = b.get("data", {})
        cards += (f'<div style="background:{card_bg};border:1px solid #E2E4E8;border-radius:10px;padding:12px 14px;min-height:70px;box-sizing:border-box;">'
                  f'<div style="font:700 20px {hf};color:{col("kpi_value","#111")};">{_esc(d.get("value"))} '
                  f'<span style="font:400 11px {bf};color:{col("text_secondary","#555")};">{_esc(d.get("unit"))}</span></div>'
                  f'<div style="font:500 11px {bf};color:{col("text_secondary","#444")};margin-top:3px;">{_esc(d.get("title"))}</div>'
                  + (f'<div style="font:400 10px {bf};color:{col("text_muted","#777")};margin-top:2px;">{_esc(d.get("commentary"))}</div>' if d.get("commentary") else "")
                  + "</div>")
    return f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px;">{cards}</div>'


def _block_html(b: Dict, c, hf, bf, in_slide: bool = False) -> str:
    """Render a single non-cover, non-kpi block to HTML."""
    def col(k, d="#000"):
        return c.get(k, d)
    bt = b.get("block_type")
    d = b.get("data", {})
    if bt == "text":
        style = d.get("style")
        if style == "executive_summary":
            return (f'<div style="background:{col("bg_surface","#f5f5f5")};border-left:3px solid {col("accent","#333")};'
                    f'border-radius:6px;padding:12px 16px;margin:8px 0;font:400 14px {bf};color:{col("text_primary","#111")};line-height:1.6;">{_esc(d.get("content"))}</div>')
        if style == "legal":
            return f'<div style="font:400 11.5px {bf};color:{col("text_secondary","#555")};line-height:1.4;margin:0 0 6px;text-align:justify;">{_esc(d.get("content"))}</div>'
        if style == "spacer":
            try:
                _h = int(float(d.get("content") or 16))
            except (TypeError, ValueError):
                _h = 16
            return f'<div style="height:{_h}px;" aria-hidden="true"></div>'
        if style == "subhead":
            return (f'<div style="font:700 15px {hf};color:{col("text_primary","#111")};'
                    f'border-bottom:2px solid {col("accent","#F3D200")};padding-bottom:5px;'
                    f'margin:12px 0 10px;display:block;width:fit-content;max-width:100%;">{_esc(d.get("content"))}</div>')
        if style == "bullet":
            return (f'<div style="font:400 14px {bf};color:{col("text_primary","#111")};line-height:1.3;'
                    f'margin:3px 0;padding-left:20px;text-indent:-16px;break-inside:avoid;">'
                    f'<span style="color:{col("accent","#F3D200")};font-weight:700;font-size:16px;">•</span>&nbsp;{_esc(d.get("content"))}</div>')
        return f'<div style="font:400 14px {bf};color:{col("text_primary","#111")};line-height:1.6;margin:6px 0;{"font-style:italic;" if style=="conclusion" else ""}">{_esc(d.get("content"))}</div>'
    if bt == "table":
        cols = d.get("columns", [])
        rows = d.get("rows", [])
        ths = "".join(f'<th style="text-align:left;padding:7px 11px;font:600 11px {bf};color:{col("table_header_text","#fff")};">{_esc(x)}</th>' for x in cols)
        trs = ""
        for i, r in enumerate(rows):
            tds = "".join(f'<td style="padding:7px 11px;font:400 12px {bf};color:{col("text_primary","#111")};">{_esc(x)}</td>' for x in r)
            bg = col("table_row_alt", "#fafafa") if i % 2 else "transparent"
            trs += f'<tr style="background:{bg};">{tds}</tr>'
        title = f'<div style="font:600 12px {bf};color:{col("text_secondary","#444")};margin:8px 0 4px;">{_esc(d.get("title"))}</div>' if d.get("title") else ""
        return (title + f'<table style="width:100%;border-collapse:collapse;margin-bottom:8px;">'
                f'<thead><tr style="background:{col("table_header_bg","#222")};">{ths}</tr></thead><tbody>{trs}</tbody></table>')
    if bt == "insight":
        accent = col("accent", "#c00")
        sz = "14px" if in_slide else "13px"
        return (f'<div style="background:#FFFFFF;border:1px solid #E2E4E8;border-left:3px solid {accent};'
                f'border-radius:8px;padding:14px 16px;margin:0;box-sizing:border-box;">'
                f'<div style="font:600 13px {hf};color:{col("text_primary","#111")};margin-bottom:4px;">{_esc(d.get("title"))}</div>'
                f'<div style="font:400 {sz} {bf};color:{col("text_secondary","#444")};line-height:1.5;">{_esc(d.get("summary"))}</div></div>')
    if bt == "deal_snapshot":
        # Bloque estándar de bud advisors — misma identidad en One Pager, Teaser e Infomemo.
        accent = col("accent", "#F3D200")
        ink = col("text_primary", "#111")
        muted = col("text_secondary", "#555")
        items = d.get("items", [])
        title = d.get("title", "Deal Snapshot")
        cells = ""
        for i, it in enumerate(items):
            cells += (
                f'<div style="border:1px solid #E2E4E8;border-radius:8px;padding:11px 13px;box-sizing:border-box;background:#FFFFFF;">'
                f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:5px;">'
                f'<span style="display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;'
                f'border-radius:50%;background:{accent};color:#111;font:700 11px {bf};flex:none;">{i+1}</span>'
                f'<span style="font:700 11px {hf};color:{ink};letter-spacing:.4px;text-transform:uppercase;">{_esc(it.get("label"))}</span>'
                f'</div>'
                f'<div style="font:400 12.5px {bf};color:{muted};line-height:1.35;">{_esc(it.get("text"))}</div>'
                f'</div>')
        head = (f'<div style="display:flex;align-items:center;gap:9px;margin:2px 0 9px;">'
                f'<span style="font:700 13px {hf};color:{ink};letter-spacing:1px;text-transform:uppercase;">{_esc(title)}</span>'
                f'<span style="flex:1;height:2px;background:{accent};"></span></div>')
        return (head + f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:9px;">{cells}</div>')
    if bt == "chart":
        title = f'<div style="font:600 13px {bf};color:{col("text_secondary","#444")};margin:8px 0 4px;">{_esc(d.get("title"))}</div>' if d.get("title") else ""
        ctype = d.get("chart_type", "bar")
        cfg = d.get("config") or {}
        # Tipos de la librería SVG (barras con ref, donut, scatter, línea).
        if ctype in ("donut", "pie", "scatter", "line", "grouped_bar", "grouped", "waterfall", "bridge", "radar", "nested_circles", "tam_sam_som", "nested", "gauge") or (d.get("dataset") or {}).get("bars"):
            from docstudio import charts as _charts
            svg = _charts.render_chart(ctype, d, col("accent", "#BA7517"), bf)
            if svg:
                # Ancho acotado opcional (config.max_width) para reducir SOLO este gráfico.
                mw = cfg.get("max_width")
                wrap = f"max-width:{mw};" if mw else ""
                return title + f'<div style="margin:2px 0 8px;{wrap}">{svg}</div>'
        # Legado: barras inline desde dataset.points + value_key.
        pts = (d.get("dataset") or {}).get("points") or d.get("points") or []
        key = d.get("value_key", "revenue")
        return title + (_bars(pts, key, col("accent", "#666"), bf, 150 if in_slide else 90) or f'<div style="font:400 11px {bf};color:#999;">[gráfico]</div>')
    if bt == "ownership":
        return _ownership_html(d, c, hf, bf)
    if bt == "orgchart":
        return _orgchart_html(d, c, hf, bf)
    if bt == "divider":
        return f'<hr style="border:none;border-top:1px solid #eee;margin:14px 0;">'
    if bt == "page_break" and not in_slide:
        return (f'<div style="display:flex;align-items:center;gap:8px;margin:14px 0;color:{col("accent","#888")};opacity:.55;">'
                f'<div style="flex:1;border-top:2px dashed {col("accent","#888")};"></div>'
                f'<span style="font:600 9px {bf};text-transform:uppercase;letter-spacing:1px;">salto de página</span>'
                f'<div style="flex:1;border-top:2px dashed {col("accent","#888")};"></div></div>')
    return ""


def _section_blocks_html(blocks: List[Dict], c, hf, bf, in_slide: bool) -> str:
    """Render a section's non-cover/non-kpi blocks. Consecutive `insight` blocks are laid
    out in a responsive 2-column grid (Investment Highlights style); everything else full width."""
    out = ""
    i, n = 0, len(blocks)
    while i < n:
        bt = blocks[i].get("block_type")
        if bt == "cover":
            i += 1
            continue
        if bt == "kpi":
            run = []
            while i < n and blocks[i].get("block_type") == "kpi":
                run.append(blocks[i]); i += 1
            out += _kpi_grid_html(run, c, hf, bf)
            continue
        if bt == "text" and (blocks[i].get("data") or {}).get("style") == "bullet":
            run = []
            while i < n and blocks[i].get("block_type") == "text" and (blocks[i].get("data") or {}).get("style") == "bullet":
                run.append(blocks[i]); i += 1
            inner = "".join(_block_html(b, c, hf, bf, in_slide) for b in run)
            out += f'<div style="column-count:2;column-gap:32px;margin:6px 0 6px 12px;">{inner}</div>'
            continue
        # Fila emparejada: gráfico compacto (config.pair) + insight contiguo en la misma fila.
        if (bt == "chart" and ((blocks[i].get("data") or {}).get("config") or {}).get("pair")
                and i + 1 < n and blocks[i + 1].get("block_type") == "insight"):
            _cfg = (blocks[i]["data"].get("config") or {})
            chart_w = _cfg.get("pair_width") or "26%"
            align = _cfg.get("pair_align") or "center"
            chart_html = _block_html(blocks[i], c, hf, bf, in_slide)
            insight_html = _block_html(blocks[i + 1], c, hf, bf, in_slide)
            out += (f'<div style="display:flex;gap:22px;align-items:{align};margin:6px 0;">'
                    f'<div style="width:{chart_w};flex:0 0 {chart_w};box-sizing:border-box;">{chart_html}</div>'
                    f'<div style="flex:1;box-sizing:border-box;">{insight_html}</div></div>')
            i += 2
            continue
        if bt == "chart":
            run = []
            while i < n and blocks[i].get("block_type") == "chart":
                run.append(blocks[i]); i += 1
            if len(run) >= 2:
                items = "".join(f'<div style="width:calc(50% - 11px);box-sizing:border-box;">{_block_html(b, c, hf, bf, in_slide)}</div>' for b in run)
                out += f'<div style="display:flex;flex-wrap:wrap;gap:22px;align-items:flex-start;">{items}</div>'
            else:
                out += _block_html(run[0], c, hf, bf, in_slide)
            continue
        if bt == "insight":
            run = []
            while i < n and blocks[i].get("block_type") == "insight":
                run.append(blocks[i]); i += 1
            # Los insights con data.full_width se renderizan a línea completa (no en 2 columnas);
            # el resto se agrupan de dos en dos.
            buff = []
            def _flush(bl):
                if not bl:
                    return ""
                if len(bl) >= 2:
                    items = "".join(f'<div style="width:calc(50% - 6px);box-sizing:border-box;">{_block_html(x, c, hf, bf, in_slide)}</div>' for x in bl)
                    return f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin:4px 0;">{items}</div>'
                return _block_html(bl[0], c, hf, bf, in_slide)
            for x in run:
                if (x.get("data") or {}).get("full_width"):
                    out += _flush(buff); buff = []
                    out += f'<div style="margin:4px 0;">{_block_html(x, c, hf, bf, in_slide)}</div>'
                else:
                    buff.append(x)
            out += _flush(buff)
            continue
        out += _block_html(blocks[i], c, hf, bf, in_slide)
        i += 1
    return out


def _logo_markup(brand, height: int, text_color: str, bf: str, prefer: str = "light") -> str:
    """Logotipo de marca robusto: imagen si carga; si falla (URL caída/inaccesible), cae a un
    wordmark de texto para no dejar la marca en blanco."""
    url = (brand.get("logo_light" if prefer == "light" else "logo_dark")
           or brand.get("logo_dark") or brand.get("logo_light"))
    word = _esc(brand.get("logo_text") or "bud")
    span = (f'<span style="font:700 {round(height*0.8)}px {bf};letter-spacing:.5px;color:{text_color};'
            f'{"display:none;" if url else ""}">{word}</span>')
    if url:
        img = (f'<img src="{_esc(url)}" alt="{word}" style="height:{height}px;display:inline-block;vertical-align:middle;" '
               f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\'">')
        return img + span
    return span


def _own_pct(v) -> str:
    if v is None:
        return ""
    return f"{v:.2f}".replace(".", ",") + " %"


def _ownership_html(d: Dict, c, hf, bf) -> str:
    """Diagrama de estructura societaria (accionistas · sociedad · participadas), estilo dashboard."""
    def col(k, dv="#000"):
        return c.get(k, dv)
    accent = col("accent", "#F3D200")
    ramp = [accent, "#2b2b2b", "#565656", "#7e7e7e", "#a3a3a3", "#c4c4c4", "#dcdcdc", "#e8e8e8"]
    company = d.get("company") or {}
    sh = [s for s in (d.get("shareholders") or []) if s.get("name")]
    inv = [i for i in (d.get("investees") or []) if i.get("name")]

    def card(sq_color, name, sub, pct, pct_pill=False, highlight=False):
        pct_html = (f'<span style="background:{accent};color:#1b1b1b;font:700 12px {bf};padding:2px 8px;border-radius:6px;">{_own_pct(pct)}</span>'
                    if pct_pill else f'<span style="font:700 15px {hf};color:{col("text_primary","#111")};">{_own_pct(pct)}</span>')
        bd = f'2px solid {accent}' if highlight else '1px solid #E2E4E8'
        return (f'<div style="border:{bd};border-radius:10px;padding:10px 12px;background:#fff;box-sizing:border-box;">'
                f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;">'
                f'<span style="width:11px;height:11px;border-radius:3px;background:{sq_color};display:inline-block;"></span>'
                f'<span style="font:600 12.5px {hf};color:{col("text_primary","#111")};line-height:1.15;">{_esc(name)}</span></div>'
                f'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">'
                f'<span style="font:400 10px {bf};color:{col("text_muted","#888")};">{_esc(sub)}</span>{pct_html}</div></div>')

    def _connector():
        return f'<div style="display:flex;justify-content:center;"><div style="width:2px;height:16px;background:#D0D2D6;"></div></div>'

    out = []
    # Accionistas
    if sh:
        tot = sum((s.get("pct") or 0) for s in sh) or 100
        out.append(f'<div style="font:600 12px {bf};color:{col("text_secondary","#555")};margin:2px 0 6px;">Accionistas · {len(sh)}</div>')
        seg = "".join(f'<div style="width:{max((s.get("pct") or 0)/tot*100,1):.1f}%;background:{ramp[min(i,len(ramp)-1)]};"></div>' for i, s in enumerate(sh))
        out.append(f'<div style="display:flex;height:12px;border-radius:6px;overflow:hidden;margin-bottom:10px;">{seg}</div>')
        cards = "".join(card(ramp[min(i, len(ramp)-1)], s["name"], ("Persona jurídica" if s.get("cif") else "Accionista"), s.get("pct"), highlight=(i == 0)) for i, s in enumerate(sh))
        out.append(f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;">{cards}</div>')
        out.append(_connector())

    # Matriz (si la hay), encima del nodo central
    if company.get("parent"):
        out.append(f'<div style="display:flex;justify-content:center;margin-bottom:2px;">'
                   f'<div style="border:1px solid #D0D2D6;border-radius:8px;padding:5px 12px;background:#fff;font:400 11px {bf};color:{col("text_secondary","#555")};">'
                   f'Matriz · <span style="font-weight:600;color:{col("text_primary","#111")};">{_esc(company["parent"])}</span></div></div>')
        out.append(_connector())

    # Sociedad (nodo central)
    ini = "".join(w[0] for w in (company.get("name") or "  ").split()[:2]).upper() or "•"
    meta = " · ".join(x for x in [company.get("type"), (f'CIF {company.get("cif")}' if company.get("cif") else None), company.get("location")] if x)
    out.append(
        f'<div style="display:flex;justify-content:center;margin:2px 0;">'
        f'<div style="display:flex;align-items:center;gap:12px;background:#0b0b0b;border-radius:12px;padding:12px 18px;max-width:72%;">'
        f'<span style="width:34px;height:34px;border-radius:8px;background:{accent};color:#1b1b1b;font:700 13px {hf};display:flex;align-items:center;justify-content:center;">{_esc(ini)}</span>'
        f'<div><div style="font:700 15px {hf};color:#fff;">{_esc(company.get("name"))}</div>'
        f'<div style="font:400 10.5px {bf};color:#aaa;margin-top:1px;">{_esc(meta)}</div></div></div></div>')
    if inv:
        out.append(_connector())

    # Participadas — con ramal de organigrama (bus horizontal + stub a cada card)
    if inv:
        out.append(f'<div style="font:600 12px {bf};color:{col("text_secondary","#555")};margin:6px 0 4px;">Controla a · Empresas participadas · {len(inv)}</div>')
        cols = ""
        for i in inv:
            sub = " · ".join(x for x in [i.get("sector"), i.get("location")] if x)
            cols += (f'<div style="flex:1 1 150px;min-width:150px;max-width:250px;position:relative;padding-top:14px;box-sizing:border-box;">'
                     f'<div style="position:absolute;top:0;left:50%;width:2px;height:14px;background:#D0D2D6;"></div>'
                     f'{card(accent, i["name"], sub, i.get("pct"), pct_pill=True)}</div>')
        out.append(f'<div style="position:relative;">'
                   f'<div style="position:absolute;top:0;left:12%;right:12%;height:2px;background:#D0D2D6;"></div>'
                   f'<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;">{cols}</div></div>')
    return "".join(out)


def _person_avatar(size: int = 40) -> str:
    """Silueta gris de persona (icono organigrama), estilo referencia."""
    r = size
    return (f'<svg width="{r}" height="{r}" viewBox="0 0 40 40" style="display:block;">'
            f'<circle cx="20" cy="14" r="7.5" fill="#B8BCC2"/>'
            f'<path d="M6 37 C6 27 14 24 20 24 C26 24 34 27 34 37 Z" fill="#B8BCC2"/></svg>')


def _orgchart_html(d: Dict, c, hf, bf) -> str:
    """Organigrama / estructura operativa: nodo raíz · departamentos · miembros."""
    def col(k, dv="#000"):
        return c.get(k, dv)
    root = d.get("root") or {}
    groups = [g for g in (d.get("groups") or []) if (g.get("lead") or {}).get("name") or g.get("members")]

    def node(p, lead=False):
        name = _esc((p or {}).get("name") or "")
        role = _esc((p or {}).get("role") or "")
        av = _person_avatar(42 if lead else 30)
        nm = (f'<div style="font:{"600 11.5px" if lead else "400 10.5px"} {hf};color:{col("text_primary","#111")};'
              f'margin-top:3px;line-height:1.15;text-align:center;max-width:120px;">{name}</div>' if name else "")
        rl = (f'<div style="font:400 9.5px {bf};color:{col("text_muted","#888")};text-align:center;max-width:120px;">{role}</div>'
              if role else "")
        return (f'<div style="display:flex;flex-direction:column;align-items:center;margin:0 6px;">{av}{nm}{rl}</div>')

    out = []
    # Nodo raíz (Dirección)
    if root.get("name") or root.get("role"):
        out.append(f'<div style="display:flex;justify-content:center;">{node(root, lead=True)}</div>')
        if groups:
            out.append(f'<div style="display:flex;justify-content:center;"><div style="width:2px;height:14px;background:#D0D2D6;"></div></div>')
    # Departamentos (bus horizontal + columnas)
    if groups:
        colsn = ""
        for g in groups:
            members = "".join(node(m) for m in (g.get("members") or []) if m.get("name"))
            mem_html = (f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px;margin-top:8px;">{members}</div>'
                        if members else "")
            colsn += (f'<div style="flex:1 1 130px;min-width:120px;max-width:220px;position:relative;padding-top:14px;box-sizing:border-box;'
                      f'display:flex;flex-direction:column;align-items:center;">'
                      f'<div style="position:absolute;top:0;left:50%;width:2px;height:14px;background:#D0D2D6;"></div>'
                      f'{node(g.get("lead") or {}, lead=True)}{mem_html}</div>')
        out.append(f'<div style="position:relative;margin-top:2px;">'
                   f'<div style="position:absolute;top:0;left:10%;right:10%;height:2px;background:#D0D2D6;"></div>'
                   f'<div style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;align-items:flex-start;">{colsn}</div></div>')
    return "".join(out)


def _cover_html(d: Dict, brand, cov, hf, bf, big: bool = False) -> str:
    logo = _logo_markup(brand, 40 if big else 28, cov.get("brand_text", cov.get("text", "#fff")), bf, prefer="light")
    pad = "44px 60px" if big else "40px 34px"
    tsize = "42px" if big else "26px"
    ssize = "18px" if big else "14px"
    advisor = (f'<div style="font:400 {("13px" if big else "11px")} {bf};color:{cov.get("subtitle_text","#bbb")};'
               f'margin-top:{"34px" if big else "22px"};opacity:.85;line-height:1.9;letter-spacing:.4px;">'
               f'{_esc(d.get("advisor"))}</div>'
               if d.get("advisor") else "")
    accent = cov.get("brand_text", "#F3D200")
    bar_w = "80px" if big else "56px"
    bar = f'<div style="width:{bar_w};height:{"5px" if big else "4px"};background:{accent};border-radius:2px;margin:16px 0 4px;"></div>'
    date_html = (f'<div style="font:500 {("14px" if big else "12px")} {bf};color:{accent};margin-top:4px;letter-spacing:.3px;">{_esc(d.get("date"))}</div>'
                 if d.get("date") else "")
    return (f'<div style="background:{cov.get("bg", "#111")};padding:{pad};border-radius:12px;margin-bottom:12px;position:relative;{"height:100%;box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;" if big else ""}">'
            f'<div style="margin-bottom:2px;">{logo}</div>'
            f'<div style="font:700 {tsize} {hf};color:{cov.get("text","#fff")};margin-top:10px;line-height:1.1;">{_esc(d.get("title"))}</div>'
            f'{bar}'
            f'<div style="font:400 {ssize} {bf};color:{cov.get("subtitle_text","#bbb")};margin-top:2px;">{_esc(d.get("subtitle"))}</div>{date_html}{advisor}</div>')


def _page_shell(body: str, bg: str) -> str:
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Montserrat:wght@400;500;600;700&family=Playfair+Display:wght@600;700&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">'
            f'<style>@media print{{.slide{{page-break-after:always;box-shadow:none!important;margin:0 auto!important;}}}}</style>'
            f'</head><body style="margin:0;background:{bg};padding:26px 30px;">{body}</body></html>')


def _norm_title(s) -> str:
    """Normaliza un título para comparar: minúsculas, sin acentos, sin numeración/puntuación,
    quedándose con la parte anterior a un separador ' · ' o ' — '."""
    import unicodedata, re
    s = str(s or "")
    for sep in (" · ", " — ", " - "):
        if sep in s:
            s = s.split(sep)[0]
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"^\s*\d+(\.\d+)*\s*", "", s)          # quita "5.1 ", "04 ", etc.
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _dedupe_leading_subhead(blocks: List[Dict], title: str) -> List[Dict]:
    """Elimina el PRIMER bloque de texto tipo 'subhead' si repite el título de la sección
    (evita el titular duplicado bajo la cabecera). Se aplica a todos los documentos."""
    if not blocks or not title:
        return blocks
    b0 = blocks[0]
    if b0.get("block_type") == "text" and (b0.get("data") or {}).get("style") == "subhead":
        nt, nsub = _norm_title(title), _norm_title((b0.get("data") or {}).get("content"))
        if nsub and (nsub == nt or nt.startswith(nsub) or nsub.startswith(nt)):
            return blocks[1:]
    return blocks


def _render_flow(doc: Dict, brand, t, c, cov, hf, bf) -> str:
    """Documento en VERTICAL A4 (p. ej. el Teaser). Usa los mismos bloques y estilo que el
    infomemo (marca, tarjetas, gráficos) pero apilados en una columna A4, con paleta legible
    sobre fondo blanco. La portada/cierre conservan el fondo de marca (negro en bud)."""
    cpal = _content_palette(c)
    def pcol(k, d="#000"):
        return cpal.get(k, d)
    A4_W = 794  # A4 a 96 dpi
    parts = []
    for section in doc.get("sections", []):
        blocks = section.get("blocks", [])
        cover = next((b for b in blocks if b.get("block_type") == "cover"), None)
        is_black = bool(cover) or section.get("slide_kind") in ("separator", "closing")
        if cover:
            # Portada/cierre a ancho completo con el fondo de marca.
            parts.append(f'<div style="max-width:{A4_W}px;margin:0 auto 18px;">'
                         f'{_cover_html(cover.get("data", {}), brand, cov, hf, bf, big=True)}</div>')
            continue
        head = (f'<div style="font:700 18px {hf};color:{pcol("text_primary","#111")};'
                f'border-bottom:2px solid {pcol("accent","#c00")};padding-bottom:6px;'
                f'margin:24px 0 12px;">{_esc(section.get("title"))}</div>')
        blocks = _dedupe_leading_subhead(blocks, section.get("title"))
        parts.append(f'<div style="max-width:{A4_W}px;margin:0 auto;">{head}'
                     f'{_section_blocks_html(blocks, cpal, hf, bf, in_slide=False)}</div>')
    body = "".join(parts)
    return _page_shell(f'<div style="max-width:{A4_W}px;margin:0 auto;">{body}</div>', "#ffffff")


def _content_palette(c: Dict) -> Dict:
    """Paleta LEGIBLE para las páginas de contenido (fondo gris claro), independiente del
    tema de marca (que puede ser oscuro). Conserva el color de acento de la marca para
    líneas, bordes y cabeceras de tabla."""
    accent = c.get("accent", "#F3D200")
    return {
        "text_primary": "#1b1b1b", "text_secondary": "#4a4a4a", "text_muted": "#7a7a7a",
        "kpi_value": "#1b1b1b", "kpi_bg": "#FFFFFF", "kpi_label": "#6a6a6a",
        "accent": accent,
        "table_header_bg": accent, "table_header_text": "#000000",
        "table_row_alt": "#F2F3F5",
        "bg_surface": "#F4F5F7", "bg_danger": "#FDECEC", "border_light": "#E2E4E8",
    }


def _render_slides(doc: Dict, brand, t, c, cov, hf, bf, start_no: int = 1, total: int = None) -> str:
    def col(k, d="#000"):
        return c.get(k, d)
    cpal = _content_palette(c)

    def pcol(k, d="#000"):
        return cpal.get(k, d)
    # Small brand logotype (dark variant for the light content pages); text fallback if it fails.
    corner_logo = _logo_markup(brand, 18, "#1b1b1b", bf, prefer="dark")
    advisor = brand.get("name") or "el Asesor Financiero"
    sections = doc.get("sections", [])
    total = total or len(sections)
    slides = ""
    for local, section in enumerate(sections):
        page_no = start_no + local
        blocks = section.get("blocks", [])
        cover = next((b for b in blocks if b.get("block_type") == "cover"), None)
        if section.get("slide_kind") == "separator":
            accent = cov.get("brand_text", "#F3D200")
            sep_logo = _logo_markup(brand, 26, cov.get("text", "#fff"), bf, prefer="light")
            num = section.get("section_number")
            num_html = (f'<div style="font:600 10px {bf};color:{accent};letter-spacing:3px;margin-bottom:6px;">'
                        f'SECCIÓN {_esc(num)}</div>' if num else "")
            title_html = (f'<div style="font:500 22px {hf};color:{cov.get("text","#fff")};line-height:1.15;'
                          f'letter-spacing:.3px;white-space:nowrap;">{_esc(section.get("title"))}</div>')
            bar = f'<div style="width:48px;height:2px;background:{accent};border-radius:2px;margin-top:12px;"></div>'
            inner = (f'<div style="position:absolute;top:34px;right:44px;">{sep_logo}</div>'
                     f'<div style="position:absolute;left:64px;bottom:96px;">{num_html}{title_html}{bar}</div>')
        elif cover:
            inner = _cover_html(cover.get("data", {}), brand, cov, hf, bf, big=True)
        else:
            head = (f'<div style="font:600 24px {hf};color:{pcol("text_primary","#111")};'
                    f'border-bottom:1px solid {pcol("accent","#c00")};padding-bottom:10px;margin-bottom:16px;letter-spacing:.2px;">{_esc(section.get("title"))}</div>')
            tag = f'<div style="position:absolute;top:18px;right:34px;">{corner_logo}</div>'
            body = _section_blocks_html(_dedupe_leading_subhead(blocks, section.get("title")), cpal, hf, bf, in_slide=True)
            footer = (f'<div style="position:absolute;bottom:0;left:0;right:0;height:28px;display:flex;align-items:center;'
                      f'justify-content:space-between;padding:0 46px;border-top:1px solid rgba(0,0,0,0.08);'
                      f'font:400 9px {bf};color:{pcol("text_muted","#999")};">'
                      f'<span>Información confidencial · Prohibida su reproducción o distribución sin autorización de {_esc(advisor)}</span>'
                      f'<span>{page_no} / {total}</span></div>')
            inner = f'<div style="height:100%;padding:32px 46px 40px;box-sizing:border-box;overflow:hidden;">{tag}{head}{body}</div>{footer}'
        # Fondos: portada / separadores / cierre en negro; páginas de contenido en gris (como las cards).
        is_black = bool(cover) or section.get("slide_kind") in ("separator", "closing")
        slide_bg = "#0b0b0b" if is_black else "#E7E9EC"
        # Medidas estándar de diapositiva (1280×720, formato PPT) para todas las páginas.
        slides += (f'<div class="slide" style="position:relative;width:1280px;height:720px;background:{slide_bg};'
                   f'margin:0 auto 26px;box-shadow:0 4px 24px rgba(0,0,0,.16);border-radius:6px;overflow:hidden;">{inner}</div>')
    return _page_shell(slides, "#dfe1e4")


def render_html(doc: Dict, brand: Dict, layout: str = None, page_meta=None) -> str:
    """page_meta = (start_no, total) lets a single-section preview show its real page
    number within the full document; None = number this doc's own sections from 1."""
    t = brand.get("tokens", {})
    c = t.get("colors", {})
    cov = t.get("cover", {})
    hf = t.get("fonts", {}).get("heading", "'Inter',sans-serif")
    bf = t.get("fonts", {}).get("body", "'Inter',sans-serif")
    lay = layout or _layout_for(doc)
    if lay == "slides":
        start_no, total = page_meta if page_meta else (1, None)
        return _render_slides(doc, brand, t, c, cov, hf, bf, start_no=start_no, total=total)
    return _render_flow(doc, brand, t, c, cov, hf, bf)
