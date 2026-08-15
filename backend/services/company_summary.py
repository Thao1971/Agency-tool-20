"""Resumen de compañía para la ficha (solo dato real; la IA solo reformula, no inventa):

- `resolve_description`: cascada de descripción con flag de origen + caché en Mongo.
    (1) descripción oficial registral en prosa -> 'official'
    (2) IA (Nvidia) reformula el objeto social -> 'ai'   (cacheada por master_id + hash del objeto)
    (3) `web_description` (scraping web) -> 'web'
    (4) None
- `opportunity_thesis`: tesis DETERMINISTA (sector + posición + veredicto financiero) en prosa.
- `opportunity_chips`: chips de tesis (el 'qué'), derivadas del motor; solo las que puntúan.
"""
import asyncio
import hashlib
import json
import os
from typing import Dict, List, Optional

from database import db
from models import now_iso
from docstudio.model_provider import generate_company_description, generate_summary

_CACHE = "company_descriptions"   # colección aparte de la caché del /ficha
_MKT_CACHE = "market_readings"    # caché de la lectura de mercado (IA, fact-lock)
_AI_TIMEOUT = 25


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


async def resolve_description(master_id: str, identity: Dict, cnae_es: Optional[str]) -> Dict:
    """Devuelve {'description', 'description_source' in {official, ai, web} | None}."""
    objeto = (identity.get("objeto_social") or identity.get("corporate_purpose") or "").strip()
    web = (identity.get("description") or "").strip()   # hoy = web_description (scraping web)
    name = identity.get("legal_name")

    # (2) IA reformula el objeto social — cacheada por master_id + hash(objeto).
    if objeto:
        h = _hash(objeto)
        cached = await db[_CACHE].find_one({"master_id": master_id, "objeto_hash": h}, {"_id": 0})
        if cached and cached.get("description"):
            return {"description": cached["description"],
                    "description_source": cached.get("description_source", "ai")}
        res = {}
        try:
            res = await asyncio.wait_for(
                generate_company_description(objeto, cnae_es, name, provider="nvidia"),
                timeout=_AI_TIMEOUT)
        except Exception:
            res = {}
        text = (res.get("description") or "").strip() if isinstance(res, dict) else ""
        if text and "error" not in (res or {}):
            out = {"description": text, "description_source": "ai"}
            await db[_CACHE].update_one(
                {"master_id": master_id, "objeto_hash": h},
                {"$set": {**out, "master_id": master_id, "objeto_hash": h,
                          "model": res.get("_model"), "generated_at": now_iso()}}, upsert=True)
            return out
        # IA falló/timeout -> cae a web

    # (3) web
    if web:
        return {"description": web, "description_source": "web"}
    return {"description": None, "description_source": None}


def _market_reading_context(market_block: Dict) -> Optional[Dict]:
    """Extrae SOLO el dato material ya calculado del bloque market (fact-lock): nada que la
    IA no tenga delante. Las narrativas por bloque ya son prosa determinista con los hechos."""
    if not market_block or not market_block.get("available"):
        return None
    ctx: Dict = {}
    sector = market_block.get("sector") or {}
    if sector.get("available"):
        ctx["sector"] = {k: sector.get(k) for k in (
            "cnae_label", "size_score", "dynamism_score", "activity_score", "market_share",
            "trend_label", "primary_driver_label", "signal_label", "narrative")
            if sector.get(k) is not None}
    geo = market_block.get("geo") or {}
    if geo.get("available"):
        ctx["geo"] = {k: geo.get(k) for k in (
            "geo_name", "size_score", "dynamism_score", "growth_score", "trend_label", "narrative")
            if geo.get(k) is not None}
    conc = market_block.get("concentration") or {}
    if conc.get("available"):
        ctx["concentration"] = {k: conc.get(k) for k in (
            "hhi", "concentration_label_es", "level", "narrative")
            if conc.get(k) is not None}
    pos = market_block.get("position") or {}
    if pos.get("available"):
        ctx["position"] = {k: pos.get(k) for k in (
            "sector_revenue_percentile", "market_position", "locality_position", "narrative")
            if pos.get(k) is not None}
    return ctx or None


async def resolve_market_reading(master_id: str, market_block: Dict) -> Optional[str]:
    """Lectura de mercado en prosa (IA, FACT-LOCK) sobre el bloque `market` ya agregado:
    combina posición sectorial (ranking/percentil) + estado del sector + territorio +
    concentración en 2-3 frases ejecutivas. Cacheada en Mongo por master_id + hash del
    contenido material (se regenera solo si cambia el dato). Fallo/timeout/IA vacía -> None
    (Beta degrada sin bloquear). Proveedor configurable con MARKET_READING_PROVIDER (claude)."""
    ctx = _market_reading_context(market_block)
    if not ctx:
        return None
    h = _hash(json.dumps(ctx, sort_keys=True, ensure_ascii=False, default=str))
    cached = await db[_MKT_CACHE].find_one({"master_id": master_id, "ctx_hash": h}, {"_id": 0})
    if cached and cached.get("reading"):
        return cached["reading"]
    provider = os.environ.get("MARKET_READING_PROVIDER", "claude")
    res = {}
    try:
        res = await asyncio.wait_for(
            generate_summary(ctx, doc_type="market_reading", provider=provider, fact_lock=True),
            timeout=_AI_TIMEOUT)
    except Exception:
        res = {}
    text = (res.get("executive_summary") or "").strip() if isinstance(res, dict) else ""
    if text and "error" not in (res or {}):
        await db[_MKT_CACHE].update_one(
            {"master_id": master_id, "ctx_hash": h},
            {"$set": {"reading": text, "master_id": master_id, "ctx_hash": h,
                      "model": res.get("_model"), "generated_at": now_iso()}}, upsert=True)
        return text
    return None


def opportunity_thesis(finances: Dict, market: Dict) -> Dict:
    """Tesis de oportunidad DETERMINISTA: combina contexto sectorial + posicionamiento +
    veredicto financiero en prosa coherente (juicio analítico trazable, sin IA)."""
    sector = (market or {}).get("sector") or {}
    position = (market or {}).get("position") or {}
    assessment = (finances or {}).get("assessment") or {}
    segs = []
    for txt in (sector.get("narrative"), position.get("narrative"), assessment.get("verdict")):
        t = (txt or "").strip()
        if t:
            segs.append(t if t.endswith(".") else t + ".")
    return {
        "narrative": " ".join(segs) if segs else None,
        "components": {
            "sector": sector.get("narrative"),
            "position": position.get("narrative"),
            "financial_verdict": assessment.get("verdict"),
        },
    }


def opportunity_chips(signals_block: Dict, control_graph: Dict, finances: Dict) -> List[Dict]:
    """Chips de tesis (el 'qué'), derivadas del motor con dato real: solo las que puntúan.
    enum + label_es (Buy & Build se mantiene; el resto en español CF)."""
    chips = []
    sig_types = {s.get("type") for s in (signals_block or {}).get("signals", [])}
    if "ownership.consolidator" in sig_types:
        chips.append({"enum": "buy_and_build", "label_es": "Buy & Build"})
    if any(t and t.startswith("growth.") for t in sig_types):
        chips.append({"enum": "capital_raise", "label_es": "Captación de capital"})
    shareholders = (control_graph or {}).get("shareholders") or []
    has_majority = any((s.get("pct") or 0) >= 50 for s in shareholders)
    score = ((finances or {}).get("assessment") or {}).get("score") or 0
    if has_majority and score >= 50:
        chips.append({"enum": "partner_entry", "label_es": "Entrada de socio"})
    return chips
