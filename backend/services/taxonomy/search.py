"""Búsqueda por taxonomía ARROBA (F5) — DOBLE MODO: "cualquier clasificación" vs "solo actividad
principal" (Primary Industry). Consulta company_classifications. Incluye resolución de una etiqueta de
texto (p. ej. "salud", "adtech") al id de nodo/dimensión, para el Copilot. Ver canon §Primary Industry.
"""

import re
import unicodedata
from typing import Dict, List, Optional

from services.taxonomy import registry as REG


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


# Índice etiqueta→(id, kind) para resolver texto a nodo/dimensión (una vez).
def _build_label_index():
    idx: Dict[str, Dict] = {}
    for n in REG.build_nodes():
        idx.setdefault(_norm(n["label_es"]), {"id": n["id"], "kind": n["level"], "label": n["label_es"]})
    for d in REG.build_dimensions():
        idx.setdefault(_norm(d["label_es"]), {"id": d["id"], "kind": d["dimension"], "label": d["label_es"]})
    return idx


_LABEL_IDX = _build_label_index()
_IS_NODE = {"sector", "industry", "category"}
# Prioridad por nivel al resolver un texto ambiguo ("salud" → sector S05, no la categoría "Salud").
_KIND_PRIO = {"sector": 0, "industry": 1, "verticals": 2, "business_models": 3, "technologies": 3,
              "client_types": 3, "value_chain": 3, "capabilities": 3, "category": 4}


def resolve_label(text: str) -> Optional[Dict]:
    """Mapea un texto ('salud', 'adtech', 'tecnología'…) a {id, kind, label}. Prioriza el nivel más alto
    (sector > industria > dimensión > categoría) y, a igualdad, la etiqueta más corta."""
    t = _norm(text)
    if not t:
        return None
    cands = [v for k, v in _LABEL_IDX.items()
             if k == t or (len(k) >= 4 and (t in k or k in t)) or (len(t) >= 4 and t in k)]
    if not cands:
        return None
    return sorted(cands, key=lambda v: (_KIND_PRIO.get(v["kind"], 5), len(v["label"])))[0]


async def search_by_taxonomy(node_id: Optional[str] = None, dimension_id: Optional[str] = None,
                             primary_only: bool = False, limit: int = 50, offset: int = 0) -> Dict:
    """Empresas clasificadas bajo un nodo (sector/industria/categoría) o dimensión (vertical, etc.).
    primary_only=True → solo cuando ese nodo es la actividad PRINCIPAL (role=primary)."""
    target = node_id or dimension_id
    if not target:
        return {"count": 0, "company_ids": [], "note": "Indica node_id o dimension_id."}
    q: Dict = {"taxonomy_id": target}
    if node_id and primary_only:
        q["role"] = "primary"
    try:
        from database import db
        ids: List[str] = []
        async for r in db.company_classifications.find(q, {"_id": 0, "company_id": 1}) \
                .sort("confidence", -1).skip(offset).limit(limit):
            ids.append(r["company_id"])
        total = await db.company_classifications.count_documents(q)
        sample = []
        if ids:
            async for m in db.master_companies.find(
                    {"master_id": {"$in": ids[:10]}},
                    {"_id": 0, "master_id": 1, "identity.legal_name": 1}):
                sample.append({"company_id": m["master_id"],
                               "legal_name": (m.get("identity") or {}).get("legal_name")})
    except Exception:
        ids, total, sample = [], 0, []
    return {"taxonomy_id": target, "primary_only": bool(node_id and primary_only),
            "count": total, "returned": len(ids), "company_ids": ids, "sample": sample}
