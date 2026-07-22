"""Skill: Valuation (REQ-004) — automatic company valuation.

Agency Tool calculates; arroba renders. Returns the flat contract:
  {valuation_range, comparables, explanation, confidence, lineage}

Method: reference sector multiples (EV/EBITDA, EV/Revenue) applied to the company's
real financials (Iberinform), with same-sector real comparables. Multiples are
reference/inferred ranges (lineage.source = "inferred"), not market-observed EVs.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from database import db
from services.data_layer.accessors import (
    name_of, category_of, cnae_section_of, financials_latest,
)

logger = logging.getLogger(__name__)

# Reference EV/EBITDA and EV/Revenue ranges (low, high) by CNAE section.
# Conservative industry references — inferred, not market-observed.
_SECTION_MULTIPLES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "C": {"ev_ebitda": (6.0, 9.0), "ev_revenue": (0.8, 1.5)},    # Manufactura
    "F": {"ev_ebitda": (5.0, 8.0), "ev_revenue": (0.6, 1.2)},    # Construcción
    "G": {"ev_ebitda": (6.0, 9.0), "ev_revenue": (0.5, 1.0)},    # Comercio
    "H": {"ev_ebitda": (6.0, 9.0), "ev_revenue": (0.8, 1.5)},    # Transporte
    "I": {"ev_ebitda": (7.0, 10.0), "ev_revenue": (1.0, 2.0)},   # Hostelería
    "J": {"ev_ebitda": (10.0, 16.0), "ev_revenue": (2.0, 5.0)},  # Información/TIC
    "K": {"ev_ebitda": (8.0, 12.0), "ev_revenue": (2.0, 4.0)},   # Financieras
    "M": {"ev_ebitda": (7.0, 11.0), "ev_revenue": (1.0, 2.5)},   # Profesionales
    "N": {"ev_ebitda": (6.0, 9.0), "ev_revenue": (0.8, 1.5)},    # Administrativas
    "Q": {"ev_ebitda": (9.0, 13.0), "ev_revenue": (1.2, 2.5)},   # Sanidad
    "R": {"ev_ebitda": (7.0, 10.0), "ev_revenue": (1.0, 2.0)},   # Artísticas
}
_DEFAULT_MULTIPLE = {"ev_ebitda": (6.0, 10.0), "ev_revenue": (0.8, 1.6)}

# Keyword → section for the agency/marketing dataset (when CNAE is missing).
_CATEGORY_KEYWORDS: List[Tuple[Tuple[str, ...], str]] = [
    (("software", "data", "tech", "digital", "programmatic", "performance", "medios"), "J"),
    (("salud", "health", "farma", "clinic"), "Q"),
    (("consult", "estrategia", "marca", "branding", "diseno", "diseño", "creativ", "comunicacion", "pr", "publicidad", "reputacion", "marketing"), "M"),
    (("industri", "fabric", "manufact"), "C"),
    (("retail", "comercio", "ecommerce"), "G"),
    (("hostel", "restaur", "turismo"), "I"),
    (("construc", "inmobili"), "F"),
]


def _section_from_category(category: Optional[str]) -> Optional[str]:
    if category:
        c = category.lower()
        for keywords, section in _CATEGORY_KEYWORDS:
            if any(k in c for k in keywords):
                return section
    return None


def _resolve_multiples(section: Optional[str]) -> Dict[str, Tuple[float, float]]:
    return _SECTION_MULTIPLES.get(section or "", _DEFAULT_MULTIPLE)


def _comparable_financials(peer: Dict) -> Optional[Dict]:
    return financials_latest(peer)


async def _comparables(doc: Dict, category: Optional[str], limit: int = 5) -> List[Dict]:
    if not category:
        return []
    rx = {"$regex": f"^{re.escape(category)}$", "$options": "i"}
    peers = await db.companies_master.find(
        {"$and": [
            {"$or": [{"classification.category": rx}, {"classification.sector": rx},
                     {"category_name": rx}, {"sources.web.category": rx}]},
            {"master_company_id": {"$ne": doc.get("master_company_id")}},
            {"merge_status": {"$ne": "merged"}},
        ]},
        {"_id": 0},
    ).limit(60).to_list(60)

    out = []
    for p in peers:
        fin = _comparable_financials(p)
        if not fin or not (fin.get("revenue") or fin.get("ebitda")):
            continue
        out.append({
            "master_company_id": p.get("master_company_id"),
            "name": name_of(p),
            "sector": category,
            "revenue": fin.get("revenue"),
            "ebitda": fin.get("ebitda"),
            "ebitda_margin": fin.get("ebitda_margin"),
            "year": fin.get("year"),
        })
        if len(out) >= limit:
            break
    return out


def _fmt_eur(v: float) -> str:
    return f"{v:,.0f} €".replace(",", ".")


async def value_company(master_company_id: str, context: Dict) -> Optional[Dict]:
    doc = await db.companies_master.find_one({"master_company_id": master_company_id}, {"_id": 0})
    if not doc:
        return None

    web = (doc.get("sources") or {}).get("web") or {}
    name = name_of(doc)
    category = category_of(doc)
    section = cnae_section_of(doc) or _section_from_category(category)
    mult = _resolve_multiples(section)
    fin = financials_latest(doc)
    comparables = await _comparables(doc, category)

    base_confidence = float(doc.get("confidence_score") or 0.0)
    lineage = {
        "source": "inferred",
        "method": None,
        "multiples_origin": "reference_sector_multiples",
        "financials_source": "iberinform" if fin else None,
        "section": section,
        "comparables_count": len(comparables),
    }

    valuation_range: Dict = {}
    explanation = ""
    confidence = round(0.1 + 0.1 * base_confidence, 2)

    if fin and (fin.get("ebitda") or 0) > 0:
        lo, hi = mult["ev_ebitda"]
        mid = (lo + hi) / 2
        ebitda = fin["ebitda"]
        valuation_range = {
            "currency": "EUR", "method": "ev_ebitda",
            "low": round(ebitda * lo, 2), "base": round(ebitda * mid, 2), "high": round(ebitda * hi, 2),
            "multiple_low": lo, "multiple_base": mid, "multiple_high": hi,
            "driver": "ebitda", "driver_value": ebitda, "fiscal_year": fin.get("year"),
        }
        lineage["method"] = "ev_ebitda"
        confidence = round(min(0.8, 0.55 + 0.1 * (1 if comparables else 0) + 0.15 * base_confidence), 2)
        explanation = (f"Valoración por múltiplo EV/EBITDA ({mid:.1f}x, rango {lo:.1f}x–{hi:.1f}x) "
                       f"sobre EBITDA {fin.get('year')} de {_fmt_eur(ebitda)}. "
                       f"Sector: {category or 'n/d'}{f' (sección {section})' if section else ''}. "
                       f"Múltiplos de referencia sectoriales (inferidos). "
                       f"{len(comparables)} comparables del mismo sector.")
    elif fin and (fin.get("revenue") or 0) > 0:
        lo, hi = mult["ev_revenue"]
        mid = (lo + hi) / 2
        revenue = fin["revenue"]
        valuation_range = {
            "currency": "EUR", "method": "ev_revenue",
            "low": round(revenue * lo, 2), "base": round(revenue * mid, 2), "high": round(revenue * hi, 2),
            "multiple_low": lo, "multiple_base": mid, "multiple_high": hi,
            "driver": "revenue", "driver_value": revenue, "fiscal_year": fin.get("year"),
        }
        lineage["method"] = "ev_revenue"
        confidence = round(min(0.6, 0.4 + 0.1 * (1 if comparables else 0) + 0.1 * base_confidence), 2)
        explanation = (f"Valoración por múltiplo EV/Ventas ({mid:.1f}x, rango {lo:.1f}x–{hi:.1f}x) "
                       f"sobre ingresos {fin.get('year')} de {_fmt_eur(revenue)} (sin EBITDA disponible). "
                       f"Sector: {category or 'n/d'}. Múltiplos de referencia (inferidos).")
    elif fin and (fin.get("equity") or 0) > 0:
        equity = fin["equity"]
        valuation_range = {
            "currency": "EUR", "method": "book_value",
            "low": round(equity * 0.8, 2), "base": round(equity, 2), "high": round(equity * 1.5, 2),
            "driver": "equity", "driver_value": equity, "fiscal_year": fin.get("year"),
        }
        lineage["method"] = "book_value"
        confidence = round(min(0.35, 0.25 + 0.1 * base_confidence), 2)
        explanation = (f"Valoración por valor en libros (patrimonio neto {_fmt_eur(equity)}, "
                       f"{fin.get('year')}) ante ausencia de EBITDA/ingresos. Estimación conservadora.")
    else:
        lineage["method"] = "insufficient_data"
        explanation = (f"Sin datos financieros suficientes para {name or master_company_id}. "
                       f"Se requieren EBITDA, ingresos o patrimonio para estimar el rango de valoración.")

    return {
        "master_company_id": master_company_id,
        "company_name": name,
        "valuation_range": valuation_range,
        "comparables": comparables,
        "explanation": explanation,
        "confidence": confidence,
        "lineage": lineage,
    }
