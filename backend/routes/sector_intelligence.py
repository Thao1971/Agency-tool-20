"""Sector Intelligence V2 — Public endpoints for Arroba/Valuo consumption.

CNAE-based hierarchy: Section (A-U) → Division (2-digit) → Group (4-digit).
Multi-score: size_score, growth_score, activity_score → dynamism_score.
Multi-taxonomy ready: official_cnae (active), business_archetype (prepared).
"""

from typing import Dict, List
from fastapi import APIRouter, Depends, Query, HTTPException
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.sector_intelligence_v2 import compute_sector_intelligence_v2
from services.cnae_catalog import (
    BUSINESS_ARCHETYPES, TAXONOMY_TYPES,
)
import time

router = APIRouter(prefix="/api/v1/public/sector-intelligence", tags=["sector_intelligence"])

CONTRACT_VERSION = "2.0"


def _meta(t0):
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now_iso(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
        "source_attribution": "INE Demografia Empresarial, Contratacion Publica, BORME, Iberinform",
    }


_CNAE_LEVEL_ES = {"section": "Sección", "division": "División", "group": "Grupo"}


def _sector_card(s):
    """Compact card representation for lists."""
    return {
        "cnae_code": s.get("cnae_code"),
        "cnae_level": s.get("cnae_level"),
        # 2026-09-10: etiqueta ya traducida del nivel CNAE (sugerencia de la
        # verificacion en preview) - para que un ranking de /top-dynamic con
        # varios niveles mezclados (ver `level` como lista mas abajo) se pueda
        # etiquetar fila a fila ("Seccion"/"Division"/"Grupo") sin que el
        # frontend tenga que mantener su propio mapeo.
        "cnae_level_es": _CNAE_LEVEL_ES.get(s.get("cnae_level")),
        "cnae_label": s.get("cnae_label"),
        "size_score": s.get("size_score", 0),
        "growth_score": s.get("growth_score", 0),
        "activity_score": s.get("activity_score", 0),
        "dynamism_score": s.get("dynamism_score", 0),
        "trend_direction": s.get("trend_direction"),
        "signal": s.get("signal"),
        "primary_driver": s.get("primary_driver"),
        "active_companies": s.get("active_companies", 0),
        "procurement_contracts": s.get("procurement_contracts", 0),
        "procurement_amount": s.get("procurement_amount", 0),
        "partial_data": s.get("partial_data", True),
    }


def _company_query_for_sector(sector: Dict) -> Dict:
    """Q5 — maps a sector_intelligence doc (section/division/group) to the real
    `master_companies` filter at the matching CNAE granularity. Reuses the same
    classification fields (`cnae_code`/`cnae_division`/`cnae_section`) already
    populated by `master_builder.py`, and the same `status: active` convention used
    everywhere else in this codebase (mandates.py, competitor_graph.py, etc.)."""
    level = sector.get("cnae_level")
    code = sector.get("cnae_code")
    q: Dict = {"status": "active"}
    if level == "group":
        q["classification.cnae_code"] = code
    elif level == "division":
        q["classification.cnae_division"] = code
    elif level == "section":
        q["classification.cnae_section"] = code
    else:
        q["classification.cnae_code"] = code
    return q


async def _companies_page(sector: Dict, limit: int, offset: int) -> Dict:
    """Real companies from ARROBA's own ingested universe (`master_companies`) for a
    sector, enriched with their real active-signal count (Q1/Q4 `db.signals`, no new
    computation). Deliberately separate from `active_companies` on the sector doc,
    which is a DIRCE/INE-based NATIONAL ESTIMATE redistributed by CNAE
    (`sector_intelligence_v2.py::_gather_demography`), not a real company count — the
    two numbers measure different things and must never be presented as the same."""
    q = _company_query_for_sector(sector)
    total = await db.master_companies.count_documents(q)
    cursor = db.master_companies.find(
        q, {"_id": 0, "master_id": 1, "identity.legal_name": 1, "classification.cnae_code": 1,
            "location.provincia": 1, "financials.latest.revenue": 1, "financials.latest.ebitda": 1},
    ).sort("financials.latest.revenue", -1).skip(offset).limit(limit)
    rows = await cursor.to_list(limit)
    master_ids = [r["master_id"] for r in rows]

    signals_by_company: Dict[str, List[Dict]] = {}
    if master_ids:
        async for s in db.signals.find(
            {"master_id": {"$in": master_ids}, "status": "active"},
            {"_id": 0, "master_id": 1, "signal_type": 1, "category": 1, "dimensions.impact": 1},
        ):
            signals_by_company.setdefault(s["master_id"], []).append(s)

    companies = []
    for r in rows:
        sigs = signals_by_company.get(r["master_id"], [])
        top = max(sigs, key=lambda s: (s.get("dimensions") or {}).get("impact", 0)) if sigs else None
        companies.append({
            "master_id": r["master_id"],
            "legal_name": (r.get("identity") or {}).get("legal_name"),
            "cnae_code": (r.get("classification") or {}).get("cnae_code"),
            "provincia": (r.get("location") or {}).get("provincia"),
            "revenue": (r.get("financials") or {}).get("latest", {}).get("revenue"),
            "ebitda": (r.get("financials") or {}).get("latest", {}).get("ebitda"),
            "active_signals_count": len(sigs),
            "top_signal": {"signal_type": top["signal_type"], "category": top["category"]} if top else None,
        })
    return {
        "companies": companies,
        "pagination": {"total_in_arroba_universe": total, "limit": limit, "offset": offset,
                       "returned": len(companies)},
        "data_caveat": ("Este recuento y listado reflejan el universo de empresas ya ingeridas en "
                        "ARROBA (Iberinform + BORME), NO la estimación nacional DIRCE/INE usada en "
                        "'active_companies' del dynamism_score del sector, que es una redistribución "
                        "estadística del total nacional, no un conteo real por CNAE."),
    }


@router.get("/taxonomies")
async def list_taxonomies():
    """List supported taxonomy types."""
    t0 = time.time()
    return {
        **_meta(t0),
        "taxonomy_types": TAXONOMY_TYPES,
        "active": "official_cnae",
        "archetypes": BUSINESS_ARCHETYPES,
    }


# ══════════════════════════════════════════
# OVERVIEW & RANKINGS
# ══════════════════════════════════════════

@router.get("/overview")
async def overview(
    level: str = Query("section", regex="^(section|division|group)$"),
    taxonomy_type: str = Query("official_cnae"),
):
    """All sectors at the specified CNAE level, ranked by dynamism_score."""
    t0 = time.time()
    query = {"cnae_level": level, "taxonomy_type": taxonomy_type}
    sectors = await db.sector_intelligence.find(
        query, {"_id": 0}
    ).sort("dynamism_score", -1).to_list(200)

    return {
        **_meta(t0),
        "level": level,
        "taxonomy_type": taxonomy_type,
        "sectors": [_sector_card(s) for s in sectors],
        "count": len(sectors),
    }


_VALID_CNAE_LEVELS = ("section", "division", "group")


@router.get("/top-dynamic")
async def top_dynamic(
    limit: int = Query(10, ge=1, le=200),
    level: str = Query(
        "section",
        description="Uno o varios niveles CNAE separados por coma, ej. 'section' o "
                     "'section,division,group'. Homes que quieran una unica lista de "
                     "dinamismo mezclando granularidades (ej. 'Salud' a nivel seccion "
                     "junto a 'Actividades veterinarias' a nivel division) piden varios "
                     "niveles a la vez; consumidores existentes (Mapa Empresarial) que "
                     "piden un solo nivel siguen funcionando igual.",
    ),
):
    """Top sectors by dynamism_score (combined metric).

    `level` acepta una lista separada por coma para poder rankear por
    dynamism_score a traves de varios niveles CNAE en una sola llamada
    (2026-09-10, a peticion de Daniel: la Home nueva quiere mezclar
    secciones amplias como 'Salud' con divisiones concretas como
    'Actividades veterinarias' en un unico ranking). Cada sector devuelto
    ya trae su propio `cnae_level` en `_sector_card`, asi que el frontend
    puede etiquetar cada fila con su granularidad real en vez de tratarlas
    como si fueran comparables 1:1."""
    t0 = time.time()
    levels = [lv.strip() for lv in level.split(",") if lv.strip()]
    invalid = [lv for lv in levels if lv not in _VALID_CNAE_LEVELS]
    if not levels or invalid:
        raise HTTPException(
            status_code=422,
            detail=f"level invalido: {invalid or level!r}. Valores permitidos: "
                   f"{', '.join(_VALID_CNAE_LEVELS)} (separados por coma).",
        )

    level_query = levels[0] if len(levels) == 1 else {"$in": levels}
    sectors = await db.sector_intelligence.find(
        {"cnae_level": level_query, "taxonomy_type": "official_cnae", "dynamism_score": {"$gt": 0}},
        {"_id": 0},
    ).sort([("dynamism_score", -1), ("cnae_code", 1)]).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "ranking_by": "dynamism_score",
        "level": levels[0] if len(levels) == 1 else ",".join(levels),  # compat: consumidores de un solo nivel siguen leyendo un string simple
        "levels": levels,
        "sectors": [_sector_card(s) for s in sectors],
    }


@router.get("/largest")
async def largest(
    limit: int = Query(10, ge=1, le=200),
    level: str = Query("section", regex="^(section|division|group)$"),
):
    """Top sectors by size_score (number of active companies)."""
    t0 = time.time()
    sectors = await db.sector_intelligence.find(
        {"cnae_level": level, "taxonomy_type": "official_cnae"},
        {"_id": 0},
    ).sort([("size_score", -1), ("cnae_code", 1)]).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "ranking_by": "size_score",
        "level": level,
        "sectors": [_sector_card(s) for s in sectors],
    }


@router.get("/fastest-growing")
async def fastest_growing(
    limit: int = Query(10, ge=1, le=200),
    level: str = Query("section", regex="^(section|division|group)$"),
):
    """Top sectors by growth_score (company creation dynamics)."""
    t0 = time.time()
    sectors = await db.sector_intelligence.find(
        {"cnae_level": level, "taxonomy_type": "official_cnae"},
        {"_id": 0},
    ).sort([("growth_score", -1), ("cnae_code", 1)]).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "ranking_by": "growth_score",
        "level": level,
        "sectors": [_sector_card(s) for s in sectors],
    }


@router.get("/most-active")
async def most_active(
    limit: int = Query(10, ge=1, le=200),
    level: str = Query("section", regex="^(section|division|group)$"),
):
    """Top sectors by activity_score (procurement + BORME + Iberinform)."""
    t0 = time.time()
    sectors = await db.sector_intelligence.find(
        {"cnae_level": level, "taxonomy_type": "official_cnae"},
        {"_id": 0},
    ).sort([("activity_score", -1), ("cnae_code", 1)]).limit(limit).to_list(limit)

    return {
        **_meta(t0),
        "ranking_by": "activity_score",
        "level": level,
        "sectors": [_sector_card(s) for s in sectors],
    }


@router.get("/emerging")
async def emerging(
    level: str = Query("section", regex="^(section|division|group)$"),
):
    """Sectors with expansion or emerging signals."""
    t0 = time.time()
    sectors = await db.sector_intelligence.find(
        {
            "cnae_level": level,
            "taxonomy_type": "official_cnae",
            "signal": {"$in": ["sector_expansion", "emerging_sector", "high_public_demand"]},
        },
        {"_id": 0},
    ).sort("dynamism_score", -1).to_list(50)

    return {
        **_meta(t0),
        "level": level,
        "sectors": [_sector_card(s) for s in sectors],
        "count": len(sectors),
    }


@router.get("/contracting")
async def contracting(
    level: str = Query("section", regex="^(section|division|group)$"),
):
    """Sectors with contraction signals."""
    t0 = time.time()
    sectors = await db.sector_intelligence.find(
        {
            "cnae_level": level,
            "taxonomy_type": "official_cnae",
            "signal": {"$in": ["sector_contraction"]},
        },
        {"_id": 0},
    ).sort("dynamism_score", 1).to_list(50)

    return {
        **_meta(t0),
        "level": level,
        "sectors": [_sector_card(s) for s in sectors],
        "count": len(sectors),
    }


# ══════════════════════════════════════════
# DRILL-DOWN
# ══════════════════════════════════════════

@router.get("/section/{code}")
async def section_detail(code: str):
    """Drill-down: Section → its Divisions with scores."""
    t0 = time.time()
    code = code.upper()

    # Get section
    section = await db.sector_intelligence.find_one(
        {"cnae_code": code, "cnae_level": "section", "taxonomy_type": "official_cnae"},
        {"_id": 0},
    )
    if not section:
        raise HTTPException(404, f"Section {code} not found. Run /sync first.")

    # Get divisions within this section
    divisions = await db.sector_intelligence.find(
        {"parent_section": code, "cnae_level": "division", "taxonomy_type": "official_cnae"},
        {"_id": 0},
    ).sort("dynamism_score", -1).to_list(50)

    return {
        **_meta(t0),
        "section": section,
        "divisions": [_sector_card(d) for d in divisions],
        "divisions_count": len(divisions),
    }


@router.get("/detail/{cnae_code}")
async def cnae_detail(cnae_code: str):
    """Full detail for any CNAE code (section/division/group)."""
    t0 = time.time()
    cnae_code = cnae_code.upper() if len(cnae_code) == 1 else cnae_code

    sector = await db.sector_intelligence.find_one(
        {"cnae_code": cnae_code, "taxonomy_type": "official_cnae"},
        {"_id": 0},
    )
    if not sector:
        raise HTTPException(404, f"CNAE {cnae_code} not found")

    # If section or division, also get children
    children = []
    if sector["cnae_level"] == "section":
        children = await db.sector_intelligence.find(
            {"parent_section": cnae_code, "cnae_level": "division", "taxonomy_type": "official_cnae"},
            {"_id": 0},
        ).sort("dynamism_score", -1).to_list(50)
    elif sector["cnae_level"] == "division":
        children = await db.sector_intelligence.find(
            {"parent_division": cnae_code, "cnae_level": "group", "taxonomy_type": "official_cnae"},
            {"_id": 0},
        ).sort("dynamism_score", -1).to_list(50)

    # Q5 — close the "sector → lista de targets" gap: at group level (finest CNAE
    # granularity, no sector_intelligence children below it) embed a real-company
    # preview from master_companies. Full pagination lives at the dedicated
    # /detail/{cnae_code}/companies endpoint below.
    companies_preview = None
    if sector["cnae_level"] == "group":
        companies_preview = await _companies_page(sector, limit=10, offset=0)

    return {
        **_meta(t0),
        "sector": sector,
        "children": [_sector_card(c) for c in children],
        "children_count": len(children),
        "companies_preview": companies_preview,
    }


@router.get("/detail/{cnae_code}/companies")
async def cnae_companies(
    cnae_code: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Q5 — Drill-down sector→empresa. Real companies (from ARROBA's own ingested
    universe, `master_companies`) matching this CNAE code at whatever granularity it
    represents (section/division/group), enriched with real active-signal counts
    (Q1/Q4). Paginated because a section/division can match many companies."""
    t0 = time.time()
    cnae_code = cnae_code.upper() if len(cnae_code) == 1 else cnae_code

    sector = await db.sector_intelligence.find_one(
        {"cnae_code": cnae_code, "taxonomy_type": "official_cnae"}, {"_id": 0},
    )
    if not sector:
        raise HTTPException(404, f"CNAE {cnae_code} not found")

    page = await _companies_page(sector, limit=limit, offset=offset)
    return {**_meta(t0), "cnae_code": cnae_code, "cnae_level": sector.get("cnae_level"), **page}


# ══════════════════════════════════════════
# ADMIN: SYNC (separate prefix for admin operations)
# ══════════════════════════════════════════

admin_router = APIRouter(prefix="/api/v1/admin/sector-intelligence", tags=["sector_intelligence_admin"])


@admin_router.post("/sync")
async def sync(user=Depends(get_current_user)):
    """Recompute all sector intelligence V2 scores."""
    result = await compute_sector_intelligence_v2()
    from services.intelligence_scheduler import log_manual_sync
    await log_manual_sync("sector_intelligence", result.get("total", 0))
    return result


# Keep backward-compat under public prefix
@router.post("/sync")
async def sync_public(user=Depends(get_current_user)):
    """Recompute all sector intelligence V2 scores (backward compat)."""
    result = await compute_sector_intelligence_v2()
    from services.intelligence_scheduler import log_manual_sync
    await log_manual_sync("sector_intelligence", result.get("total", 0))
    return result
