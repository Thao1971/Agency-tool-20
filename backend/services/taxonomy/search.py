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


def _stem_token(w: str) -> str:
    """Raíz ligera ES: quita plural (-es/-s) y vocal final de género (-o/-a) para casar
    'farmacéutico'/'farmacéutica'/'farmacéuticas' → 'farmaceutic'. Conserva palabras cortas."""
    if len(w) <= 4:
        return w
    if w.endswith("es"):
        w = w[:-2]
    elif w.endswith("s"):
        w = w[:-1]
    if len(w) > 4 and w[-1] in "oa":
        w = w[:-1]
    return w


def _stem(s: str) -> str:
    return " ".join(_stem_token(w) for w in s.split())


def _phrase_in(a: str, b: str) -> bool:
    """True si `a` aparece en `b` como frase completa a nivel de palabra (no dentro de otra palabra)."""
    return a == b or (" " + a + " ") in (" " + b + " ")


# Índice con raíz precomputada: (stem_label, norm_label, value). Evita re-stemizar en cada consulta.
_STEM_ITEMS = [(_stem(k), k, v) for k, v in _LABEL_IDX.items()]

# Prioridad por nivel al resolver un texto ambiguo ("salud" → sector S05, no la categoría "Salud").
_KIND_PRIO = {"sector": 0, "industry": 1, "verticals": 2, "business_models": 3, "technologies": 3,
              "client_types": 3, "value_chain": 3, "capabilities": 3, "category": 4}

# Palabras de relleno de una consulta en lenguaje natural ("busca empresas del sector X") que no
# aportan a la resolución de la etiqueta. Se descartan antes de generar n-gramas.
_STOPWORDS = {
    "busca", "buscar", "buscame", "dame", "damos", "muestra", "muestrame", "ensename",
    "quiero", "ver", "listado", "lista", "listame", "cuales", "cual", "son", "hay",
    "empresas", "empresa", "companias", "compania", "companies", "firmas", "firma",
    "sector", "sectores", "industria", "industrias", "vertical", "verticales", "segmento",
    "segmentos", "mercado", "mercados", "actividad", "categoria", "categorias",
    "del", "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "en", "con",
    "que", "como", "y", "o", "a", "al", "sobre", "me", "por", "para", "mi", "tu", "su",
}


def resolve_label(text: str) -> Optional[Dict]:
    """Mapea un texto libre ('salud', 'adtech', 'sector farmacéutico', 'busca empresas de fintech'…)
    a {id, kind, label}. Tolera frases completas: descarta palabras de relleno, prueba n-gramas de
    mayor a menor y agrega todos los candidatos. El emparejamiento es por LÍMITE DE PALABRA sobre
    raíces (tolera género/plural: 'farmacéutico'→'farmacéutica', pero NO 'tecnología' dentro de
    'biotecnología'). Prioriza el n-grama más largo, luego el nivel más alto
    (sector > industria > dimensión > categoría), luego coincidencia exacta y la etiqueta más corta."""
    t = _norm(text)
    if not t:
        return None

    tokens = [w for w in t.split() if w and w not in _STOPWORDS]
    if not tokens:
        tokens = t.split()

    ngrams: List[str] = []
    n = len(tokens)
    for size in range(n, 0, -1):
        for i in range(0, n - size + 1):
            ngrams.append(" ".join(tokens[i:i + size]))

    cands: List = []
    for g in ngrams:
        gs, gl = _stem(g), len(g)
        for ks, k, v in _STEM_ITEMS:
            exact = (k == g)
            if not exact and gl < 4:
                continue
            if exact or _phrase_in(gs, ks) or _phrase_in(ks, gs):
                cands.append((gl, _KIND_PRIO.get(v["kind"], 5), 0 if exact else 1,
                              len(v["label"]), v))
    if not cands:
        return None
    cands.sort(key=lambda c: (-c[0], c[1], c[2], c[3]))
    return cands[0][4]


async def sector_counts() -> List[Dict]:
    """Sectores con nº de empresas cuya actividad PRINCIPAL es ese sector (para los chips del Copilot)."""
    labels = {n["id"]: n["label_es"] for n in REG.build_nodes() if n["level"] == "sector"}
    out = []
    for sid, label in labels.items():
        try:
            from database import db
            c = await db.company_classifications.count_documents(
                {"axis": "sector", "taxonomy_id": sid, "role": "primary"})
        except Exception:
            c = 0
        out.append({"id": sid, "label": label, "count": c})
    return sorted(out, key=lambda x: -x["count"])


async def resolve_company_by_name(name: str) -> Optional[Dict]:
    """Resuelve un nombre de empresa a master_id (best-effort, por identity.legal_name)."""
    if not name or len(name.strip()) < 3:
        return None
    try:
        import re as _re
        from database import db
        rx = _re.compile(_re.escape(name.strip()), _re.I)
        d = await db.master_companies.find_one({"identity.legal_name": rx},
                                               {"_id": 0, "master_id": 1, "identity.legal_name": 1})
        if d:
            return {"company_id": d.get("master_id"), "name": (d.get("identity") or {}).get("legal_name")}
    except Exception:
        pass
    return None


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
