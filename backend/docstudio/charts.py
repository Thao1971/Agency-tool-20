"""Librería de gráficos SVG puros para el Document Studio.

SVG estático (sin JavaScript) para que rendericen igual en la previsualización HTML y en
el export a PDF (WeasyPrint). Cada función es pura y recibe los colores del tema, así se
adaptan a la paleta de la página (clara/oscura). Tipos: barras, donut, scatter, línea.

El renderer (`html_render`) despacha el bloque `chart` por `chart_type` a estas funciones.
"""

from __future__ import annotations

import html as _h
import math
from typing import Dict, List, Optional

# Paleta categórica (coherente con el resto de documentos).
PALETTE = ["#1D9E75", "#EF9F27", "#E24B4A", "#378ADD", "#7F77DD", "#D4537E", "#888780"]


def _esc(s) -> str:
    return _h.escape(str(s)) if s is not None else ""


def _es_num(v: float, dec: int = 0) -> str:
    return f"{v:,.{dec}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# ── BARRAS ────────────────────────────────────────────────────────────
def bar_chart(bars: List[Dict], accent: str, bf: str, fmt=None, ref_lines: Optional[List[Dict]] = None,
              width: int = 560, height: int = 230) -> str:
    """bars: [{label, value}]. ref_lines: [{value_x_frac(0-1), label, dashed}] (marcadores verticales)."""
    bars = [b for b in bars if b.get("value") is not None]
    if not bars:
        return ""
    fmt = fmt or (lambda v: _es_num(v))
    pad_l, pad_b, pad_t, pad_r = 44, 34, 22, 14
    pw, ph = width - pad_l - pad_r, height - pad_b - pad_t
    mx = max(b["value"] for b in bars) or 1
    n = len(bars)
    gap = 10
    slot = (pw - gap * (n - 1)) / n            # espacio por columna
    bw = min(slot, 72)                          # ancho de barra acotado (barras finas, como en Contexto)
    slot_off = (slot - bw) / 2                  # centrar la barra en su hueco
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    # eje Y (3 gridlines)
    for i in range(4):
        gy = pad_t + ph * i / 3
        val = mx * (3 - i) / 3
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width-pad_r}" y2="{gy:.1f}" stroke="#E2E4E8" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-6}" y="{gy+3:.1f}" text-anchor="end" font-size="9" fill="#8a8a8a">{_esc(fmt(val))}</text>')
    # barras
    for i, b in enumerate(bars):
        bh = (b["value"] / mx) * ph
        x = pad_l + i * (slot + gap) + slot_off
        y = pad_t + ph - bh
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{accent}"/>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{pad_t+ph+13:.1f}" text-anchor="middle" font-size="9" fill="#5a5a5a">{_esc(b.get("label",""))}</text>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{y-4:.1f}" text-anchor="middle" font-size="9" font-weight="700" fill="#3a3a3a">{_esc(fmt(b["value"]))}</text>')
    # líneas de referencia verticales (etiquetas escalonadas para no solaparse)
    for _ri, rl in enumerate(ref_lines or []):
        xf = rl.get("value_x_frac")
        if xf is None:
            continue
        x = pad_l + pw * min(max(xf, 0), 1)
        dash = 'stroke-dasharray="4 3"' if rl.get("dashed") else ''
        parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t+ph}" stroke="#333" stroke-width="1.3" {dash}/>')
        if rl.get("label"):
            near_right = xf > 0.72
            tx = x - 4 if near_right else x + 4
            anchor = "end" if near_right else "start"
            ly = pad_t + 9 + (_ri % 2) * 13   # escalona: 1ª arriba, 2ª un poco más abajo
            parts.append(f'<text x="{tx:.1f}" y="{ly}" text-anchor="{anchor}" font-size="9" '
                         f'font-weight="700" fill="#333">{_esc(rl["label"])}</text>')
    parts.append('</svg>')
    return "".join(parts)


# ── DONUT ─────────────────────────────────────────────────────────────
def donut_chart(segments: List[Dict], bf: str, width: int = 460, height: int = 250) -> str:
    """segments: [{label, value, color?}]. Anillo centrado con leyenda horizontal debajo
    ("Etiqueta: N"), como el 'Perfil de Riesgo Sectorial'."""
    segs = [s for s in segments if (s.get("value") or 0) > 0]
    if not segs:
        return ""
    total = sum(s["value"] for s in segs)
    cx, cy, r, sw = width / 2, 108, 78, 30
    circ = 2 * math.pi * r
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    off = 0.0
    for i, s in enumerate(segs):
        frac = s["value"] / total
        color = s.get("color") or PALETTE[i % len(PALETTE)]
        seg_len = frac * circ
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-dasharray="{seg_len:.2f} {circ-seg_len:.2f}" stroke-dashoffset="{-off:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>')
        off += seg_len
    # leyenda horizontal centrada debajo
    labels = [f'{s["label"]}: {_es_num(s["value"])}' for s in segs]
    approx_w = [len(x) * 6.4 + 20 for x in labels]
    total_w = sum(approx_w) + 14 * (len(segs) - 1)
    lx = max(10, (width - total_w) / 2)
    ly = cy + r + 34
    for i, s in enumerate(segs):
        color = s.get("color") or PALETTE[i % len(PALETTE)]
        parts.append(f'<circle cx="{lx+6:.0f}" cy="{ly-4:.0f}" r="6" fill="{color}"/>')
        parts.append(f'<text x="{lx+18:.0f}" y="{ly:.0f}" font-size="11.5" fill="#3a3a3a">{_esc(labels[i])}</text>')
        lx += approx_w[i] + 14
    parts.append('</svg>')
    return "".join(parts)


# ── SCATTER ───────────────────────────────────────────────────────────
def scatter_chart(points: List[Dict], bf: str, x_label: str = "", y_label: str = "",
                  med_x: Optional[float] = None, med_y: Optional[float] = None,
                  x_fmt=None, y_fmt=None, width: int = 560, height: int = 300) -> str:
    """points: [{x, y, group?, highlight?}]. Colorea por grupo; marca medianas de cuadrante."""
    pts = [p for p in points if p.get("x") is not None and p.get("y") is not None]
    if not pts:
        return ""
    x_fmt = x_fmt or (lambda v: _es_num(v))
    y_fmt = y_fmt or (lambda v: _es_num(v))
    pad_l, pad_b, pad_t, pad_r = 48, 34, 18, 16
    pw, ph = width - pad_l - pad_r, height - pad_b - pad_t
    xs = [p["x"] for p in pts]; ys = [p["y"] for p in pts]
    xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys)
    xr = (xmax - xmin) or 1; yr = (ymax - ymin) or 1

    def px(x): return pad_l + (x - xmin) / xr * pw
    def py(y): return pad_t + ph - (y - ymin) / yr * ph

    groups = {}
    for i, g in enumerate(sorted({p.get("group", "") for p in pts})):
        groups[g] = PALETTE[i % len(PALETTE)]
    # Coloreado por CUADRANTE respecto a las medianas (como el "Mapa de Eficiencia"):
    # verde = arriba-izq, azul = arriba-dcha, naranja = abajo-dcha, gris = abajo-izq.
    quad = med_x is not None and med_y is not None
    def _qcolor(x, y):
        top = y >= med_y
        right = x >= med_x
        if top and not right: return "#1D9E75"
        if top and right: return "#378ADD"
        if (not top) and right: return "#EF9F27"
        return "#9AA0A6"
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    # marco
    parts.append(f'<rect x="{pad_l}" y="{pad_t}" width="{pw}" height="{ph}" fill="none" stroke="#E2E4E8"/>')
    # medianas de cuadrante
    if med_x is not None and xmin <= med_x <= xmax:
        parts.append(f'<line x1="{px(med_x):.1f}" y1="{pad_t}" x2="{px(med_x):.1f}" y2="{pad_t+ph}" stroke="#BA7517" stroke-width="1" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{px(med_x)+3:.1f}" y="{pad_t+10}" font-size="9" fill="#BA7517">Med. {_esc(x_fmt(med_x))}</text>')
    if med_y is not None and ymin <= med_y <= ymax:
        parts.append(f'<line x1="{pad_l}" y1="{py(med_y):.1f}" x2="{pad_l+pw}" y2="{py(med_y):.1f}" stroke="#BA7517" stroke-width="1" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{pad_l+pw-2:.1f}" y="{py(med_y)-3:.1f}" text-anchor="end" font-size="9" fill="#BA7517">Med. {_esc(y_fmt(med_y))}</text>')
    # puntos (color por cuadrante si hay medianas; si no, por grupo) + etiqueta de nombre
    def _clip(s, n=22):
        s = str(s)
        return s if len(s) <= n else s[: n - 1] + "…"
    for p in pts:
        c = _qcolor(p["x"], p["y"]) if quad else groups.get(p.get("group", ""), PALETTE[0])
        cx, cy = px(p["x"]), py(p["y"])
        hl = p.get("highlight")
        if hl:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{c}" stroke="#111" stroke-width="2"/>')
        else:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{c}" fill-opacity="0.72"/>')
        lbl = p.get("label")
        if lbl:
            # etiqueta a la derecha del punto; si está muy a la derecha, a la izquierda
            right = cx < pad_l + pw * 0.72
            tx = cx + (8 if right else -8)
            anchor = "start" if right else "end"
            parts.append(
                f'<text x="{tx:.1f}" y="{cy + 3:.1f}" text-anchor="{anchor}" '
                f'font-size="{9.5 if hl else 8}" fill="{"#111" if hl else "#6b6f76"}" '
                f'font-weight="{700 if hl else 400}">{_esc(_clip(lbl))}</text>')
    # ejes min/max
    parts.append(f'<text x="{pad_l}" y="{height-8}" font-size="9" fill="#8a8a8a">{_esc(x_fmt(xmin))}</text>')
    parts.append(f'<text x="{pad_l+pw:.0f}" y="{height-8}" text-anchor="end" font-size="9" fill="#8a8a8a">{_esc(x_fmt(xmax))}</text>')
    if x_label:
        parts.append(f'<text x="{pad_l+pw/2:.0f}" y="{height-8}" text-anchor="middle" font-size="9.5" fill="#5a5a5a">{_esc(x_label)}</text>')
    parts.append(f'<text x="6" y="{pad_t+ph:.0f}" font-size="9" fill="#8a8a8a">{_esc(y_fmt(ymin))}</text>')
    parts.append(f'<text x="6" y="{pad_t+8:.0f}" font-size="9" fill="#8a8a8a">{_esc(y_fmt(ymax))}</text>')
    if y_label:
        parts.append(f'<text transform="translate(11 {pad_t+ph/2:.0f}) rotate(-90)" text-anchor="middle" font-size="9.5" fill="#5a5a5a">{_esc(y_label)}</text>')
    parts.append('</svg>')
    return "".join(parts)


# ── LÍNEA ─────────────────────────────────────────────────────────────
def line_chart(points: List[Dict], accent: str, bf: str, value_key: str = "value",
               label_key: str = "label", fmt=None, width: int = 560, height: int = 220) -> str:
    """points: [{label, <value_key>}]."""
    pts = [p for p in points if p.get(value_key) is not None]
    if len(pts) < 2:
        return ""
    fmt = fmt or (lambda v: _es_num(v))
    pad_l, pad_b, pad_t, pad_r = 46, 32, 22, 14
    pw, ph = width - pad_l - pad_r, height - pad_b - pad_t
    vals = [p[value_key] for p in pts]
    _raw_mx, mn = max(vals), min(0, min(vals))
    mx = _raw_mx + (_raw_mx - mn) * 0.15  # margen superior para que las etiquetas no toquen el eje
    rng = (mx - mn) or 1
    n = len(pts)

    def X(i): return pad_l + (pw * i / (n - 1) if n > 1 else 0)
    def Y(v): return pad_t + ph - (v - mn) / rng * ph

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    for i in range(4):
        gy = pad_t + ph * i / 3
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width-pad_r}" y2="{gy:.1f}" stroke="#E2E4E8"/>')
        parts.append(f'<text x="{pad_l-6}" y="{gy+3:.1f}" text-anchor="end" font-size="9" fill="#8a8a8a">{_esc(fmt(mx-(mx-mn)*i/3))}</text>')
    poly = " ".join(f"{X(i):.1f},{Y(p[value_key]):.1f}" for i, p in enumerate(pts))
    parts.append(f'<polyline points="{poly}" fill="none" stroke="{accent}" stroke-width="2.5"/>')
    for i, p in enumerate(pts):
        anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
        tx = X(i) + (3 if i == 0 else (-3 if i == n - 1 else 0))
        parts.append(f'<circle cx="{X(i):.1f}" cy="{Y(p[value_key]):.1f}" r="3.5" fill="{accent}"/>')
        parts.append(f'<text x="{tx:.1f}" y="{Y(p[value_key])-7:.1f}" text-anchor="{anchor}" font-size="9" font-weight="700" fill="#3a3a3a">{_esc(fmt(p[value_key]))}</text>')
        parts.append(f'<text x="{X(i):.1f}" y="{pad_t+ph+13:.1f}" text-anchor="middle" font-size="9" fill="#5a5a5a">{_esc(p.get(label_key,""))}</text>')
    parts.append('</svg>')
    return "".join(parts)


def grouped_bar_chart(categories: List[str], series: List[Dict], bf: str, fmt=None,
                      width: int = 560, height: int = 240) -> str:
    """categories: [str]; series: [{name, color?, values:[...]}] (2-3 series). Barras agrupadas."""
    series = [s for s in series if s.get("values")]
    if not categories or not series:
        return ""
    fmt = fmt or (lambda v: _es_num(v))
    pad_l, pad_b, pad_t, pad_r = 52, 40, 26, 14
    pw, ph = width - pad_l - pad_r, height - pad_b - pad_t
    allv = [v for s in series for v in s["values"] if v is not None]
    mx = max(allv + [0]); mn = min(allv + [0])
    rng = (mx - mn) or 1
    # línea de base (cero) — soporta valores negativos (p. ej. fondo de maniobra negativo)
    y0 = pad_t + ph - (0 - mn) / rng * ph
    nser = len(series)
    ncat = len(categories)
    gcat = 16
    cat_w = (pw - gcat * (ncat - 1)) / ncat
    bw = cat_w / nser
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    for i in range(4):
        gy = pad_t + ph * i / 3
        val = mx - rng * i / 3
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width-pad_r}" y2="{gy:.1f}" stroke="#E2E4E8"/>')
        parts.append(f'<text x="{pad_l-6}" y="{gy+3:.1f}" text-anchor="end" font-size="9" fill="#8a8a8a">{_esc(fmt(val))}</text>')
    # eje cero resaltado
    parts.append(f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{width-pad_r}" y2="{y0:.1f}" stroke="#9AA0A6" stroke-width="1.2"/>')
    for ci, cat in enumerate(categories):
        cx = pad_l + ci * (cat_w + gcat)
        for si, s in enumerate(series):
            v = s["values"][ci] if ci < len(s["values"]) else None
            if v is None:
                continue
            vy = pad_t + ph - (v - mn) / rng * ph
            y = min(vy, y0); bh = abs(vy - y0)
            x = cx + si * bw
            color = s.get("color") or PALETTE[si % len(PALETTE)]
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw-2:.1f}" height="{max(bh,0.5):.1f}" rx="2" fill="{color}"/>')
            ty = (y - 3) if v >= 0 else (y + bh + 9)
            parts.append(f'<text x="{x+(bw-2)/2:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="8" fill="#3a3a3a">{_esc(fmt(v))}</text>')
        parts.append(f'<text x="{cx+cat_w/2:.1f}" y="{pad_t+ph+13:.1f}" text-anchor="middle" font-size="9" fill="#5a5a5a">{_esc(cat)}</text>')
    # leyenda
    lx = pad_l
    for si, s in enumerate(series):
        color = s.get("color") or PALETTE[si % len(PALETTE)]
        parts.append(f'<rect x="{lx:.0f}" y="{height-12}" width="10" height="10" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{lx+14:.0f}" y="{height-3}" font-size="9.5" fill="#3a3a3a">{_esc(s.get("name",""))}</text>')
        lx += 18 + len(s.get("name", "")) * 6.2
    parts.append('</svg>')
    return "".join(parts)


def waterfall_chart(items: List[Dict], bf: str, fmt=None, width: int = 620, height: int = 260) -> str:
    """Puente/cascada (p. ej. EBITDA bridge). items: [{label, value, type}] con
    type in {start, delta, total}. Los deltas a 0 se muestran como marcador punteado
    (placeholder) para que el asesor vea el layout definitivo antes de rellenar importes."""
    items = [i for i in items if i.get("label")]
    if not items:
        return ""
    fmt = fmt or (lambda v: _es_num(v))
    pad_l, pad_b, pad_t, pad_r = 54, 46, 24, 14
    pw, ph = width - pad_l - pad_r, height - pad_b - pad_t
    # niveles acumulados
    run = 0.0
    levels = []  # (base, top, kind, value)
    for it in items:
        k = it.get("type", "delta"); v = it.get("value") or 0
        if k in ("start", "total"):
            levels.append((0, v, k, v)); run = v
        else:
            levels.append((run, run + v, "delta", v)); run += v
    tops = [max(b, t) for b, t, _, _ in levels] + [0]
    mx = max(tops) or 1
    n = len(items)
    gap = 14
    slot = (pw - gap * (n - 1)) / n
    bw = min(slot, 70)
    off = (slot - bw) / 2

    def Y(v): return pad_t + ph - (v / mx) * ph
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    parts.append(f'<line x1="{pad_l}" y1="{pad_t+ph:.1f}" x2="{width-pad_r}" y2="{pad_t+ph:.1f}" stroke="#C9CCD1"/>')
    prev_x2 = None
    for i, ((base, top, kind, val), it) in enumerate(zip(levels, items)):
        x = pad_l + i * (slot + gap) + off
        y = Y(max(base, top)); h = abs(Y(base) - Y(top))
        if kind == "start" or kind == "total":
            color = "#2b2b2b"
        else:
            color = "#1D9E75" if val > 0 else ("#E24B4A" if val < 0 else "#C9CCD1")
        if kind == "delta" and val == 0:
            # placeholder punteado (layout a completar por el asesor)
            yb = Y(0)
            parts.append(f'<rect x="{x:.1f}" y="{yb-40:.1f}" width="{bw:.1f}" height="40" rx="3" fill="none" '
                         f'stroke="#B9BdC3" stroke-width="1.2" stroke-dasharray="4 3"/>')
            parts.append(f'<text x="{x+bw/2:.1f}" y="{yb-16:.1f}" text-anchor="middle" font-size="9" fill="#9AA0A6">[·]</text>')
        else:
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(h,1):.1f}" rx="2" fill="{color}"/>')
            parts.append(f'<text x="{x+bw/2:.1f}" y="{y-4:.1f}" text-anchor="middle" font-size="9" font-weight="700" fill="#3a3a3a">{_esc(fmt(val))}</text>')
        # conector punteado entre pasos
        if prev_x2 is not None and kind == "delta":
            parts.append(f'<line x1="{prev_x2:.1f}" y1="{Y(base):.1f}" x2="{x:.1f}" y2="{Y(base):.1f}" stroke="#C9CCD1" stroke-dasharray="3 2"/>')
        prev_x2 = x + bw
        # etiqueta (envuelta en 2 líneas si es larga)
        lbl = str(it["label"])
        parts.append(f'<text x="{x+bw/2:.1f}" y="{pad_t+ph+14:.1f}" text-anchor="middle" font-size="8.5" fill="#5a5a5a">{_esc(lbl[:18])}</text>')
        if len(lbl) > 18:
            parts.append(f'<text x="{x+bw/2:.1f}" y="{pad_t+ph+25:.1f}" text-anchor="middle" font-size="8.5" fill="#5a5a5a">{_esc(lbl[18:34])}</text>')
    parts.append('</svg>')
    return "".join(parts)


# ── RADAR ─────────────────────────────────────────────────────────────
def radar_chart(axes: List[str], series: List[Dict], bf: str, accent: str = "#378ADD",
                max_value: float = 100.0, width: int = 460, height: int = 300) -> str:
    """axes: ['Quality Score','Margen EBITDA',...]. series: [{name, color?, values:[...]}].
    Valores en escala 0..max_value (por defecto percentiles 0-100). Polígono por serie,
    rejilla concéntrica y etiquetas de eje. Pensado para 'Empresa vs Mediana categoría'."""
    axes = [a for a in (axes or []) if a]
    series = [s for s in (series or []) if s.get("values")]
    n = len(axes)
    if n < 3 or not series:
        return ""
    cx, cy = width / 2, height / 2 + 6
    r = min(width, height) / 2 - 46
    import math as _m
    def _pt(i, frac):
        ang = -_m.pi / 2 + 2 * _m.pi * i / n
        return (cx + r * frac * _m.cos(ang), cy + r * frac * _m.sin(ang))
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    # rejilla concéntrica (4 anillos)
    for ring in range(1, 5):
        frac = ring / 4
        poly = " ".join(f"{_pt(i, frac)[0]:.1f},{_pt(i, frac)[1]:.1f}" for i in range(n))
        parts.append(f'<polygon points="{poly}" fill="none" stroke="#E2E4E8" stroke-width="1"/>')
    # radios + etiquetas de eje
    for i, ax in enumerate(axes):
        ex, ey = _pt(i, 1.0)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#E2E4E8" stroke-width="1"/>')
        lx, ly = _pt(i, 1.16)
        anchor = "middle"
        if lx < cx - 6: anchor = "end"
        elif lx > cx + 6: anchor = "start"
        parts.append(f'<text x="{lx:.1f}" y="{ly+3:.1f}" text-anchor="{anchor}" font-size="9.5" fill="#5a5a5a">{_esc(ax)}</text>')
    # series
    for si, s in enumerate(series):
        color = s.get("color") or (accent if si == 0 else PALETTE[(si + 1) % len(PALETTE)])
        vals = s.get("values") or []
        poly = []
        for i in range(n):
            v = vals[i] if i < len(vals) and vals[i] is not None else 0
            frac = min(max(float(v) / max_value, 0), 1)
            px, py = _pt(i, frac)
            poly.append(f"{px:.1f},{py:.1f}")
        dash = 'stroke-dasharray="5 3"' if si > 0 else ''
        parts.append(f'<polygon points="{" ".join(poly)}" fill="{color}" fill-opacity="{0.16 if si==0 else 0.05}" '
                     f'stroke="{color}" stroke-width="2" {dash}/>')
        for p in poly:
            x, y = p.split(",")
            parts.append(f'<circle cx="{x}" cy="{y}" r="2.6" fill="{color}"/>')
    # leyenda
    lx = 14; ly = height - 8
    for si, s in enumerate(series):
        color = s.get("color") or (accent if si == 0 else PALETTE[(si + 1) % len(PALETTE)])
        parts.append(f'<circle cx="{lx+5:.0f}" cy="{ly-4:.0f}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{lx+15:.0f}" y="{ly:.0f}" font-size="11" fill="#3a3a3a">{_esc(s.get("name",""))}</text>')
        lx += 15 + len(str(s.get("name",""))) * 6.6 + 18
    parts.append('</svg>')
    return "".join(parts)


# ── CÍRCULOS CONCÉNTRICOS (TAM/SAM/SOM) ───────────────────────────────
def nested_circles_chart(items: List[Dict], bf: str, accent: str = "#BA7517",
                         core: str = "#111111", width: int = 460, height: int = 340) -> str:
    """items (de mayor a menor): [{label, sublabel?, frac(0-1), dashed?}].
    Dibuja círculos concéntricos apoyados en la base (estilo TAM/SAM/SOM) con los colores de
    la MARCA: anillos en el color de acento y núcleo interior sólido. El radio es proporcional
    a `frac`; las etiquetas se apilan dentro de cada anillo."""
    items = [i for i in (items or []) if i.get("frac")]
    if not items:
        return ""
    items = sorted(items, key=lambda i: -i["frac"])
    max_r = min(width, height) / 2 - 8
    cx = width / 2
    base_y = height - 6           # todos los círculos comparten la base inferior
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    for idx, it in enumerate(items):
        r = max_r * min(max(it["frac"], 0.05), 1)
        cy = base_y - r
        is_inner = (idx == len(items) - 1)
        if is_inner:                # el más pequeño: disco sólido (núcleo de marca)
            parts.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="{core}"/>')
            tcol = "#ffffff"
            ly = cy + 2
        else:                       # anillos en color de acento (marca)
            dash = 'stroke-dasharray="6 5"' if it.get("dashed") else ''
            parts.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="none" stroke="{accent}" stroke-width="2.5" {dash}/>')
            tcol = "#3a3a3a"
            ly = cy - r + 26
        parts.append(f'<text x="{cx:.0f}" y="{ly:.0f}" text-anchor="middle" font-size="15" font-weight="700" fill="{tcol}">{_esc(it.get("label",""))}</text>')
        if it.get("sublabel"):
            parts.append(f'<text x="{cx:.0f}" y="{ly+16:.0f}" text-anchor="middle" font-size="11" fill="{tcol}">{_esc(it["sublabel"])}</text>')
    parts.append('</svg>')
    return "".join(parts)


# ── GAUGE / TERMÓMETRO HORIZONTAL (p. ej. HHI 0–10.000) ────────────────
def _mix(hex_color: str, other: str, t: float) -> str:
    """Mezcla lineal de dos colores hex (t=0 -> hex_color, t=1 -> other)."""
    def rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    try:
        a, b = rgb(hex_color), rgb(other)
    except Exception:
        return hex_color
    m = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return "#%02X%02X%02X" % m


def gauge_chart(value: float, vmin: float, vmax: float, zones: List[Dict], bf: str,
                accent: str = "#F3D200", ink: str = "#1A1A1A",
                value_label: str = "", ticks: Optional[List[float]] = None,
                width: int = 640, height: int = 122) -> str:
    """Barra horizontal con zonas en color de MARCA (rampa del acento hacia el tono oscuro,
    a mayor valor mayor intensidad) y un marcador en `value`. zones: [{to, label}]."""
    if value is None:
        return ""
    span = (vmax - vmin) or 1
    pad_l, pad_r, track_y, track_h = 22, 22, 46, 16
    tw = width - pad_l - pad_r
    n = max(len(zones), 1)

    def _fx(v):
        return pad_l + tw * (min(max(v, vmin), vmax) - vmin) / span

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="{bf}">']
    prev = vmin
    for i, z in enumerate(zones):
        x0, x1 = _fx(prev), _fx(z["to"])
        # Rampa de marca: acento claro -> acento -> acento oscuro/tinta
        t = i / max(n - 1, 1)
        base = _mix("#FFFFFF", accent, 0.55) if t == 0 else (accent if t < 0.999 else _mix(accent, ink, 0.55))
        parts.append(f'<rect x="{x0:.1f}" y="{track_y}" width="{max(0,x1-x0):.1f}" height="{track_h}" fill="{base}"/>')
        if z.get("label"):
            parts.append(f'<text x="{(x0+x1)/2:.1f}" y="{track_y+track_h+12:.0f}" text-anchor="middle" '
                         f'font-size="7.5" fill="#6b6b6b">{_esc(z["label"])}</text>')
        prev = z["to"]
    # ticks (valores de escala)
    for t in (ticks or [vmin, vmax]):
        tx = _fx(t)
        parts.append(f'<line x1="{tx:.1f}" y1="{track_y+track_h}" x2="{tx:.1f}" y2="{track_y+track_h+3}" stroke="#9a9a9a" stroke-width="1"/>')
        parts.append(f'<text x="{tx:.1f}" y="{track_y+track_h+26:.0f}" text-anchor="middle" font-size="7.5" fill="#9a9a9a">{_es_num(t)}</text>')
    # marcador (triángulo + línea + etiqueta)
    mx = _fx(value)
    parts.append(f'<line x1="{mx:.1f}" y1="{track_y-6}" x2="{mx:.1f}" y2="{track_y+track_h+2}" stroke="{ink}" stroke-width="2"/>')
    parts.append(f'<path d="M{mx-6:.1f},{track_y-6} L{mx+6:.1f},{track_y-6} L{mx:.1f},{track_y+2} Z" fill="{ink}"/>')
    if value_label:
        anchor = "middle"
        lx = mx
        if mx < pad_l + 40: anchor, lx = "start", pad_l
        elif mx > width - pad_r - 40: anchor, lx = "end", width - pad_r
        parts.append(f'<text x="{lx:.1f}" y="{track_y-12:.0f}" text-anchor="{anchor}" font-size="12.5" font-weight="700" fill="{ink}">{_esc(value_label)}</text>')
    parts.append('</svg>')
    return "".join(parts)


def render_chart(chart_type: str, data: Dict, accent: str, bf: str) -> str:
    """Dispatch por tipo. `data` es el dict del bloque chart (data)."""
    ct = (chart_type or "bar").lower()
    ds = data.get("dataset") or data
    if ct == "gauge":
        return gauge_chart(ds.get("value"), ds.get("min", 0), ds.get("max", 10000),
                           ds.get("zones") or [], bf, accent=accent, ink=ds.get("ink", "#1A1A1A"),
                           value_label=ds.get("value_label", ""), ticks=ds.get("ticks"))
    if ct in ("nested_circles", "tam_sam_som", "nested"):
        return nested_circles_chart(ds.get("items") or [], bf, accent, core=ds.get("core", "#111111"))
    if ct == "radar":
        return radar_chart(ds.get("axes") or [], ds.get("series") or [], bf, accent,
                           max_value=ds.get("max_value", 100.0))
    if ct == "donut" or ct == "pie":
        return donut_chart(ds.get("segments") or [], bf)
    if ct == "scatter":
        return scatter_chart(ds.get("points") or [], bf, ds.get("x_label", ""), ds.get("y_label", ""),
                             ds.get("med_x"), ds.get("med_y"),
                             x_fmt=_fmt_from(ds.get("x_fmt")), y_fmt=_fmt_from(ds.get("y_fmt")))
    if ct == "line":
        return line_chart(ds.get("points") or [], accent, bf, ds.get("value_key", "value"),
                          fmt=_fmt_from(ds.get("fmt")))
    if ct in ("grouped_bar", "grouped"):
        return grouped_bar_chart(ds.get("categories") or [], ds.get("series") or [], bf,
                                 fmt=_fmt_from(ds.get("fmt")))
    if ct in ("waterfall", "bridge"):
        return waterfall_chart(ds.get("items") or [], bf, fmt=_fmt_from(ds.get("fmt")))
    # bar (default)
    return bar_chart(ds.get("bars") or [], accent, bf, fmt=_fmt_from(ds.get("fmt")),
                     ref_lines=ds.get("ref_lines"))


def _fmt_from(name: Optional[str]):
    if name == "pct":
        return lambda v: _es_num(v * 100, 1) + " %"
    if name == "pct_raw":
        return lambda v: _es_num(v, 1) + " %"
    if name == "millions":
        return lambda v: _es_num(v / 1e6, 1) + " M€"
    if name == "eur":
        return lambda v: _es_num(v) + " €"
    return None
