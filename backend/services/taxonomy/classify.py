"""Company Classification Engine v1 (determinista). Combina el ancla CNAE→ARROBA con reglas de
alias/semántica sobre nombre + perfil, produce clasificación MULTICLASE (sector/industria/categoría +
dimensiones) con evidencia y confianza, distingue core_technology vs technology_used, calcula un
Fingerprint y persiste de forma idempotente. IA opcional (fase posterior). Fact-lock: no inventa.
Ver memory/ARROBA_TAXONOMY_ENGINE_DESIGN.md (P0–P5)."""

import re
import unicodedata
from typing import Dict, List, Optional

from services.taxonomy import TAXONOMY_VERSION
from services.taxonomy import registry as REG
from services.taxonomy import bridge as BRIDGE

CLASSIFIER_VERSION = "company-classification-engine-v1"

# ── Config (versionada)
W = {"cnae_section": 0.55, "division_industry": 0.6, "kw_industry": 0.55, "kw_category": 0.45,
     "prop_ind_to_sector": 0.4, "prop_cat_to_ind": 0.4, "dim": 0.6, "sector_label": 0.3}
KEEP, SECONDARY = 0.4, 0.6   # umbrales de rol
_TECH_SECTORS = {"S02"}

# Alias de alta señal por id de nodo/dimensión (además de la etiqueta). Se ampliará con la clasificación.
ALIASES: Dict[str, List[str]] = {
    "IND-S03-adtech": ["adtech", "publicidad programatica", "programmatic", "ad server", "dsp", "ssp",
                       "publicidad contextual"],
    "IND-S03-agencias-creativas": ["agencia creativa", "agencia de publicidad", "agencia publicitaria"],
    "IND-S03-agencias-digitales": ["agencia digital", "marketing digital"],
    "IND-S03-agencias-de-medios": ["agencia de medios", "compra de medios", "media agency"],
    "IND-S03-martech": ["martech", "marketing automation", "customer data platform", "cdp"],
    "IND-S02-desarrollo-de-software": ["desarrollo de software", "software factory", "programacion informatica"],
    "IND-S02-inteligencia-artificial": ["inteligencia artificial", "machine learning", "deep learning"],
    "IND-S02-software-empresarial": ["saas", "software as a service", "plataforma software"],
    "IND-S02-ciberseguridad": ["ciberseguridad", "cybersecurity"],
    "IND-S01-consultoria-empresarial": ["consultoria", "consulting"],
    "IND-S08-fintech": ["fintech"],
    "IND-S05-healthtech": ["healthtech", "salud digital"],
    "DIM-verticals-adtech": ["adtech", "publicidad programatica", "publicidad contextual", "programmatic"],
    "DIM-verticals-martech": ["martech", "marketing automation"],
    "DIM-verticals-saas": ["saas", "software as a service"],
    "DIM-verticals-inteligencia-artificial": ["inteligencia artificial", "ia", "machine learning"],
    "DIM-verticals-fintech": ["fintech"],
    "DIM-business_models-saas": ["saas", "suscripcion software"],
    "DIM-business_models-b2b": ["b2b", "empresas"],
    "DIM-business_models-marketplace": ["marketplace"],
    "DIM-technologies-inteligencia-artificial": ["inteligencia artificial", "machine learning", "ia generativa"],
    "DIM-technologies-cloud": ["cloud", "nube"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip() + " "


# ── Índices (una vez)
def _build_index():
    nodes = REG.build_nodes()
    node = {n["id"]: n for n in nodes}
    kw_nodes = []   # (kw_norm, node_id, level, sector_id, industry_id)
    for n in nodes:
        if n["level"] == "sector":
            continue
        sector_id = n["id"].split("-")[1] if n["level"] in ("industry", "category") else None
        industry_id = n["parent_id"] if n["level"] == "category" else n["id"]
        seen = set()
        for kw in [n["label_es"]] + ALIASES.get(n["id"], []):
            nk = _norm(kw).strip()
            if len(nk) >= 4 and nk not in seen:
                seen.add(nk)
                kw_nodes.append((nk, n["id"], n["level"], sector_id, industry_id))
    dims = REG.build_dimensions()
    kw_dims = []    # (kw_norm, dimension, dim_id, label)
    for d in dims:
        seen = set()
        for kw in [d["label_es"]] + ALIASES.get(d["id"], []):
            nk = _norm(kw).strip()
            if len(nk) >= 3 and nk not in seen:
                seen.add(nk)
                kw_dims.append((nk, d["dimension"], d["id"], d["label_es"]))
    sec_labels = {s["id"]: s["label_es"] for s in nodes if s["level"] == "sector"}
    return kw_nodes, kw_dims, node, sec_labels


_KW_NODES, _KW_DIMS, _NODE, _SEC_LABELS = _build_index()


def _add(scores: Dict, ev: Dict, key: str, w: float, source: str, detail: str):
    scores[key] = scores.get(key, 0.0) + w
    ev.setdefault(key, []).append({"source": source, "detail": detail, "weight": w})


def _rows(axis: str, scores: Dict, ev: Dict, label_of) -> List[Dict]:
    ranked = sorted(((k, min(0.99, round(v, 2))) for k, v in scores.items() if v >= KEEP),
                    key=lambda x: -x[1])
    out = []
    for i, (k, conf) in enumerate(ranked):
        role = "primary" if i == 0 else ("secondary" if conf >= SECONDARY else "adjacent")
        out.append({"axis": axis, "taxonomy_id": k, "label_es": label_of(k), "role": role,
                    "confidence": conf, "evidence": ev.get(k, [])})
    return out


async def classify(request: Dict) -> Dict:
    inputs = request.get("inputs") or {}
    company_id = request.get("company_id") or inputs.get("company_id") or inputs.get("master_id")
    cnaes = inputs.get("cnae") or inputs.get("cnaes") or []
    if isinstance(cnaes, str):
        cnaes = [cnaes]
    name = inputs.get("name") or (inputs.get("identity") or {}).get("name") or ""
    desc = inputs.get("description") or inputs.get("profile_text") or inputs.get("objeto_social") or ""
    hay = _norm(f"{name} {desc}")

    sec, ind, cat, ev = {}, {}, {}, {}
    dim_scores = {d: {} for d in ("verticals", "business_models", "client_types", "technologies",
                                  "value_chain", "capabilities")}
    dim_ev = {}

    # P1a — ancla CNAE
    for code in cnaes:
        s_id, ind_label = BRIDGE.anchor_from_cnae(code)
        if s_id:
            _add(sec, ev, s_id, W["cnae_section"], "cnae", f"CNAE {code}")
            if ind_label:
                iid = REG.industry_id(s_id, ind_label)
                _add(ind, ev, iid, W["division_industry"], "cnae", f"CNAE {code} → {ind_label}")
                _add(sec, ev, s_id, W["prop_ind_to_sector"], "cnae", f"industria {ind_label}")

    # P1b — reglas de alias/semántica (nombre + perfil)
    for kw, nid, level, sector_id, industry_id in _KW_NODES:
        if kw in hay:
            if level == "industry":
                _add(ind, ev, nid, W["kw_industry"], "rules", f"'{kw.strip()}'")
                if sector_id:
                    _add(sec, ev, sector_id, W["prop_ind_to_sector"], "rules", f"'{kw.strip()}'")
            elif level == "category":
                _add(cat, ev, nid, W["kw_category"], "rules", f"'{kw.strip()}'")
                if industry_id:
                    _add(ind, ev, industry_id, W["prop_cat_to_ind"], "rules", f"'{kw.strip()}'")
                if sector_id:
                    _add(sec, ev, sector_id, W["prop_ind_to_sector"] * 0.6, "rules", f"'{kw.strip()}'")
    for sid, label in _SEC_LABELS.items():
        if _norm(label).strip() in hay:
            _add(sec, ev, sid, W["sector_label"], "rules", label)

    # P1c — dimensiones transversales
    for kw, dimension, dim_id, label in _KW_DIMS:
        if kw in hay:
            _add(dim_scores[dimension], dim_ev, dim_id, W["dim"], "rules", f"'{kw.strip()}'")

    # Construcción de filas
    label_node = lambda k: (_NODE.get(k) or {}).get("label_es", k)
    sectors = _rows("sector", sec, ev, label_node)
    industries = _rows("industry", ind, ev, label_node)
    categories = _rows("category", cat, ev, label_node)
    primary_sector = sectors[0]["taxonomy_id"] if sectors else None

    dim_out = {}
    dim_label = {d["id"]: d["label_es"] for d in REG.build_dimensions()}
    for dimension, scores in dim_scores.items():
        rows = _rows(dimension, scores, dim_ev, lambda k: dim_label.get(k, k))
        # P3 — core vs used para tecnologías: la tecnología es NÚCLEO si el negocio es tecnológico
        # (sector Tecnología como principal o secundario fuerte), no por mera mención de uso.
        if dimension == "technologies":
            tech_business = (primary_sector in _TECH_SECTORS) or any(
                s["taxonomy_id"] in _TECH_SECTORS and s["confidence"] >= SECONDARY for s in sectors)
            for r in rows:
                r["core_technology"] = bool(tech_business and r["confidence"] >= SECONDARY)
        dim_out[dimension] = rows

    # P4 — Fingerprint (confianza del top por eje, 0..100)
    def _top(rows):
        return int(round(rows[0]["confidence"] * 100)) if rows else 0
    fingerprint = {"sector": _top(sectors), "industry": _top(industries),
                   "vertical": _top(dim_out["verticals"]), "capabilities": _top(dim_out["capabilities"]),
                   "business_model": _top(dim_out["business_models"]), "client": _top(dim_out["client_types"]),
                   "technology": _top(dim_out["technologies"])}
    overall = round(sum([fingerprint["sector"], fingerprint["industry"]]) / 200, 2)

    result = {"company_id": company_id, "taxonomy_version": TAXONOMY_VERSION,
              "classifier_version": CLASSIFIER_VERSION, "primary_sector": primary_sector,
              "classifications": {"sector": sectors, "industry": industries, "category": categories, **dim_out},
              "fingerprint": fingerprint, "overall_confidence": overall}
    if company_id:
        await _persist(company_id, result)
    return result


# ── Persistencia idempotente
_INDEXED = False


async def ensure_indexes():
    global _INDEXED
    if _INDEXED:
        return
    try:
        from database import db
        await db.company_classifications.create_index("company_id")
        await db.company_fingerprint.create_index("company_id", unique=True)
        _INDEXED = True
    except Exception:
        pass


async def _persist(company_id: str, result: Dict):
    try:
        from database import db
        from models import now_iso
        await ensure_indexes()
        now = now_iso()
        rows = []
        for axis, items in result["classifications"].items():
            for r in items:
                rows.append({"company_id": company_id, "axis": axis, "taxonomy_id": r["taxonomy_id"],
                             "label_es": r["label_es"], "role": r.get("role"),
                             "confidence": r["confidence"], "evidence": r.get("evidence", []),
                             "core_technology": r.get("core_technology"),
                             "source": "engine", "classified_at": now,
                             "taxonomy_version": TAXONOMY_VERSION, "classifier_version": CLASSIFIER_VERSION})
        # idempotente: reemplaza la clasificación de esta versión
        await db.company_classifications.delete_many(
            {"company_id": company_id, "taxonomy_version": TAXONOMY_VERSION})
        if rows:
            await db.company_classifications.insert_many(rows)
        await db.company_fingerprint.update_one({"company_id": company_id},
            {"$set": {"company_id": company_id, "fingerprint": result["fingerprint"],
                      "primary_sector": result["primary_sector"],
                      "overall_confidence": result["overall_confidence"],
                      "taxonomy_version": TAXONOMY_VERSION, "computed_at": now}}, upsert=True)
    except Exception:
        pass


async def get_company_classification(company_id: str) -> Dict:
    try:
        from database import db
        rows = [r async for r in db.company_classifications.find(
            {"company_id": company_id}, {"_id": 0}).sort("confidence", -1)]
        fp = await db.company_fingerprint.find_one({"company_id": company_id}, {"_id": 0})
        return {"company_id": company_id, "classifications": rows, "fingerprint": fp}
    except Exception:
        return {"company_id": company_id, "classifications": [], "fingerprint": None}
