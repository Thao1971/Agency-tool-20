"""arroba.v2 company Ficha surfaces (I-2/I-3): ownership, governance, corporate events.

Read-only, additive, X-API-Key protected. Real-data-only: every block reports its own
`coverage` and returns `available: false` cleanly when there is no data (Beta degrades to
"información en preparación"). No internal/provider vocabulary in user-facing text.
"""
from typing import Dict, List, Optional
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from services.service_auth import require_service_key
from borme.parser import normalize_company_name
from services.data_layer.master import control_synergy as CS
from services.data_layer.normalize import strip_accents
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
async def ownership(identifier: str, authenticated: bool = False, _key=Depends(require_service_key)):
    """Estructura de propiedad: accionistas, concentración y tramo de control (I-2 #6). DPD:
    `authenticated=false` (por defecto) oculta TODOS los nombres (estructura + % + tipo/tier)."""
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
        is_person, _ = _classify_holder(
            r.get("counterparty_name"), bool(r.get("counterparty_has_cif")), r.get("counterparty_cif"))
        shareholders.append({
            "name": r.get("counterparty_name"),
            "type": "individual" if is_person else "legal",
            "cif": r.get("counterparty_cif"),
            "pct": r.get("pct"),
            "as_of_year": r.get("year"),
        })

    # Fallback to the master snapshot if the normalized layer has nothing.
    if not shareholders:
        for s in ((master.get("ownership") or {}).get("shareholders") or []):
            is_person, _ = _classify_holder(s.get("name"), bool(s.get("cif")), s.get("cif"))
            shareholders.append({"name": s.get("name"), "type": "individual" if is_person else "legal",
                                 "cif": s.get("cif"), "pct": s.get("pct"), "as_of_year": None})
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

    # DPD: en anónimo se ocultan TODOS los nombres (estructura + % + tipo/tier).
    if not authenticated:
        for i, s in enumerate(shareholders):
            s["name"] = "Accionista principal" if i == 0 else f"Accionista {i + 1}"
            s["cif"] = None

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
        "role_es": _role_es(r.get("role")),
        "since": r.get("appointment_date"),
        "year": r.get("year"),
    } for r in best.values()]
    officers.sort(key=lambda o: (o["year"] or 0), reverse=True)

    if not officers:
        return {"identifier": identifier, "cif": cif, "available": False,
                "engine_version": ENGINE_VERSION}
    role_labels = {o["role"]: o["role_es"] for o in officers if o.get("role")}
    return {"identifier": identifier, "cif": cif, "available": True,
            "officers": officers, "governance_role_labels_es": role_labels,
            "coverage": {"officers_count": len(officers)},
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
        "national_yoy_pct", "trend_direction", "primary_driver", "signal")} | {
        "signal_label": _SIGNAL_LABELS.get(s.get("signal")),
        "primary_driver_label": _DRIVER_LABELS.get(s.get("primary_driver")),
        "trend_label": _TREND_LABELS_ES.get(s.get("trend_direction"))}


def _geo_card(g: Dict) -> Dict:
    return {k: g.get(k) for k in (
        "geo_id", "geo_name", "geo_level", "parent_ccaa", "size_score", "dynamism_score",
        "growth_score", "revenue_growth", "employment_growth", "net_company_creation",
        "active_companies", "trend_direction", "primary_driver", "signal")} | {
        "signal_label": _SIGNAL_LABELS.get(g.get("signal")),
        "primary_driver_label": _DRIVER_LABELS.get(g.get("primary_driver")),
        "trend_label": _TREND_LABELS_ES.get(g.get("trend_direction"))}


def _conc_fields(fr: Dict) -> Dict:
    return {"cnae_field": fr.get("cnae_field"), "cnae_value": fr.get("cnae_value"),
            "hhi": fr.get("hhi"), "concentration_label": fr.get("concentration_label"),
            "concentration_label_es": _CONC_LABELS_ES.get(fr.get("concentration_label")),
            "market_actors_count": fr.get("market_actors_count"),
            "distinct_ownership_groups": fr.get("distinct_ownership_groups"),
            "standalone_targets_count": fr.get("standalone_targets_count"),
            "companies_in_sector": fr.get("total_companies_in_arroba_universe"),
            "companies_with_revenue_data": fr.get("companies_with_revenue_data")}


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
            block["degraded_reason"] = ("La lectura se ha ampliado al conjunto del sector por "
                                        "disponibilidad de datos comparables; conviene tomarla como orientativa.")
        if fr.get("hhi") is not None and (fr.get("market_actors_count") or 0) >= _MIN_ACTORS_FOR_HHI:
            return block
        if fallback is None and fr.get("hhi") is not None:
            fallback = {**block, "caveat": "El reducido número de compañías comparables aconseja "
                                           "tomar esta lectura como orientativa."}
    if fallback:
        return fallback
    return {"available": False, "reason": "insufficient_universe_for_hhi"}


# ── Traducción determinista enum→prosa CF (canon §2) + composición de narrativa por bloque ──
_SIGNAL_PROSE = {
    "sector_contraction": "se encuentra en contracción",
    "growth_momentum": "muestra impulso de crecimiento",
    "corporate_hub": "es una plaza empresarial de primer nivel, con gran concentración de actividad",
    "stable_activity": "mantiene una actividad estable",
    "stable_territory": "mantiene una actividad estable",
    "high_activity": "muestra una actividad elevada",
    "low_activity": "muestra una actividad reducida",
    "declining_activity": "muestra una actividad en descenso",
}
_TREND_PROSE = {"down": "a la baja", "up": "al alza", "flat": "estable", "stable": "estable"}
_CONC_PROSE = {"highly_concentrated": "un mercado muy concentrado",
               "moderately_concentrated": "un mercado moderadamente concentrado",
               "unconcentrated": "un mercado poco concentrado y fragmentado"}

# ── Batch de labels ES (canon): etiqueta corta por enum; el enum crudo se conserva como metadato. ──
_SIGNAL_LABELS = {
    "sector_contraction": "Sector en contracción",
    "growth_momentum": "Impulso de crecimiento",
    "corporate_hub": "Plaza empresarial de primer nivel",
    "stable_activity": "Actividad estable",
    "stable_territory": "Territorio estable",
    "high_activity": "Actividad elevada",
    "low_activity": "Actividad reducida",
    "declining_activity": "Actividad en descenso",
}
_DRIVER_LABELS = {"activity": "Actividad", "growth": "Crecimiento", "size": "Tamaño de mercado"}
_CONC_LABELS_ES = {"highly_concentrated": "Muy concentrado",
                   "moderately_concentrated": "Moderadamente concentrado",
                   "unconcentrated": "Poco concentrado"}
_TREND_LABELS_ES = {"down": "A la baja", "up": "Al alza", "flat": "Estable", "stable": "Estable"}

# Roles de gobierno (norm_officers): 192 variantes, mayoría en inglés → canon ES.
_ROLE_ES = {
    "Representative": "Representante",
    "Sole Director": "Administrador único",
    "Joint And Several Director": "Administrador solidario",
    "Director": "Consejero",
    "Joint Director": "Administrador mancomunado",
    "Chairperson": "Presidente",
    "Secretary": "Secretario",
    "Auditor": "Auditor de cuentas",
    "Director Member": "Vocal del consejo",
    "Joint And Several Chief Executive Officer": "Consejero delegado solidario",
    "Chief Executive Officer": "Consejero delegado",
    "Delegate Joint Director": "Consejero delegado mancomunado",
    "Joint And Several Representative": "Representante solidario",
    "Controlling Committee Member": "Miembro de la comisión de control",
    "Member": "Vocal",
    "Member Of The Committee": "Miembro de la comisión",
    "Vice-Chairperson": "Vicepresidente",
    "Member Of The Controlling Committee": "Miembro de la comisión de control",
    "Accounts Auditor": "Auditor de cuentas",
    "Committee Member": "Miembro de la comisión",
    "Professional Partner": "Socio profesional",
    "Bankruptcy Administrator": "Administrador concursal",
    "Non-Director Secretary": "Secretario no consejero",
    "Representative Art. 143 Rrm": "Representante (art. 143 RRM)",
    "Partner": "Socio",
    "Joint Representative": "Representante mancomunado",
    "Depositary Entity": "Entidad depositaria",
    "Managing Entity": "Entidad gestora",
    "Alternate Auditor": "Auditor suplente",
    "Vice-Secretary": "Vicesecretario",
    "Liquidator": "Liquidador",
    "Manager": "Gerente",
    "Sole Shareholder": "Socio único",
    "Joint Accounts Auditor": "Auditor de cuentas conjunto",
    "Committee Chairperson": "Presidente de la comisión",
    "Joint And Joint And Several Delegate Director": "Consejero delegado mancomunado y solidario",
    "Member Of The Board": "Vocal del consejo",
    "Sole Chief Executive Officer": "Consejero delegado único",
    "Supervisor": "Supervisor",
    "Non-Director Vice-Secretary": "Vicesecretario no consejero",
    "Director Secretary": "Consejero secretario",
    "Alternate Director": "Consejero suplente",
    "Secretary To The Controlling Committee": "Secretario de la comisión de control",
    "Depositary": "Depositario",
    "Chairperson Of The Controlling Committee": "Presidente de la comisión de control",
    "Advisor": "Asesor",
    "Alternate": "Suplente",
    "Attorney": "Apoderado",
    "Vice-Chairperson Of The Board": "Vicepresidente del consejo",
    "Chairperson Of The Board": "Presidente del consejo",
    "Chairperson Of The Board Of Directors": "Presidente del consejo de administración",
    "Board Of Directors' Member": "Vocal del consejo de administración",
    "Board": "Consejo de administración",
    "Treasurer": "Tesorero",
    "Accountant": "Contador",
}


def _role_es(role: Optional[str]) -> Optional[str]:
    if not role:
        return None
    return _ROLE_ES.get(role) or _ROLE_ES.get(role.strip()) or role


def _score_word(v) -> Optional[str]:
    if v is None:
        return None
    return "elevado" if v >= 66 else "moderado" if v >= 34 else "reducido"


def _pct_num_es(v) -> Optional[str]:
    """Formatea un valor ya en porcentaje (p.ej. -15.4) a prosa española: '15,4%'."""
    if not isinstance(v, (int, float)):
        return None
    return f"{abs(v):.1f}".replace(".", ",") + "%"


def _sector_narrative(s: Dict) -> Optional[str]:
    name = (s.get("cnae_label") or "").strip()
    if not name:
        return None
    parts = []
    sig = _SIGNAL_PROSE.get(s.get("signal"))
    first = f"El sector de {name.lower()} {sig}" if sig else \
            f"El sector de {name.lower()} se mantiene dentro de sus parámetros habituales"
    yoy = s.get("national_yoy_pct")
    if isinstance(yoy, (int, float)) and abs(yoy) >= 0.1:
        verb = "una caída" if yoy < 0 else "un avance"
        first += f", con {verb} de actividad del {_pct_num_es(yoy)} en el último año"
    parts.append(first + ".")
    dyn = _score_word(s.get("dynamism_score"))
    trend = _TREND_PROSE.get(s.get("trend_direction"))
    if dyn and trend:
        parts.append(f"El dinamismo del sector es {dyn} y su evolución, {trend}.")
    elif dyn:
        parts.append(f"El dinamismo del sector es {dyn}.")
    return " ".join(parts)


def _geo_narrative(g: Dict) -> Optional[str]:
    name = (g.get("geo_name") or "").strip()
    if not name:
        return None
    size = g.get("size_score")
    if g.get("signal") == "corporate_hub":
        sizeq = "una plaza empresarial de primer nivel, con gran concentración de actividad"
    elif size is None:
        sizeq = "una plaza empresarial"
    else:
        sizeq = ("una plaza empresarial de primer nivel" if size >= 80
                 else "una plaza de tamaño medio" if size >= 40 else "una plaza de menor tamaño")
    first = f"{name} es {sizeq}"
    dyn = _score_word(g.get("dynamism_score"))
    if dyn:
        first += f" y {dyn} dinamismo"
    ncc = g.get("net_company_creation")
    if isinstance(ncc, (int, float)) and ncc != 0:
        first += f", con creación neta de empresas {'positiva' if ncc > 0 else 'negativa'} en el último ejercicio"
    return first + "."


def _concentration_narrative(c: Dict, sector_name: Optional[str]) -> Optional[str]:
    if not c.get("available"):
        return None
    label = _CONC_PROSE.get(c.get("concentration_label"))
    if not label:
        return None
    head = f"Es {label}"
    if c.get("concentration_label") == "highly_concentrated":
        head += ", en manos de unos pocos operadores"
    elif c.get("concentration_label") == "unconcentrated":
        head += ", con numerosos operadores independientes"
    head += "."
    tail = []
    if c.get("degraded"):
        sect = f"del sector {sector_name.lower()}" if sector_name else "del conjunto del sector"
        tail.append(f"El análisis se ha ampliado al conjunto {sect} por disponibilidad de datos "
                    "comparables; la lectura de concentración es, por tanto, orientativa.")
    elif c.get("caveat"):
        tail.append("El reducido número de compañías comparables aconseja tomar esta lectura como orientativa.")
    return " ".join([head] + tail)


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

    # Prosa CF por bloque (una sola vez, en Intel — R13). position.narrative viene de ranking().
    if sector_block.get("available"):
        sector_block["narrative"] = _sector_narrative(sector_doc)
    if geo_block.get("available"):
        geo_block["narrative"] = _geo_narrative(geo_doc)
    if concentration.get("available"):
        concentration["narrative"] = _concentration_narrative(
            concentration, (sector_doc or {}).get("cnae_label"))

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


# ── Propiedad / grafo de control (mockup): accionistas → compañía → participadas ──
# DPD: personas físicas anonimizadas; personas jurídicas con nombre (canon + ownership).
_LEGAL_MARKERS = {
    "sa", "sl", "slu", "sau", "scp", "sc", "sll", "slne", "coop", "aie", "ag", "bv", "nv",
    "gmbh", "ltd", "llc", "inc", "plc", "spa", "sarl", "sas", "sca", "sccl", "srl", "oy", "ab", "as",
    "holding", "holdings", "group", "grupo", "partners", "capital", "invest", "inversiones",
    "ventures", "fund", "fondo", "fundacion", "asociacion", "ayuntamiento", "generalitat",
    "sociedad", "company", "corp", "corporation", "limited", "international", "co", "sl.", "sa.",
}
_PERSON_TITLES = ("d. ", "d ", "dna", "dna.", "don ", "dona ", "sr.", "sra.", "sr ", "sra ")
_DOTTED_LEGAL = re.compile(r"\b(b\.?v|n\.?v|s\.?a|s\.?l|s\.?p\.?a|s\.?a\.?r\.?l|ltd|inc|gmbh)\b")


def _classify_holder(name: Optional[str], has_cif: bool, cif: Optional[str]):
    """(is_person, display_name). Persona jurídica si tiene CIF o marcador legal; persona
    física si título ('D.'/'DÑA.') o patrón 'APELLIDOS, NOMBRE'. DPD: anonimiza a la física."""
    raw = (name or "").strip()
    if has_cif or (cif and re.match(r"^[A-Za-z]", cif or "")):
        return False, raw
    low = strip_accents(raw).lower()
    toks = set(re.sub(r"[^a-z0-9 ]", " ", low).split())
    if toks & _LEGAL_MARKERS or _DOTTED_LEGAL.search(low):
        return False, raw
    if low.startswith(_PERSON_TITLES) or ("," in raw):
        return True, "Persona física"
    return False, raw


def _control_label(pct) -> Optional[str]:
    """Tier de control de una participada en prosa (sin umbral crudo)."""
    if pct is None:
        return None
    if pct >= 99.5:
        return "control total"
    if pct > 50:
        return "mayoritaria"
    if pct >= 10:
        return "significativa"
    return "participación minoritaria"


def _ubo_kind(name: Optional[str], is_person: bool) -> str:
    if is_person:
        return "control familiar"
    low = (name or "").lower()
    if "holding" in low:
        return "holding"
    if any(t in low for t in ("capital", "fund", "fondo", "partners", "ventures", "invest")):
        return "fondo"
    return "sociedad matriz"


def _pct_es(p) -> Optional[str]:
    return f"{p:.1f}".replace(".", ",").rstrip("0").rstrip(",") + "%" if isinstance(p, (int, float)) else None


def _control_narrative(role, shareholders, subsidiaries, authenticated) -> str:
    """Prosa CF (§2), registro analista M&A. Anónimo: sin nombres ('su accionista principal')."""
    parts = []
    ctrl = next((s for s in shareholders if (s.get("pct") or 0) > 50), None)
    if ctrl:
        who = ctrl["name"] if authenticated else "su accionista principal"
        seg = f"Compañía controlada por {who}"
        if ctrl.get("pct") is not None:
            seg += f" con una participación del {_pct_es(ctrl['pct'])}"
        parts.append(seg + ".")
    elif shareholders:
        n = len(shareholders)
        if n == 1:
            who = shareholders[0]["name"] if authenticated else "un único accionista"
            parts.append(f"Participada por {who}.")
        else:
            parts.append(f"Accionariado repartido entre {n} socios, sin una posición de control mayoritaria.")
    if subsidiaries:
        n = len(subsidiaries)
        full = sum(1 for d in subsidiaries if (d.get("pct") or 0) >= 99.5)
        maj = sum(1 for d in subsidiaries if (d.get("pct") or 0) > 50)
        plural = "participada" if n == 1 else "participadas"
        if full == n:
            parts.append(f"Cabecera de un grupo con control total en sus {n} {plural} — plataforma "
                         "consolidada, idónea para integrar más activos.")
        elif maj == n:
            parts.append(f"Cabecera de un grupo con control mayoritario en sus {n} {plural}.")
        elif maj:
            parts.append(f"Cabecera de un grupo: {maj} de {n} {plural} bajo control mayoritario.")
        else:
            parts.append(f"Mantiene participaciones en {n} {plural}.")
    if not parts:
        return "Sin estructura de propiedad registrada."
    return " ".join(parts)


async def _control_graph_block(master: Dict, authenticated: bool = False, max_subs: int = 100) -> Dict:
    """Bloque `control_graph` (spec PARA_INTEL): accionistas → compañía → participadas + UBO,
    tres vistas (árbol via shareholders/subsidiaries, distribution[], graph.nodes/edges) + narrative.
    DPD: authenticated=False oculta TODOS los nombres (estructura + % + tiers)."""
    cif = master["cif_normalized"]
    ident = master.get("identity") or {}
    loc = master.get("location") or {}
    company_name = ident.get("legal_name")
    rows = await db.norm_ownership.find({"src_cif": cif}, {"_id": 0}).to_list(1000)

    up_best: Dict[str, Dict] = {}
    down_best: Dict[str, Dict] = {}
    for r in rows:
        rt = r.get("relationship_type")
        key = r.get("counterparty_key") or (r.get("counterparty_name") or "").lower()
        if not key:
            continue
        bucket = down_best if rt == "investee_co" else up_best if rt in ("shareholder", "parent_co") else None
        if bucket is None:
            continue
        cur = bucket.get(key)
        if cur is None or (r.get("year") or 0) > (cur.get("year") or 0) or \
                ((r.get("year") or 0) == (cur.get("year") or 0) and (r.get("pct") or 0) > (cur.get("pct") or 0)):
            bucket[key] = r

    cps = [r.get("counterparty_cif") for r in list(up_best.values()) + list(down_best.values()) if r.get("counterparty_cif")]
    info_by_cif: Dict[str, Dict] = {}
    if cps:
        async for m in db.master_companies.find(
                {"cif_normalized": {"$in": cps}},
                {"_id": 0, "cif_normalized": 1, "master_id": 1, "identity.legal_name": 1,
                 "classification.cnae_description": 1}):
            info_by_cif[m["cif_normalized"]] = m

    years = [r.get("year") for r in rows if r.get("year")]
    as_of_year = max(years) if years else None

    shareholders = []
    for r in up_best.values():
        is_person, _ = _classify_holder(r.get("counterparty_name"), bool(r.get("counterparty_has_cif")), r.get("counterparty_cif"))
        cp_cif = r.get("counterparty_cif")
        info = info_by_cif.get(cp_cif) if cp_cif else None
        canonical = (info.get("identity") or {}).get("legal_name") if info else None
        shareholders.append({
            "_name": canonical or r.get("counterparty_name"),
            "type": "individual" if is_person else "legal",
            "pct": r.get("pct"), "cif": cp_cif,
            "master_id": info.get("master_id") if info else None,
            "is_ubo": False, "_is_parent": r.get("relationship_type") == "parent_co",
            "_is_self": bool(cp_cif and cp_cif == cif),
        })
    shareholders.sort(key=lambda s: (s["pct"] is not None, s["pct"] or 0), reverse=True)

    subsidiaries = []
    for r in down_best.values():
        cp_cif = r.get("counterparty_cif")
        info = info_by_cif.get(cp_cif) if cp_cif else None
        subsidiaries.append({
            "_name": ((info.get("identity") or {}).get("legal_name") if info else None) or r.get("counterparty_name"),
            "cif": cp_cif, "master_id": info.get("master_id") if info else None,
            "pct": r.get("pct"),
            "activity": (info.get("classification") or {}).get("cnae_description") if info else None,
            "control_label": _control_label(r.get("pct")),
        })
    subsidiaries.sort(key=lambda d: (d["pct"] is not None, d["pct"] or 0), reverse=True)
    truncated = len(subsidiaries) > max_subs
    subsidiaries = subsidiaries[:max_subs]

    if not shareholders and not subsidiaries:
        return {"available": False, "reason": "no_control_graph"}

    ubo_src = next((s for s in shareholders if s["_is_parent"]), None) or \
              next((s for s in shareholders if (s.get("pct") or 0) > 50), None)
    if ubo_src:
        ubo_src["is_ubo"] = True

    role = "holding" if subsidiaries else ("target" if shareholders else "standalone")

    def _name(kind, idx, real):
        if authenticated:
            return real
        if kind == "shareholder":
            return "Accionista principal" if idx == 0 else f"Accionista {idx + 1}"
        if kind == "subsidiary":
            return f"Participada {idx + 1}"
        if kind == "ubo":
            return "Beneficiario último"
        return real

    def _sh_label(s):
        if s["_is_self"]:
            return "autocartera / acciones propias"
        if s["is_ubo"]:
            return f"UBO · {_ubo_kind(s['_name'], s['type'] == 'individual')}"
        return None

    out_sh = [{
        "name": _name("shareholder", i, s["_name"]), "type": s["type"], "pct": s["pct"],
        "label": _sh_label(s), "cif": (s["cif"] if authenticated else None),
        "master_id": (s["master_id"] if authenticated else None), "is_ubo": s["is_ubo"],
    } for i, s in enumerate(shareholders)]

    out_subs = [{
        "name": _name("subsidiary", i, d["_name"]), "cif": (d["cif"] if authenticated else None),
        "master_id": (d["master_id"] if authenticated else None), "pct": d["pct"],
        "activity": d["activity"], "control_label": d["control_label"],
    } for i, d in enumerate(subsidiaries)]

    ubo = None
    if ubo_src:
        ubo = {"name": (ubo_src["_name"] if authenticated else "Beneficiario último"),
               "type": ubo_src["type"], "kind": _ubo_kind(ubo_src["_name"], ubo_src["type"] == "individual"),
               "pct_effective": ubo_src.get("pct")}

    distribution = []
    total = 0.0
    for s in out_sh:
        p = s["pct"]
        tone = "primary" if (s["is_ubo"] or (p or 0) > 50) else ("muted" if (p or 0) < 5 else "neutral")
        distribution.append({"label": s["name"], "pct": p, "tone": tone})
        total += p or 0
    if total and total < 99:
        distribution.append({"label": "No identificado", "pct": round(100 - total, 1), "tone": "muted"})

    nodes = [{"id": "company", "label": company_name, "kind": "company"}]
    edges = []
    for i, s in enumerate(out_sh):
        nid = f"sh{i + 1}"
        nodes.append({"id": nid, "label": s["name"], "kind": "ubo" if s["is_ubo"] else "shareholder"})
        edges.append({"from": nid, "to": "company", "pct": s["pct"]})
    for i, d in enumerate(out_subs):
        nid = f"sub{i + 1}"
        nodes.append({"id": nid, "label": d["name"], "kind": "subsidiary"})
        edges.append({"from": "company", "to": nid, "pct": d["pct"]})

    return {
        "available": True,
        "as_of_year": as_of_year,
        "company": {"name": company_name, "cif": cif, "locality": loc.get("municipio"), "role": role},
        "shareholders": out_sh,
        "ubo": ubo,
        "subsidiaries": out_subs,
        "distribution": distribution,
        "graph": {"nodes": nodes, "edges": edges},
        "narrative": _control_narrative(role, out_sh, out_subs, authenticated),
        "coverage": {"shareholders": bool(out_sh), "subsidiaries": bool(out_subs),
                     "ubo": ubo is not None, "truncated": truncated},
        "engine_version": ENGINE_VERSION,
    }


@router.get("/{identifier}/control-graph")
async def control_graph(identifier: str, authenticated: bool = False, _key=Depends(require_service_key)):
    """Grafo de control (Propiedad, spec PARA_INTEL): shareholders → compañía → subsidiaries +
    UBO + distribution[] + graph{nodes,edges} + narrative CF. Null-safe/degradado. DPD:
    `authenticated=false` (por defecto) oculta TODOS los nombres (estructura + % + tiers);
    `authenticated=true` = detalle nominal."""
    master = await _master(identifier)
    if not master:
        raise HTTPException(status_code=404, detail="Company not found")
    out = await _control_graph_block(master, authenticated=authenticated)
    return {"identifier": identifier, "cif": master["cif_normalized"], **out}


@router.get("/{identifier}/ficha")
async def ficha(identifier: str, authenticated: bool = False, _key=Depends(require_service_key)):
    """Agregador de la Ficha: identidad + finanzas + ranking + propiedad + gobierno + eventos
    en una sola llamada. Cada bloque es null-safe (Beta degrada por bloque). DPD: `authenticated`
    (por defecto false) oculta los nombres de propiedad (ownership + control_graph)."""
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
        "ownership": await ownership(identifier, authenticated=authenticated, _key=None),
        "governance": await governance(identifier, _key=None),
        "events": await events(identifier, _key=None),
        "signals": await signals(identifier, _key=None),
        "market": await market(identifier, _key=None),
        "control_graph": await _control_graph_block(master, authenticated=authenticated),
        "engine_version": ENGINE_VERSION,
    }
