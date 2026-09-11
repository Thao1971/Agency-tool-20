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
        idx.setdefault(_norm(n["label_es"]), {"id": n["id"], "kind": n["level"],
                                              "label": n["label_es"], "parent_id": n.get("parent_id")})
    for d in REG.build_dimensions():
        idx.setdefault(_norm(d["label_es"]), {"id": d["id"], "kind": d["dimension"],
                                              "label": d["label_es"], "parent_id": None})
    return idx


_LABEL_IDX = _build_label_index()
_IS_NODE = {"sector", "industry", "category"}

# Mapa id→nodo (id, kind, label) para resolver el PADRE COMÚN en desempates de términos
# genéricos (BUGFIX taxonomía "software"): ver el bloque final de resolve_label.
_NODE_BY_ID: Dict[str, Dict] = {
    n["id"]: {"id": n["id"], "kind": n["level"], "label": n["label_es"]}
    for n in REG.build_nodes()
}


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

# Nº mínimo de hojas empatadas (mismo n-grama/nivel/exactitud) que comparten un único padre para
# resolver al PADRE en lugar de a una hoja arbitraria (BUGFIX taxonomía "software"). Se pone en 3
# a propósito: un término realmente genérico casa muchas hojas del sector (p. ej. "software" casa
# 6 industrias de S02 → Tecnología), mientras que un empate de 2 suele ser un par de sinónimos
# cercanos donde una hoja SÍ es la respuesta canónica (p. ej. "farmaceutico" empata "Industria
# farmacéutica" con "CRO y servicios farmacéuticos" → debe quedarse en "Industria farmacéutica").
_GENERIC_PARENT_MIN_TIES = 3

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


def _strip_stopwords(t: str) -> str:
    """BUGFIX-2026-08-29 · quita las mismas palabras de relleno que ya usa el
    emparejamiento por n-gramas mas abajo, pero aplicado tambien al chequeo de
    ALIAS CURADOS (ver _build_alias_overrides/resolve_label). Antes los alias
    solo casaban contra la frase tal cual, asi que un alias curado como
    "agencias de marketing" NO reconocia "agencias marketing" (sin "de") como
    la misma frase, y la consulta caia al emparejamiento difuso generico -- que
    para una palabra tan comun como "agencias" puede resolver a la categoria
    equivocada (ej. "Agencias" de viajes, ver comentario en NODE_ALIASES de
    registry.py). Si tras quitar relleno no queda nada, devolvemos el texto
    original (evita vaciar consultas de una sola stopword)."""
    tokens = [w for w in t.split() if w and w not in _STOPWORDS]
    return " ".join(tokens) if tokens else t


# Overrides deterministas por alias de nodo (frase con límite de palabra, más largo primero).
# Se comprueban ANTES del emparejamiento difuso → garantizan la resolución de expresiones curadas.
# Cada entrada guarda la forma normalizada del alias (na) Y su forma sin
# conectores (na_sw) — ver resolve_label, que compara la consulta contra
# ambas, así "agencias de marketing" y "agencias marketing" casan con el
# mismo alias curado sin tener que listar cada variante a mano.
def _build_alias_overrides():
    by_id: Dict[str, Dict] = {}
    for n in REG.build_nodes():
        by_id[n["id"]] = {"id": n["id"], "kind": n["level"], "label": n["label_es"]}
    items = []
    for n in REG.build_nodes():
        for a in (n.get("aliases") or []):
            na = _norm(a)
            if na:
                items.append((na, _strip_stopwords(na), by_id[n["id"]]))
    items.sort(key=lambda x: -len(x[0]))
    return items


_ALIAS_OVERRIDES = _build_alias_overrides()


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
    t_sw = _strip_stopwords(t)

    # Alias curados (determinista): si una expresión conocida aparece como frase, gana.
    # Se prueba tanto la frase tal cual como la versión sin conectores (BUGFIX-2026-08-29,
    # ver _strip_stopwords) para que un alias con "de" reconozca también la consulta sin "de".
    for na, na_sw, node in _ALIAS_OVERRIDES:
        if _phrase_in(na, t) or _phrase_in(na_sw, t_sw):
            return node

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
    # Desempate por PADRE COMÚN (BUGFIX taxonomía · término genérico como "software"):
    # cuando el grupo de mejores empates (mismo n-grama, mismo nivel y misma exactitud) son ≥2
    # nodos DISTINTOS que comparten un único padre, se resuelve al PADRE en vez de elegir
    # arbitrariamente la etiqueta más corta por longitud. Antes: "software" empataba las 6
    # industrias de S02 (Software empresarial/financiero/RRHH/comercial/marketing/Desarrollo)
    # y el desempate por longitud devolvía "Software de RRHH"; ahora → S02 "Tecnología".
    # Las coincidencias EXACTAS (c[2]=0) quedan protegidas: forman su propio top_rank y no
    # entran en la sustitución. Si el padre es None (sectores/dimensiones) no se sustituye.
    top = cands[0]
    top_rank = (top[0], top[1], top[2])
    tied = {c[4]["id"]: c[4] for c in cands if (c[0], c[1], c[2]) == top_rank}
    if len(tied) >= _GENERIC_PARENT_MIN_TIES:
        parents = {node.get("parent_id") for node in tied.values()}
        if len(parents) == 1 and next(iter(parents)) is not None:
            parent = _NODE_BY_ID.get(next(iter(parents)))
            if parent:
                return parent
    return top[4]


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


# Point 2 (2026-09-09): columnas admitidas en `sort_by` -> path real en master_companies.
# Fuera de esta whitelist se ignora (nunca se arma el path de Mongo con el string del cliente).
_SORT_FIELDS_MASTER = {
    "name": "identity.legal_name",
    "revenue": "financials.latest.revenue",
    "ebitda": "financials.latest.ebitda",
    "employees": "financials.latest.employees",
    "cif": "cif_normalized",
}
_TAXO_SORT_POOL_CAP = 3000  # tope del pool completo a ordenar cuando se pide sort_by


async def search_by_taxonomy(node_id: Optional[str] = None, dimension_id: Optional[str] = None,
                             primary_only: bool = False, limit: int = 50, offset: int = 0,
                             sort_by: Optional[str] = None, sort_dir: str = "desc") -> Dict:
    """Empresas clasificadas bajo un nodo (sector/industria/categoría) o dimensión (vertical, etc.).
    primary_only=True → solo cuando ese nodo es la actividad PRINCIPAL (role=primary).
    Devuelve `results` enriquecidos con el `summary` de cada empresa (tabla sin N+1) + paginación
    de servidor (`count` total real, `limit`, `offset`)."""
    target = node_id or dimension_id
    if not target:
        return {"count": 0, "results": [], "company_ids": [], "note": "Indica node_id o dimension_id."}
    q: Dict = {"taxonomy_id": target}
    if node_id and primary_only:
        q["role"] = "primary"
    from database import db
    ids: List[str] = []
    total = 0
    rows: List[Dict] = []
    try:
        sort_key = _SORT_FIELDS_MASTER.get((sort_by or "").strip().lower())
        sort_valid = sort_key is not None
        total = await db.company_classifications.count_documents(q)
        base: Dict[str, Dict] = {}
        master_proj = {"_id": 0, "master_id": 1, "cif_normalized": 1,
                       "identity.legal_name": 1, "classification.cnae_section": 1}
        if sort_valid:
            # Point 2: ordenar por columna sobre TODO el conjunto (no solo la pagina).
            # Resolvemos el pool completo de company_ids (tope _TAXO_SORT_POOL_CAP, orden
            # estable por company_id) y paginamos sobre master_companies ya ordenado en BD,
            # con desempate por master_id (Point 1).
            direction = 1 if (sort_dir or "").strip().lower() == "asc" else -1
            pool_ids: List[str] = []
            async for r in db.company_classifications.find(q, {"_id": 0, "company_id": 1}) \
                    .sort("company_id", 1).limit(_TAXO_SORT_POOL_CAP):
                pool_ids.append(r["company_id"])
            if pool_ids:
                async for m in db.master_companies.find(
                        {"master_id": {"$in": pool_ids}}, master_proj) \
                        .sort([(sort_key, direction), ("master_id", 1)]).skip(offset).limit(limit):
                    ids.append(m["master_id"])
                    base[m["master_id"]] = m
        else:
            # Point 1: desempate determinista por company_id (evita duplicados/huecos entre paginas).
            async for r in db.company_classifications.find(q, {"_id": 0, "company_id": 1}) \
                    .sort([("confidence", -1), ("company_id", 1)]).skip(offset).limit(limit):
                ids.append(r["company_id"])
            if ids:
                async for m in db.master_companies.find(
                        {"master_id": {"$in": ids}}, master_proj):
                    base[m["master_id"]] = m
        if ids:
            from services.company_card import build_summaries
            summaries = await build_summaries(ids)
            for cid in ids:  # preserve chosen order (confidence o columna)
                m = base.get(cid) or {}
                rows.append({"master_id": cid, "cif": m.get("cif_normalized"),
                             "name": (m.get("identity") or {}).get("legal_name"),
                             "cnae_section": (m.get("classification") or {}).get("cnae_section"),
                             "summary": summaries.get(cid)})
    except Exception:
        ids, total, rows = [], 0, []
    return {"taxonomy_id": target, "primary_only": bool(node_id and primary_only),
            "count": total, "limit": limit, "offset": offset, "returned": len(rows),
            "results": rows, "company_ids": ids}
