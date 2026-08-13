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
from typing import Dict, List, Optional

from database import db
from models import now_iso
from docstudio.model_provider import generate_company_description

_CACHE = "company_descriptions"   # colección aparte de la caché del /ficha
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
