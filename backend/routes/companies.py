"""Buscador predictivo de empresas (autocompletar mientras se teclea).

GET /api/v1/companies/suggest?q=<texto>&limit=8 — público (sin auth), aditivo.
Coincidencia por PREFIJO del nombre normalizado, tolerante a tildes y a mayúsculas.
"""

from typing import Optional

from fastapi import APIRouter, Query
import re

from database import db
from services.entity_resolution import _normalize_name
from services.skills_search import _diacritic_insensitive_regex

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])

_SUGGEST_HARD_LIMIT = 20  # tope duro aunque el cliente pida más

# Formas jurídicas / siglas que se dejan en MAYÚSCULAS al pasar a "tipo título".
_LEGAL_UPPER = {"SL", "SA", "SLU", "SAU", "SLNE", "SCP", "SC", "SCA", "SAL", "SLL",
                "AIE", "UTE", "SICAV", "SRL", "SLP", "CB", "SDAD", "SAS", "SPA"}
_VOWELS = set("AEIOUÁÉÍÓÚÜ")


def _title_token(tok: str) -> str:
    """Pasa un token a Título dejando en mayúsculas lo que parece sigla/forma jurídica:
    formas con puntos (S.L., A.B.C.), abreviaturas conocidas (SL, SA, SLU…) y acrónimos
    cortos sin vocales (FSM). El resto: primera en mayúscula, resto en minúscula."""
    if not tok:
        return tok
    stripped = tok.replace(".", "")
    up = tok.upper()
    if "." in tok and len(stripped) <= 4:      # "S.L.", "A.B.C."
        return up
    if up in _LEGAL_UPPER:                      # "SL", "SA", ...
        return up
    if 1 <= len(stripped) <= 4 and stripped.isalpha() and not (set(up) & _VOWELS):
        return up                               # acrónimo corto sin vocales ("FSM", "Y")
    return tok[:1].upper() + tok[1:].lower()


def _title_case(name: str) -> str:
    """"BANCO DE DEPOSITOS" -> "Banco De Depositos", conservando siglas (ver _title_token)."""
    if not name:
        return name
    return " ".join(_title_token(t) for t in name.split(" "))


def _name_parts(name: str, prefix_re) -> dict:
    """Parte el `name` mostrado en {before, match, after} resaltando el tramo que casó
    con el prefijo tecleado. Se corre el MISMO patrón (tolerante a tildes, anclado con ^)
    contra el nombre que se devuelve al cliente (ya en formato título), no contra
    normalized_name, para que el rango sea exacto sobre el texto visible y `match` quede
    en el mismo formato que el resto del nombre. Si no casa, match vacío y after el nombre."""
    name = name or ""
    m = prefix_re.match(name)
    if not m:
        return {"before": "", "match": "", "after": name}
    s, e = m.start(), m.end()
    return {"before": name[:s], "match": name[s:e], "after": name[e:]}


@router.get("/suggest")
async def suggest(q: Optional[str] = Query(None), limit: int = Query(8)):
    """Autocompletar por prefijo de nombre. Devuelve como mucho `limit` empresas
    cuyo `normalized_name` empieza por `q` (normalizado igual que los nombres guardados,
    insensible a tildes/mayúsculas). `q` con menos de 2 caracteres → lista vacía sin tocar BD.
    El nombre se devuelve en formato título (siglas conservadas) y cada resultado incluye
    `name_parts` {before, match, after} para resaltar la coincidencia."""
    limit = max(1, min(int(limit or 0), _SUGGEST_HARD_LIMIT))
    if not q or len(q.strip()) < 2:
        return {"results": []}
    qn = _normalize_name(q)
    if len(qn) < 2:
        return {"results": []}
    pattern = "^" + _diacritic_insensitive_regex(qn)
    prefix_rx = {"$regex": pattern, "$options": "i"}
    prefix_re = re.compile(pattern, re.IGNORECASE)
    rows = await db.companies_master.find(
        {"normalized_name": prefix_rx, "merge_status": {"$ne": "merged"}},
        {"_id": 0, "master_company_id": 1, "legal_name": 1, "cif": 1, "sector": 1},
    ).sort([("financials.latest.revenue", -1), ("master_company_id", 1)]).limit(limit).to_list(limit)
    out = []
    for r in rows:
        display = _title_case(r.get("legal_name") or "")
        out.append({
            "master_company_id": r.get("master_company_id"),
            "name": display,
            "name_parts": _name_parts(display, prefix_re),
            "cif": r.get("cif"),
            "sector": r.get("sector"),
        })
    return {"results": out}
