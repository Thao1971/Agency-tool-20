"""arroba.v2 company Ficha surfaces (I-2/I-3): ownership, governance, corporate events.

Read-only, additive, X-API-Key protected. Real-data-only: every block reports its own
`coverage` and returns `available: false` cleanly when there is no data (Beta degrades to
"información en preparación"). No internal/provider vocabulary in user-facing text.
"""
from typing import Dict, List, Optional
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from services.service_auth import require_service_key
from borme.parser import normalize_company_name
from services.data_layer.master import control_synergy as CS
from services.engines.financial import engine as FE
from services.engines.investment import fragmentation as FRAG
from routes.company_intelligence import _build as _build_identity

router = APIRouter(prefix="/api/v1/company", tags=["company-ficha (arroba.v2)"])
ENGINE_VERSION = "arroba-company-ficha-v1"


async def _master(identifier: str) -> Optional[Dict]:
    return await db.master_companies.find_one(
        {"$or": [{"cif_normalized": identifier}, {"master_id": identifier}]}, {"_id": 0})


# ── Coverage / pre-flight (B-2 Fase 0): let Beta pre-filter valid CIFs before calling
# analyze/ficha, and diagnose 404s (company simply not in the master vs. lookup issue). ──
class CoverageCheckRequest(BaseModel):
    identifiers: List[str]


async def _coverage_for(identifier: str) -> Dict:
    """Per-CIF availability snapshot (cheap counts, no engine run). `resolved: false`
    means the company is NOT in the master → analyze/ficha would 404 (expected, honest)."""
    master = await _master(identifier)
    if not master:
        return {"identifier": identifier, "resolved": False,
                "reason": "not_in_master",
                "sections": {"financials": False, "cash_flow": False, "ownership": False,
                             "governance": False, "events": False, "signals": False}}
    cif = master["cif_normalized"]
    legal_name = (master.get("identity") or {}).get("legal_name")
    name_norm = normalize_company_name(legal_name) if legal_name else ""

    fin_years = await db.norm_financials.count_documents({"cif_normalized": cif})
    has_cf = await db.norm_financials.count_documents(
        {"cif_normalized": cif, "accounts.61500": {"$exists": True}}) > 0
    own = await db.norm_ownership.count_documents({"src_cif": cif, "relationship_type": "shareholder"})
    if not own:
        own = len(((master.get("ownership") or {}).get("shareholders") or []))
    gov = await db.norm_officers.count_documents({"cif_normalized": cif})
    events = (await db.borme_events.count_documents({"company_name_normalized": name_norm})
              if name_norm else 0)
    signals = await db.signals.count_documents({"master_id": master["master_id"], "status": "active"})
    has_fin = fin_years > 0 and (master.get("financials") or {}).get("latest") is not None
    return {
        "identifier": identifier, "resolved": True, "cif": cif,
        "master_id": master["master_id"], "name": legal_name,
        "sections": {
            "financials": has_fin, "cash_flow": has_cf,
            "ownership": own > 0, "governance": gov > 0,
            "events": events > 0, "signals": signals > 0,
        },
        "counts": {"financial_years": fin_years, "shareholders": own,
                   "officers": gov, "events": events, "signals": signals},
    }


@router.get("/coverage")
async def coverage(_key=Depends(require_service_key)):
    """Cobertura agregada del master de Intel (B-2 Fase 0): totales por sección para que
    Beta calibre expectativas. Nota: la entrega de muestra (25k) NO incluye grandes
    cotizadas del IBEX/Continuo — no hay campo `is_listed` poblado todavía."""
    total = await db.master_companies.count_documents({})
    with_fin = await db.master_companies.count_documents({"financials.latest.revenue": {"$ne": None}})
    with_balance = await db.master_companies.count_documents(
        {"financials.latest.ratios.current_ratio": {"$ne": None}})
    with_own = await db.master_companies.count_documents({"ownership.shareholders.0": {"$exists": True}})
    with_off = await db.master_companies.count_documents({"officers_count": {"$gt": 0}})
    cf_years = await db.norm_financials.count_documents({"accounts.61500": {"$exists": True}})
    listed = await db.master_companies.count_documents({"is_listed": True})
    return {
        "master_total": total,
        "with_financials": with_fin,
        "with_balance_liquidity": with_balance,
        "with_ownership": with_own,
        "with_governance": with_off,
        "financial_years_with_cashflow": cf_years,
        "listed_companies": listed,
        "notes": [
            "La muestra actual (Iberinform 25k) es un subconjunto; no incluye grandes "
            "cotizadas del IBEX/Mercado Continuo (Iberdrola, Planeta, Technip no están en el master).",
            "Cash flow (EFE) solo disponible para empresas que presentan cuentas normales "
            "(no PYME/abreviadas): la mayoría de PYMEs no lo incluyen (silencio elegante).",
            "Use POST /api/v1/company/coverage/check para pre-filtrar CIFs antes de analyze/ficha.",
        ],
        "engine_version": ENGINE_VERSION,
    }


@router.post("/coverage/check")
async def coverage_check(req: CoverageCheckRequest, _key=Depends(require_service_key)):
    """Pre-flight de un lote de CIFs: por cada uno indica si resuelve en el master y qué
    secciones tienen dato. Permite a Beta evitar 404s y elegir CIFs de demo con confianza."""
    ids = req.identifiers[:100]
    results = [await _coverage_for(i) for i in ids]
    return {"count": len(results), "resolved": sum(1 for r in results if r["resolved"]),
            "results": results, "engine_version": ENGINE_VERSION}


def _control_tier(top_pct: Optional[float]) -> Optional[str]:
    if top_pct is None:
        return None
    if top_pct > 50:
        return "Control mayoritario"
    if top_pct >= 25:
        return "Control significativo (participación de bloqueo)"
    return "Capital disperso"


@router.get("/{identifier}/ownership")
async def ownership(identifier: str, _key=Depends(require_service_key)):
    """Estructura de propiedad: accionistas, concentración y tramo de control (I-2 #6)."""
    master = await _master(identifier)
    if not master:
        raise HTTPException(status_code=404, detail="Company not found")
    cif = master["cif_normalized"]

    rows = await db.norm_ownership.find(
        {"src_cif": cif, "relationship_type": "shareholder"}, {"_id": 0}).to_list(500)

    # Deduplicate by counterparty, keeping the most recent year / highest pct.
    best: Dict[str, Dict] = {}
    for r in rows:
        key = r.get("counterparty_key") or (r.get("counterparty_name") or "").lower()
        if not key:
            continue
        cur = best.get(key)
        if cur is None or (r.get("year") or 0) > (cur.get("year") or 0):
            best[key] = r

    shareholders = []
    for r in best.values():
        shareholders.append({
            "name": r.get("counterparty_name"),
            "cif": r.get("counterparty_cif"),
            "pct": r.get("pct"),
            "as_of_year": r.get("year"),
        })

    # Fallback to the master snapshot if the normalized layer has nothing.
    if not shareholders:
        for s in ((master.get("ownership") or {}).get("shareholders") or []):
            shareholders.append({"name": s.get("name"), "cif": s.get("cif"),
                                 "pct": s.get("pct"), "as_of_year": None})
        seen = set()
        deduped = []
        for s in shareholders:
            sig = (s["name"], s["pct"])
            if sig in seen:
                continue
            seen.add(sig)
            deduped.append(s)
        shareholders = deduped

    shareholders.sort(key=lambda s: (s["pct"] is not None, s["pct"] or 0), reverse=True)
    if not shareholders:
        return {"identifier": identifier, "cif": cif, "available": False,
                "engine_version": ENGINE_VERSION}

    top = shareholders[0]
    top_pct = top.get("pct")
    controlling = top["name"] if (top_pct is not None and top_pct > 50) else None
    return {
        "identifier": identifier, "cif": cif, "available": True,
        "shareholders": shareholders,
        "control": {
            "controlling_shareholder": controlling,
            "top1_pct": top_pct,
            "top1_name": top.get("name"),
            "tier": _control_tier(top_pct),
        },
        "coverage": {"shareholders_count": len(shareholders)},
        "engine_version": ENGINE_VERSION,
    }


@router.get("/{identifier}/governance")
async def governance(identifier: str, _key=Depends(require_service_key)):
    """Órgano de administración: cargos vigentes por persona (I-2 #7)."""
    master = await _master(identifier)
    if not master:
        raise HTTPException(status_code=404, detail="Company not found")
    cif = master["cif_normalized"]

    rows = await db.norm_officers.find({"cif_normalized": cif}, {"_id": 0}).to_list(500)

    best: Dict[tuple, Dict] = {}
    for r in rows:
        key = (r.get("person_key") or (r.get("person_name") or "").lower(), r.get("role"))
        cur = best.get(key)
        if cur is None or (r.get("year") or 0) > (cur.get("year") or 0):
            best[key] = r

    officers = [{
        "name": r.get("person_name"),
        "role": r.get("role"),
        "since": r.get("appointment_date"),
        "year": r.get("year"),
    } for r in best.values()]
    officers.sort(key=lambda o: (o["year"] or 0), reverse=True)

    if not officers:
        return {"identifier": identifier, "cif": cif, "available": False,
                "engine_version": ENGINE_VERSION}
    return {"identifier": identifier, "cif": cif, "available": True,
            "officers": officers, "coverage": {"officers_count": len(officers)},
            "engine_version": ENGINE_VERSION}


@router.get("/{identifier}/events")
async def events(identifier: str, limit: int = 50, _key=Depends(require_service_key)):
    """Cronología de actos registrales (BORME) de la sociedad (I-3 #15)."""
    master = await _master(identifier)
    if not master:
        raise HTTPException(status_code=404, detail="Company not found")
    cif = master["cif_normalized"]
    legal_name = (master.get("identity") or {}).get("legal_name")
    name_norm = normalize_company_name(legal_name) if legal_name else ""
    if not name_norm:
        return {"identifier": identifier, "cif": cif, "available": False,
                "engine_version": ENGINE_VERSION}

    limit = max(1, min(limit, 200))
    total = await db.borme_events.count_documents({"company_name_normalized": name_norm})
    rows = await db.borme_events.find(
        {"company_name_normalized": name_norm},
        {"_id": 0, "publication_date": 1, "event_type": 1, "event_subtype": 1,
         "event_title": 1, "event_text_excerpt": 1, "section_name": 1, "registry_province": 1},
    ).sort("publication_date", -1).limit(limit).to_list(limit)

    if not rows:
        return {"identifier": identifier, "cif": cif, "available": False,
                "engine_version": ENGINE_VERSION}

    evs = [{
        "date": r.get("publication_date"),
        "type": r.get("event_type"),
        "subtype": r.get("event_subtype"),
        "title": r.get("event_title"),
        "excerpt": r.get("event_text_excerpt"),
        "section": r.get("section_name"),
        "province": r.get("registry_province"),
    } for r in rows]
    return {"identifier": identifier, "cif": cif, "available": True,
            "events": evs, "coverage": {"total": total, "returned": len(evs)},
            "engine_version": ENGINE_VERSION}


@router.get("/{identifier}/control-synergy/{buyer_identifier}")
async def control_synergy(identifier: str, buyer_identifier: str, _key=Depends(require_service_key)):
    """Facilidad de control + sinergias estimadas entre la sociedad y un comprador
    concreto (I-2 #8). `identifier`/`buyer_identifier` aceptan CIF o master_id."""
    target = await _master(identifier)
    buyer = await _master(buyer_identifier)
    if not target or not buyer:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        result = await CS.compute_control_synergy(buyer["master_id"], target["master_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"identifier": identifier, "cif": target["cif_normalized"],
            "buyer_identifier": buyer_identifier, "buyer_cif": buyer["cif_normalized"],
            "available": True, "control_synergy": result, "engine_version": ENGINE_VERSION}


@router.get("/{identifier}/signals")
async def signals(identifier: str, limit: int = 50, _key=Depends(require_service_key)):
    """Cambios/hechos relevantes de la empresa (I-3 'section/signal'): tipo, categoría,
    fecha, polaridad, severidad, título. Solo señales activas, más recientes primero."""
    master = await _master(identifier)
    if not master:
        raise HTTPException(status_code=404, detail="Company not found")
    cif = master["cif_normalized"]
    limit = max(1, min(limit, 200))
    total = await db.signals.count_documents({"master_id": master["master_id"], "status": "active"})
    rows = await db.signals.find(
        {"master_id": master["master_id"], "status": "active"},
        {"_id": 0, "signal_type": 1, "category": 1, "polarity": 1, "severity": 1,
         "explanation": 1, "confidence": 1, "trend": 1, "last_seen_at": 1, "detected_at": 1},
    ).sort("last_seen_at", -1).limit(limit).to_list(limit)
    if not rows:
        return {"identifier": identifier, "cif": cif, "available": False,
                "engine_version": ENGINE_VERSION}
    sigs = [{
        "type": r.get("signal_type"),
        "category": r.get("category"),
        "date": r.get("last_seen_at") or r.get("detected_at"),
        "polarity": r.get("polarity"),
        "severity": r.get("severity"),
        "title": r.get("explanation"),
        "confidence": r.get("confidence"),
        "trend": r.get("trend"),
    } for r in rows]
    return {"identifier": identifier, "cif": cif, "available": True,
            "signals": sigs, "coverage": {"total": total, "returned": len(sigs)},
            "engine_version": ENGINE_VERSION}


# ── Mercado/Sector por empresa (arroba.v2 'Mercado'): une sector-intelligence +
# geo-intelligence + fragmentation (HHI) + la posición relativa de la empresa. ──
_MIN_ACTORS_FOR_HHI = 5   # umbral de estabilidad del HHI (mismo espíritu que ranking: sector>=5)
_LEVEL_NAME = {"cnae_code": "group", "cnae_division": "division", "cnae_section": "section"}


def _norm_txt(s: Optional[str]) -> str:
    s = (s or "").strip().upper()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


async def _province_index():
    """{geo_id: doc} + {nombre_normalizado: geo_id} desde geo_intelligence (52 provincias)."""
    provs = await db.geo_intelligence.find({"geo_level": "province"}, {"_id": 0}).to_list(100)
    by_code = {p["geo_id"]: p for p in provs}
    name2code: Dict[str, str] = {}
    for p in provs:
        gn = p.get("geo_name") or ""
        name2code[_norm_txt(gn)] = p["geo_id"]
        for part in gn.replace("(", " ").replace(")", " ").replace(",", " ").split("/"):
            k = _norm_txt(part)
            if k:
                name2code[k] = p["geo_id"]
    return by_code, name2code


def _sector_card(s: Dict) -> Dict:
    return {k: s.get(k) for k in (
        "cnae_code", "cnae_label", "cnae_level", "size_score", "dynamism_score", "growth_score",
        "activity_score", "active_companies", "iberinform_companies", "market_share",
        "national_yoy_pct", "trend_direction", "primary_driver", "signal")}


def _geo_card(g: Dict) -> Dict:
    return {k: g.get(k) for k in (
        "geo_id", "geo_name", "geo_level", "parent_ccaa", "size_score", "dynamism_score",
        "growth_score", "revenue_growth", "employment_growth", "net_company_creation",
        "active_companies", "trend_direction", "primary_driver", "signal")}


def _conc_fields(fr: Dict) -> Dict:
    return {"cnae_field": fr.get("cnae_field"), "cnae_value": fr.get("cnae_value"),
            "hhi": fr.get("hhi"), "concentration_label": fr.get("concentration_label"),
            "market_actors_count": fr.get("market_actors_count"),
            "distinct_ownership_groups": fr.get("distinct_ownership_groups"),
            "standalone_targets_count": fr.get("standalone_targets_count"),
            "total_companies_in_universe": fr.get("total_companies_in_arroba_universe"),
            "companies_with_revenue_data": fr.get("companies_with_revenue_data"),
            "hhi_methodology": fr.get("hhi_methodology")}


async def _resolve_sector(cls: Dict) -> Optional[Dict]:
    """group (CNAE 4 díg.) → division (2 díg.) → section (letra): el primero que exista."""
    for level, code in (("group", cls.get("cnae_code")), ("division", cls.get("cnae_division")),
                        ("section", cls.get("cnae_section"))):
        if not code:
            continue
        doc = await db.sector_intelligence.find_one(
            {"cnae_code": code, "cnae_level": level, "taxonomy_type": "official_cnae"}, {"_id": 0})
        if doc:
            return doc
    return None


async def _resolve_geo(master: Dict) -> Optional[Dict]:
    """Provincia (texto) → geo_id. Principal: prefijo del código postal (2 díg = código INE
    de provincia). Fallback: nombre normalizado contra geo_name."""
    loc = master.get("location") or {}
    by_code, name2code = await _province_index()
    cp = (loc.get("codigo_postal") or "").strip()
    code = None
    if len(cp) >= 2 and cp[:2].isdigit() and cp[:2] in by_code:
        code = cp[:2]
    if code is None:
        code = name2code.get(_norm_txt(loc.get("provincia")))
    return by_code.get(code) if code else None


async def _resolve_concentration(cls: Dict) -> Dict:
    """HHI a nivel group (CNAE 4 díg.); degrada a division (2 díg.) si el universo del group
    es demasiado pequeño para un HHI estable. Devuelve available/level/degraded null-safe."""
    candidates = []
    if cls.get("cnae_code"):
        candidates.append(("cnae_code", cls["cnae_code"], 500))
    if cls.get("cnae_division"):
        candidates.append(("cnae_division", cls["cnae_division"], 1000))
    fallback = None
    for field, value, limit in candidates:
        fr = await FRAG.compute_fragmentation(field, value, limit_companies=limit)
        level = _LEVEL_NAME.get(field, field)
        block = {"available": True, "level": level, "degraded": field != "cnae_code",
                 **_conc_fields(fr)}
        if field != "cnae_code":
            block["degraded_reason"] = ("Universo del grupo CNAE (4 díg.) insuficiente para un "
                                        "HHI estable; se usa la división (2 díg.).")
        if fr.get("hhi") is not None and (fr.get("market_actors_count") or 0) >= _MIN_ACTORS_FOR_HHI:
            return block
        if fallback is None and fr.get("hhi") is not None:
            fallback = {**block, "caveat": "Universo reducido (por debajo del umbral de "
                                           "estabilidad); HHI orientativo."}
    if fallback:
        return fallback
    return {"available": False, "reason": "insufficient_universe_for_hhi"}


@router.get("/{identifier}/market")
async def market(identifier: str, _key=Depends(require_service_key)):
    """Contexto de mercado de la empresa (arroba.v2 'Mercado'): sector (tamaño/dinamismo/
    crecimiento), geografía (provincia), concentración/HHI (nivel group con degradación a
    division) y la posición relativa de la empresa. Cada bloque es null-safe (available)."""
    master = await _master(identifier)
    if not master:
        raise HTTPException(status_code=404, detail="Company not found")
    cif = master["cif_normalized"]
    cls = master.get("classification") or {}

    sector_doc = await _resolve_sector(cls)
    geo_doc = await _resolve_geo(master)
    concentration = await _resolve_concentration(cls)
    position = await FE.ranking(master)

    sector_block = ({"available": True, **_sector_card(sector_doc)}
                    if sector_doc else {"available": False, "reason": "sector_not_computed"})
    geo_block = ({"available": True, **_geo_card(geo_doc)}
                 if geo_doc else {"available": False, "reason": "province_not_resolved"})
    position_block = ({"available": True, **position}
                      if position else {"available": False, "reason": "no_revenue_for_ranking"})

    blocks = (sector_block, geo_block, concentration, position_block)
    return {
        "identifier": identifier, "cif": cif, "master_id": master["master_id"],
        "available": any(b.get("available") for b in blocks),
        "sector": sector_block,
        "geo": geo_block,
        "concentration": concentration,
        "position": position_block,
        "coverage": {"sector": sector_block.get("available", False),
                     "geo": geo_block.get("available", False),
                     "concentration": concentration.get("available", False),
                     "position": position_block.get("available", False)},
        "engine_version": ENGINE_VERSION,
    }


@router.get("/{identifier}/ficha")
async def ficha(identifier: str, _key=Depends(require_service_key)):
    """Agregador de la Ficha: identidad + finanzas + ranking + propiedad + gobierno + eventos
    en una sola llamada. Cada bloque es null-safe (Beta degrada por bloque)."""
    master = await _master(identifier)
    if not master:
        raise HTTPException(status_code=404, detail="Company not found")
    cif = master["cif_normalized"]
    finances = await FE.analyze(cif)
    return {
        "identifier": identifier, "cif": cif, "master_id": master["master_id"],
        "identity": _build_identity(master).model_dump(),
        "finances": finances,
        "ranking": (finances or {}).get("ranking"),
        "ownership": await ownership(identifier, _key=None),
        "governance": await governance(identifier, _key=None),
        "events": await events(identifier, _key=None),
        "signals": await signals(identifier, _key=None),
        "market": await market(identifier, _key=None),
        "engine_version": ENGINE_VERSION,
    }
