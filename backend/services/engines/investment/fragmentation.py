"""Fragmentation / Roll-up Score (E7 — Investment Intelligence).

Resuelve el gap que el roadmap llama "Índice de fragmentación sectorial, trigger de
roll-up": mide cuántos targets de add-on viables existen en un sector y qué tan
concentrado está ya. Explícitamente dependiente de Q2 (grafo de control real) — antes
de Q2 no había forma de saber si dos empresas del mismo CNAE ya pertenecían al mismo
grupo, así que cualquier "índice de fragmentación" habría contado como independientes
empresas que en realidad ya están consolidadas. También se apoya en T3
(`sector_consolidation_map`) para el universo real de empresas por sector.

Metodología (rules-based, sin IA, misma convención que el resto de motores):

1. Concentración (HHI — Herfindahl-Hirschman Index): agrupa la facturación real de
   `master_companies` por `ownership.group_id` (Q2) — dos empresas ya del mismo grupo
   cuentan como UN solo actor de mercado, no dos independientes. HHI = suma de
   (cuota de mercado)^2 * 10000, escala estándar 0-10000 usada por DOJ/FTC en el
   análisis de concentración de mercado (no es una escala inventada para este
   proyecto). Umbrales estándar: <1500 no concentrado, 1500-2500 moderadamente
   concentrado, >2500 altamente concentrado.
2. Targets viables de add-on (`standalone_targets_count`): empresas SIN
   `ownership.group_id` (nunca consolidadas, dato real de Q2) — el pool real de
   candidatos independientes en ese sector.
3. Dispersión de múltiplos (`multiple_dispersion`): SOLO se calcula cuando existe un
   múltiplo real de mercado para el sector (Q6 — hoy únicamente agencias de
   publicidad, CNAE división 73). Para cualquier otro sector se devuelve `None` con
   un caveat explícito — este módulo NUNCA fabrica una dispersión de múltiplos que no
   está respaldada por datos reales de transacciones.
"""

from typing import Dict, List, Optional

from database import db
from services.engines.financial import market_multiples as MM

ENGINE_VERSION = "fragmentation-v1"
CNAE_FIELDS = ("cnae_code", "cnae_division", "cnae_section")

# Standard DOJ/FTC Horizontal Merger Guidelines HHI thresholds (0-10000 scale) — not
# a project-specific invention.
HHI_UNCONCENTRATED = 1500
HHI_MODERATE = 2500


def _classify_hhi(hhi: float) -> str:
    if hhi < HHI_UNCONCENTRATED:
        return "unconcentrated"
    if hhi < HHI_MODERATE:
        return "moderately_concentrated"
    return "highly_concentrated"


async def _companies_for_sector(cnae_field: str, cnae_value: str, limit: int) -> List[Dict]:
    if cnae_field not in CNAE_FIELDS:
        raise ValueError(f"cnae_field must be one of {CNAE_FIELDS}")
    q = {"status": "active", f"classification.{cnae_field}": cnae_value}
    return await db.master_companies.find(
        q, {"_id": 0, "master_id": 1, "classification.cnae_code": 1,
            "financials.latest.revenue": 1, "ownership.group_id": 1},
    ).limit(limit).to_list(limit)


def _market_actors(companies: List[Dict]) -> Dict[str, float]:
    """Groups revenue by ownership.group_id (Q2) — companies already in the same real
    group count as ONE market actor, not several independent ones. Standalone
    companies (no group_id) are each their own singleton actor."""
    revenue_by_actor: Dict[str, float] = {}
    for c in companies:
        rev = (c.get("financials") or {}).get("latest", {}).get("revenue")
        if not rev or rev <= 0:
            continue
        gid = (c.get("ownership") or {}).get("group_id") or f"solo_{c['master_id']}"
        revenue_by_actor[gid] = revenue_by_actor.get(gid, 0) + rev
    return revenue_by_actor


async def compute_fragmentation(cnae_field: str, cnae_value: str, limit_companies: int = 500) -> Dict:
    companies = await _companies_for_sector(cnae_field, cnae_value, limit_companies)
    total_companies = len(companies)
    standalone = [c for c in companies if not (c.get("ownership") or {}).get("group_id")]
    grouped_ids = {(c.get("ownership") or {}).get("group_id") for c in companies
                   if (c.get("ownership") or {}).get("group_id")}

    revenue_by_actor = _market_actors(companies)
    companies_with_revenue = sum(
        1 for c in companies if (c.get("financials") or {}).get("latest", {}).get("revenue"))

    hhi = None
    concentration_label = None
    if revenue_by_actor and sum(revenue_by_actor.values()) > 0:
        total_rev = sum(revenue_by_actor.values())
        hhi = round(sum((v / total_rev) ** 2 for v in revenue_by_actor.values()) * 10000, 1)
        concentration_label = _classify_hhi(hhi)

    # Q6 real multiple, when this sector happens to be in-scope (agencies today).
    multiple_dispersion = None
    multiple_dispersion_caveat = ("Sin múltiplo real de mercado para este sector — Q6 solo cubre "
                                  "agencias de publicidad (CNAE división 73) hoy.")
    if cnae_field == "cnae_code":
        real = await MM.real_multiple_for_company(cnae_value)
        if real and real.get("ev_ebitda_p25") and real.get("ev_ebitda_median"):
            multiple_dispersion = round(
                (real["ev_ebitda_p75"] - real["ev_ebitda_p25"]) / real["ev_ebitda_median"], 3)
            multiple_dispersion_caveat = f"Calculado sobre {real['sample_size']} transacciones reales del M&A Radar."

    return {
        "cnae_field": cnae_field, "cnae_value": cnae_value,
        "total_companies_in_arroba_universe": total_companies,
        "companies_with_revenue_data": companies_with_revenue,
        "market_actors_count": len(revenue_by_actor),
        "distinct_ownership_groups": len(grouped_ids),
        "standalone_targets_count": len(standalone),
        "hhi": hhi, "concentration_label": concentration_label,
        "hhi_methodology": "DOJ/FTC Horizontal Merger Guidelines, escala 0-10000; agrupado por "
                            "ownership.group_id real (Q2), no por empresa individual",
        "multiple_dispersion": multiple_dispersion,
        "multiple_dispersion_caveat": multiple_dispersion_caveat,
        "truncated": total_companies >= limit_companies,
        "engine_version": ENGINE_VERSION,
    }
