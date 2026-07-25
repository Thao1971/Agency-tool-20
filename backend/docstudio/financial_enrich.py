"""Financial enrichment for the Document Studio — curated by an M&A analyst lens.

The Financial Intelligence Engine already computes, per company, a full ratio set
(`ratios_library.compute_all`, 13 ratios with an `available` flag), a multi-year
`evolution` series, a `financial_quality` score and honest `comparables`. The old
composers surfaced only ~6 KPIs. This module turns the SAME real bundle into the
richer financial content a "cuaderno de venta" (sales memorandum) needs, and adds a
sector positioning table built from OUR OWN data (percentiles across master_companies
of the same CNAE) — never external/licensed market reports we don't have.

Honesty rules (unchanged from the engines):
- A ratio is shown ONLY when the engine marks it `available` (its inputs exist). Ratios
  that need account lines not currently stored (gross margin, liquidity, interest
  coverage, financial debt/EBITDA) are simply omitted — never invented or approximated.
- Sector percentiles are computed from real peers; if too few peers, the block is skipped.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Callable

from models import now_iso
from docstudio import table_block, kpi_block, text_block

_FIN = "financial-intelligence-v1"

# ── formatting ────────────────────────────────────────────────────────
_CATEGORY_ES = {
    "profitability": "Rentabilidad",
    "liquidity": "Liquidez",
    "solvency": "Solvencia",
    "efficiency": "Eficiencia",
    "working_capital": "Circulante",
}

# How each ratio key should be rendered.
_PCT_KEYS = {"ebitda_margin", "ebit_margin", "net_margin", "gross_margin",
             "roa", "roe", "solvency", "debt_ratio"}
_MULT_KEYS = {"current_ratio", "debt_to_equity", "interest_coverage", "capital_intensity"}
_MONEY_KEYS = {"revenue_per_employee", "working_capital"}
_DAYS_KEYS = {"dso", "dpo", "inventory_days", "cash_conversion_cycle"}

# Curated display order — how an analyst reads a company: profitability, returns,
# solvency/liquidity, working-capital cycle, then efficiency/productivity.
_RATIO_ORDER = [
    "ebitda_margin", "ebit_margin", "net_margin", "gross_margin",
    "roe", "roa",
    "solvency", "debt_ratio", "debt_to_equity", "current_ratio", "interest_coverage",
    "dso", "dpo", "inventory_days", "cash_conversion_cycle", "working_capital",
    "revenue_per_employee", "capital_intensity",
]


def _es(s: str) -> str:
    """Formato contable español: miles con punto, decimales con coma.
    Convierte una cadena numérica en formato inglés (1,234.5) a español (1.234,5)."""
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _fmt_pct(v: Optional[float]) -> str:
    return "N/D" if v is None else _es(f"{v * 100:.1f}") + " %"


def _fmt_mult(v: Optional[float]) -> str:
    return "N/D" if v is None else _es(f"{v:.2f}") + "x"


def _fmt_money(v: Optional[float]) -> str:
    return "N/D" if v is None else _es(f"{v:,.0f}") + " €"


def _fmt_days(v: Optional[float]) -> str:
    return "N/D" if v is None else f"{v:.0f} días"


def _fmt_ratio(key: str, v: Optional[float]) -> str:
    if v is None:
        return "N/D"
    if key in _PCT_KEYS:
        return _fmt_pct(v)
    if key in _MONEY_KEYS:
        return _fmt_money(v)
    if key in _DAYS_KEYS:
        return _fmt_days(v)
    return _fmt_mult(v)


# ── ratios table ──────────────────────────────────────────────────────
def ratios_table_block(bundle: Dict) -> Optional[Dict]:
    """Table of every AVAILABLE ratio the Financial Engine computed, curated order."""
    ratios = bundle.get("ratios", {}) or {}
    rows: List[List[str]] = []
    for key in _RATIO_ORDER:
        r = ratios.get(key)
        if not r or not r.get("available"):
            continue
        rows.append([
            r.get("name", key),
            _fmt_ratio(key, r.get("value")),
            _CATEGORY_ES.get(r.get("category"), r.get("category", "")),
            r.get("formula", ""),
        ])
    if not rows:
        return None
    b = table_block("Ratios financieros (último ejercicio)",
                    ["Indicador", "Valor", "Categoría", "Fórmula"], rows)
    b["data_lineage"] = {"source": _FIN, "calculation": "ratios_library.compute_all",
                         "note": "solo ratios con inputs disponibles", "date": now_iso()}
    return b


# ── multi-year KPI table (cuaderno de venta p.23 style) ───────────────
def _safe_div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def multiyear_financials_block(bundle: Dict) -> Optional[Dict]:
    """Historical income summary across all available years (oldest→newest)."""
    pts = (bundle.get("evolution") or {}).get("points") or []
    pts = [p for p in pts if p.get("year") is not None]
    if len(pts) < 2:
        return None
    # engine gives newest-first; present oldest→newest like a track-record table
    pts = sorted(pts, key=lambda p: p["year"])
    years = [str(p["year"]) for p in pts]

    rev = [p.get("revenue") for p in pts]
    ebitda = [p.get("ebitda") for p in pts]
    net = [p.get("net_income") for p in pts]

    def growth_row(vals):
        out = ["—"]
        for i in range(1, len(vals)):
            g = _safe_div((vals[i] - vals[i - 1]) if (vals[i] is not None and vals[i - 1] is not None) else None,
                          abs(vals[i - 1]) if vals[i - 1] else None)
            out.append(_fmt_pct(g))
        return out

    rows = [
        ["Ingresos", *[_fmt_money(v) for v in rev]],
        ["Crecimiento ingresos", *growth_row(rev)],
        ["EBITDA", *[_fmt_money(v) for v in ebitda]],
        ["Margen EBITDA", *[_fmt_pct(_safe_div(e, r)) for e, r in zip(ebitda, rev)]],
        ["Resultado neto", *[_fmt_money(v) for v in net]],
        ["Margen neto", *[_fmt_pct(_safe_div(n, r)) for n, r in zip(net, rev)]],
    ]
    b = table_block("Evolución financiera", ["Concepto", *years], rows)
    b["data_lineage"] = {"source": _FIN, "calculation": "evolution.points", "date": now_iso()}
    return b


# ── financial quality KPI ─────────────────────────────────────────────
def quality_kpi_block(bundle: Dict) -> Optional[Dict]:
    q = bundle.get("financial_quality") or {}
    score = q.get("score")
    if score is None:
        return None
    b = kpi_block("Calidad financiera", f"{score}", f"/ {q.get('max', 100)}",
                  commentary="Score determinista (estados disponibles, histórico, EBITDA/PN, consistencia)")
    b["data_lineage"] = {"source": _FIN, "calculation": "financial_quality", "date": now_iso()}
    return b


def margin_percentile_kpi_block(bundle: Dict) -> Optional[Dict]:
    """Subject EBITDA-margin percentile vs its structural peer set (from comparables)."""
    comp = bundle.get("comparables") or {}
    pct = comp.get("subject_ebitda_margin_percentile")
    if pct is None:
        return None
    b = kpi_block("Percentil margen EBITDA (sector)", f"{pct * 100:.0f}º", "",
                  commentary=f"Frente a {comp.get('count', 0)} comparables (sector+tamaño+geografía)")
    b["data_lineage"] = {"source": _FIN, "calculation": "comparables.subject_ebitda_margin_percentile",
                         "date": now_iso()}
    return b


# ── sector positioning by OUR OWN percentiles ─────────────────────────
def _quantile(sorted_vals: List[float], q: float) -> Optional[float]:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
    return sorted_vals[idx]


def _percentile_of(sorted_vals: List[float], x: float) -> float:
    below = sum(1 for v in sorted_vals if v <= x)
    return below / len(sorted_vals)


def _coalesce(*vals):
    return next((v for v in vals if v is not None), None)


def _peer_ratio(fl, key):
    return (fl.get("ratios") or {}).get(key)


def _subj_ratio(bundle, key):
    return ((bundle.get("ratios") or {}).get(key) or {}).get("value")


# (key, label, format-fn, subject-value(bundle), per-peer value(fl, employees)).
# Peer ratios come from master_companies.financials.latest.ratios (populated by the
# widened _fin_summary); partial/empty until the full EAV is (re)ingested — honest.
_SECTOR_METRICS = [
    ("revenue", "Ingresos", _fmt_money,
     lambda b: (b.get("kpis") or {}).get("revenue"), lambda fl, e: fl.get("revenue")),
    ("ebitda_margin", "Margen EBITDA", _fmt_pct,
     lambda b: _coalesce((b.get("kpis") or {}).get("ebitda_margin"), _subj_ratio(b, "ebitda_margin")),
     lambda fl, e: _coalesce(fl.get("ebitda_margin"), _peer_ratio(fl, "ebitda_margin"))),
    ("gross_margin", "Margen bruto", _fmt_pct,
     lambda b: _subj_ratio(b, "gross_margin"), lambda fl, e: _peer_ratio(fl, "gross_margin")),
    ("net_margin", "Margen neto", _fmt_pct,
     lambda b: _coalesce(_subj_ratio(b, "net_margin"), (b.get("kpis") or {}).get("net_margin")),
     lambda fl, e: _peer_ratio(fl, "net_margin")),
    ("roe", "ROE", _fmt_pct,
     lambda b: _coalesce(_subj_ratio(b, "roe"), (b.get("kpis") or {}).get("roe")),
     lambda fl, e: _peer_ratio(fl, "roe")),
    ("roa", "ROA", _fmt_pct,
     lambda b: _coalesce(_subj_ratio(b, "roa"), (b.get("kpis") or {}).get("roa")),
     lambda fl, e: _peer_ratio(fl, "roa")),
    ("solvency", "Solvencia (PN/Activo)", _fmt_pct,
     lambda b: _coalesce(_subj_ratio(b, "solvency"), (b.get("kpis") or {}).get("solvency")),
     lambda fl, e: _peer_ratio(fl, "solvency")),
    ("current_ratio", "Liquidez", _fmt_mult,
     lambda b: _subj_ratio(b, "current_ratio"), lambda fl, e: _peer_ratio(fl, "current_ratio")),
    ("cash_conversion_cycle", "Ciclo de caja", _fmt_days,
     lambda b: _subj_ratio(b, "cash_conversion_cycle"), lambda fl, e: _peer_ratio(fl, "cash_conversion_cycle")),
    ("revenue_per_employee", "Ingresos/empleado", _fmt_money,
     lambda b: (b.get("kpis") or {}).get("revenue_per_employee"), lambda fl, e: _safe_div(fl.get("revenue"), e)),
]

_MIN_PEERS = 5


async def sector_positioning_block(db, bundle: Dict, size_band: bool = True,
                                   max_peers: int = 4000) -> Optional[Dict]:
    """Company vs its CNAE sector: p25 / median / p75 + the company's percentile,
    computed from real master_companies data. Skipped when too few peers."""
    ident = bundle.get("identity") or {}
    section = ident.get("cnae_section")
    kpis = bundle.get("kpis") or {}
    subj_rev = kpis.get("revenue")
    if not section:
        return None

    q: Dict = {"classification.cnae_section": section,
               "financials.latest.revenue": {"$ne": None}}
    if bundle.get("master_id"):
        q["master_id"] = {"$ne": bundle["master_id"]}
    if size_band and subj_rev:
        q["financials.latest.revenue"] = {"$gte": subj_rev * 0.3, "$lte": subj_rev * 3.0}

    peers = []
    async for p in db.master_companies.find(
            q, {"_id": 0, "financials.latest": 1, "size.employees_total": 1}).limit(max_peers):
        fl = (p.get("financials") or {}).get("latest") or {}
        emp = (p.get("size") or {}).get("employees_total")
        peers.append((fl, emp))
    # size-band may be too tight — fall back to the whole section
    if len(peers) < _MIN_PEERS and size_band:
        return await sector_positioning_block(db, bundle, size_band=False, max_peers=max_peers)
    if len(peers) < _MIN_PEERS:
        return None

    rows: List[List[str]] = []
    for key, label, fmt, subj_fn, peer_fn in _SECTOR_METRICS:
        vals = sorted(v for v in (peer_fn(fl, emp) for fl, emp in peers) if v is not None)
        if len(vals) < _MIN_PEERS:
            continue
        subj = subj_fn(bundle)
        med, p25, p75 = _quantile(vals, 0.5), _quantile(vals, 0.25), _quantile(vals, 0.75)
        subj_str = fmt(subj) if subj is not None else "N/D"
        pctl = f"{_percentile_of(vals, subj) * 100:.0f}º" if subj is not None else "N/D"
        rows.append([label, subj_str, fmt(med), fmt(p25), fmt(p75), pctl])

    if not rows:
        return None
    n = len(peers)
    band = "tamaño comparable (0,3x–3x ingresos)" if size_band and subj_rev else "sección CNAE completa"
    b = table_block(f"Posicionamiento vs sector (sección {section})",
                    ["Indicador", "Empresa", "Mediana sector", "P25", "P75", "Percentil"], rows)
    b["data_lineage"] = {"source": "master_companies",
                         "calculation": f"percentiles sobre {n} empresas del sector ({band})",
                         "date": now_iso()}
    return b


# ── cash flow statement (from full EAV, when filed) ──────────────────
def cashflow_block(bundle: Dict) -> Optional[Dict]:
    """Cash flow summary (EFE) + free cash flow + EBITDA-to-cash conversion. Returns None
    when the company filed abbreviated accounts without a cash-flow statement (honest)."""
    cf = (bundle.get("statements") or {}).get("cashflow")
    if not cf or cf.get("cf_operating") is None:
        return None
    rows = [
        ["Flujo de explotación", _fmt_money(cf.get("cf_operating"))],
        ["Flujo de inversión", _fmt_money(cf.get("cf_investing"))],
        ["Flujo de financiación", _fmt_money(cf.get("cf_financing"))],
        ["Variación neta de caja", _fmt_money(cf.get("cf_net_change"))],
        ["Flujo de caja libre (FCF)", _fmt_money(cf.get("free_cash_flow"))],
    ]
    conv = cf.get("cash_conversion")
    if conv is not None:
        rows.append(["Conversión EBITDA→caja", _fmt_pct(conv)])
    b = table_block("Flujo de caja (EFE)", ["Concepto", "Valor"], rows)
    b["data_lineage"] = {"source": _FIN, "calculation": "cashflow (PGC 61xxx-65xxx)", "date": now_iso()}
    return b


# ── Iberinform proprietary ratios (from full ingestion) ──────────────
# Curated per memory/IBERINFORM_RATIOS_PRIORITY.md: Tier 1-3 (Tier 4 credit-risk excluded).
# (code, label, kind). kind: pct | x | money | days | score | num. Order = presentation.
_IBERINFORM_RATIOS = [
    ("R01", "Rating Iberinform", "score"),
    ("S01", "Score de solvencia", "score"),
    ("SF025", "Cobertura de intereses", "x"),
    ("SF021", "Plazo medio de cobro", "days"),
    ("SF022", "Plazo medio de pago", "days"),
    ("SF023", "Plazo medio de aprovisionamiento", "days"),
    ("PRO001", "Fondo de maniobra", "money"),
    ("SF003", "Liquidez inmediata", "x"),
    ("SF004", "Coeficiente de tesorería", "x"),
    ("SF008", "Calidad de la deuda", "pct"),
    ("SF009", "Deuda a largo plazo", "pct"),
    ("SF010", "Deuda a corto plazo", "pct"),
    ("EFI008", "Gasto de personal / empleado", "money"),
    ("EFI006", "Ventas / empleado", "money"),
    ("PRO002", "Productividad", "num"),
    ("PRO005", "Apalancamiento", "x"),
    ("EFI001", "Rotación de activo", "x"),
    ("EFI003", "Rotación del circulante", "x"),
    ("REN007", "Margen EBITDA (Iberinform)", "pct"),
    ("REN005", "Margen neto (Iberinform)", "pct"),
    ("REN006", "Margen sobre ventas", "pct"),
    ("REN001", "Rentabilidad económica (ROA)", "pct"),
    ("REN003", "Rentabilidad financiera (ROE)", "pct"),
    ("REN010", "Variación de ventas", "pct"),
    ("SF001", "Ratio de solvencia", "x"),
    ("SF006", "Endeudamiento A", "pct"),
    ("SF007", "Endeudamiento B", "pct"),
    ("SF011", "Coeficiente de garantía", "x"),
]


def _fmt_ib(kind: str, v) -> str:
    if v is None:
        return "N/D"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if kind == "score":
        return f"{v:.0f}"
    if kind == "days":
        return f"{v:.0f} días"
    if kind == "money":
        return _es(f"{v:,.0f}") + " €"
    if kind == "x":
        return _es(f"{v:.2f}") + "x"
    if kind == "pct":
        # Iberinform suele expresar % como fracción (0.176) o como número (17.6); mostramos
        # como fracción si |v|<=1, si no como porcentaje ya expresado.
        return _es(f"{v*100:.1f}") + " %" if abs(v) <= 1 else _es(f"{v:.1f}") + " %"
    return _es(f"{v:.2f}")


def iberinform_ratios_block(bundle: Dict) -> Optional[Dict]:
    """Table of Iberinform's own precomputed ratios present for this company (Tier 1-3).
    Returns None until the delivery with Datos_RATIOS.tab is ingested (honest)."""
    ib = bundle.get("iberinform_ratios") or {}
    if not ib:
        return None
    rows = []
    for code, label, kind in _IBERINFORM_RATIOS:
        if code in ib and ib[code] is not None:
            rows.append([label, _fmt_ib(kind, ib[code]), code])
    if not rows:
        return None
    b = table_block("Ratios Iberinform (fuente oficial)", ["Indicador", "Valor", "Código"], rows)
    b["data_lineage"] = {"source": "iberinform", "calculation": "Datos_RATIOS.tab (precalculado)",
                         "note": "ratios oficiales del proveedor", "date": now_iso()}
    return b


# ── curated orchestrator ──────────────────────────────────────────────
def financial_detail_blocks(bundle: Dict) -> List[Dict]:
    """The curated financial detail (synchronous part): quality + margin percentile KPIs,
    ratios table, multi-year evolution table. Order = how an analyst presents it."""
    out: List[Dict] = []
    for fn in (quality_kpi_block, margin_percentile_kpi_block):
        b = fn(bundle)
        if b:
            out.append(b)
    for fn in (multiyear_financials_block, ratios_table_block, cashflow_block, iberinform_ratios_block):
        b = fn(bundle)
        if b:
            out.append(b)
    return out
