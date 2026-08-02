"""Clasificación por lotes (F3). Recorre el universo real (`master_companies`, el master moderno que usa
data_access) y clasifica cada empresa con el Classification Engine, persistiendo de forma idempotente.
Devuelve estadísticas para la auditoría. Determinista, sin coste IA. Ver ARROBA_TAXONOMY_ENGINE_DESIGN.md.
"""

from typing import Dict, Optional
from services.taxonomy import classify as CLS

DEFAULT_SOURCE = "master_companies"


def _text(v) -> str:
    """Extrae texto de un valor que puede ser str o dict ({text|value|description|summary})."""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("text", "value", "description", "summary", "content"):
            if isinstance(v.get(k), str):
                return v[k]
    return ""


def company_inputs(doc: Dict) -> Dict:
    """Adapta un doc de master_companies → request de clasificación (company_id = master_id).
    Incluye `objeto_social` (objeto social registral, ~22k empresas, español rico) y `web_description`
    (enriquecimiento web) en la descripción para que la capa de keywords trabaje con datos reales."""
    idn = doc.get("identity") or {}
    cls = doc.get("classification") or {}
    name = " ".join(x for x in [idn.get("legal_name"), idn.get("commercial_name")] if isinstance(x, str))
    parts = [cls.get("cnae_description"), idn.get("business_description"),
             doc.get("objeto_social"), doc.get("web_description")]
    desc = " ".join(t for t in (_text(p) for p in parts) if t)
    return {"company_id": doc.get("master_id"),
            "inputs": {"cnae": cls.get("cnae_code") or cls.get("cnae_section"),
                       "name": name, "description": desc}}


async def classify_batch(limit: Optional[int] = None, source: str = DEFAULT_SOURCE,
                         skip_merged: bool = True) -> Dict:
    """Clasifica el universo (o los primeros `limit`). Nunca lanza a nivel de empresa."""
    from database import db
    q = {"merge_status": {"$ne": "merged"}} if skip_merged else {}
    proj = {"_id": 0, "master_id": 1, "identity": 1, "classification": 1,
            "objeto_social": 1, "web_description": 1}
    cur = db[source].find(q, proj)
    if limit:
        cur = cur.limit(limit)
    stats = {"processed": 0, "classified": 0, "unclassified": 0, "low_confidence": 0,
             "by_primary_sector": {}, "errors": 0, "_conf": 0.0}
    async for doc in cur:
        req = company_inputs(doc)
        if not req["company_id"]:
            continue
        stats["processed"] += 1
        try:
            r = await CLS.classify(req)
        except Exception:
            stats["errors"] += 1
            continue
        ps = r.get("primary_sector")
        if ps:
            stats["classified"] += 1
            stats["by_primary_sector"][ps] = stats["by_primary_sector"].get(ps, 0) + 1
        else:
            stats["unclassified"] += 1
        oc = r.get("overall_confidence") or 0
        stats["_conf"] += oc
        if oc < 0.5:
            stats["low_confidence"] += 1
    n = stats["processed"]
    stats["avg_confidence"] = round(stats["_conf"] / n, 3) if n else 0.0
    del stats["_conf"]
    stats["taxonomy_version"] = CLS.TAXONOMY_VERSION
    stats["classifier_version"] = CLS.CLASSIFIER_VERSION
    return stats
