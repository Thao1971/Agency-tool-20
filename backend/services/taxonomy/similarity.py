"""Peer Universe Resolver + similitud de Fingerprint (F4).

No usa "todas las del sector": selecciona comparables puntuando por Industria + Categoría + Verticales +
Capacidades + Modelo de negocio + Sector + Tamaño + Geografía + similitud de Fingerprint, con `why[]`
explicable. Base para percentiles/múltiplos/benchmarks con sentido (evita comparar una agencia de 8 M€
con Publicis). Ver memory/ARROBA_COMPANY_TAXONOMY_v1.md (§Peer Universe) y el diseño (§6).
"""

import math
from typing import Dict, List, Optional

# Pesos del scoring de peers (config; suman 1.0)
PW = {"industry": 0.28, "category": 0.14, "vertical": 0.14, "capability": 0.10,
      "business_model": 0.08, "sector": 0.07, "size": 0.08, "geo": 0.05, "fingerprint": 0.06}
_FP_AXES = ["sector", "industry", "vertical", "capabilities", "business_model", "client", "technology"]
_POOL_CAP = 800


def fingerprint_cosine(a: Optional[Dict], b: Optional[Dict]) -> float:
    if not a or not b:
        return 0.0
    va = [float(a.get(k, 0) or 0) for k in _FP_AXES]
    vb = [float(b.get(k, 0) or 0) for k in _FP_AXES]
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(x * x for x in vb))
    if na == 0 or nb == 0:
        return 0.0
    return round(sum(x * y for x, y in zip(va, vb)) / (na * nb), 4)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


async def _axis_ids(company_id: str) -> Dict[str, set]:
    from database import db
    out: Dict[str, set] = {}
    async for r in db.company_classifications.find({"company_id": company_id},
                                                   {"_id": 0, "axis": 1, "taxonomy_id": 1, "role": 1}):
        out.setdefault(r["axis"], set()).add(r["taxonomy_id"])
    return out


async def _master_meta(company_id: str) -> Dict:
    """Tamaño (revenue) y provincia desde master_companies (best-effort)."""
    try:
        from database import db
        m = await db.master_companies.find_one(
            {"master_id": company_id},
            {"_id": 0, "financials.latest.revenue": 1, "location.provincia": 1}) or {}
        rev = ((m.get("financials") or {}).get("latest") or {}).get("revenue")
        prov = (m.get("location") or {}).get("provincia")
        return {"revenue": rev, "provincia": prov}
    except Exception:
        return {"revenue": None, "provincia": None}


def _size_prox(a, b) -> float:
    try:
        a, b = float(a), float(b)
        if a <= 0 or b <= 0:
            return 0.0
        r = min(a, b) / max(a, b)          # 1 = idéntico
        return round(r, 3)
    except Exception:
        return 0.0


async def peers(company_id: str, k: int = 10, same_primary_only: bool = False) -> Dict:
    from database import db
    t_axes = await _axis_ids(company_id)
    if not t_axes:
        return {"company_id": company_id, "peers": [], "universe_size": 0,
                "note": "La compañía no está clasificada todavía."}
    t_fp_doc = await db.company_fingerprint.find_one({"company_id": company_id}, {"_id": 0})
    t_fp = (t_fp_doc or {}).get("fingerprint")
    t_primary = (t_fp_doc or {}).get("primary_sector")
    t_meta = await _master_meta(company_id)

    # Pool de candidatos: comparten alguna industria (o el sector primario). Acotado.
    ind_ids = list(t_axes.get("industry", set()))
    cand: set = set()
    if ind_ids:
        async for r in db.company_classifications.find(
                {"axis": "industry", "taxonomy_id": {"$in": ind_ids}},
                {"_id": 0, "company_id": 1}).limit(_POOL_CAP):
            cand.add(r["company_id"])
    if t_primary:
        async for r in db.company_classifications.find(
                {"axis": "sector", "taxonomy_id": t_primary, "role": "primary"},
                {"_id": 0, "company_id": 1}).limit(_POOL_CAP):
            cand.add(r["company_id"])
    cand.discard(company_id)

    scored = []
    for cid in cand:
        c_axes = await _axis_ids(cid)
        if same_primary_only:
            c_fp0 = await db.company_fingerprint.find_one({"company_id": cid}, {"_id": 0, "primary_sector": 1})
            if (c_fp0 or {}).get("primary_sector") != t_primary:
                continue
        why: List[str] = []
        s = 0.0
        for axis, w, dimlabel in [("industry", PW["industry"], "industria"),
                                  ("category", PW["category"], "categoría"),
                                  ("verticals", PW["vertical"], "vertical"),
                                  ("capabilities", PW["capability"], "capacidad"),
                                  ("business_models", PW["business_model"], "modelo")]:
            j = _jaccard(t_axes.get(axis, set()), c_axes.get(axis, set()))
            if j > 0:
                s += w * j
                shared = t_axes.get(axis, set()) & c_axes.get(axis, set())
                if axis in ("industry", "verticals") and shared:
                    why.append(f"{dimlabel} común")
        # mismo sector primario
        if t_primary and t_primary in c_axes.get("sector", set()):
            s += PW["sector"]
        # tamaño y geografía
        c_meta = await _master_meta(cid)
        sp = _size_prox(t_meta.get("revenue"), c_meta.get("revenue"))
        if sp:
            s += PW["size"] * sp
            if sp >= 0.5:
                why.append("tamaño similar")
        if t_meta.get("provincia") and c_meta.get("provincia") == t_meta.get("provincia"):
            s += PW["geo"]
            why.append("misma provincia")
        # similitud de fingerprint
        c_fp = await db.company_fingerprint.find_one({"company_id": cid}, {"_id": 0, "fingerprint": 1})
        cos = fingerprint_cosine(t_fp, (c_fp or {}).get("fingerprint"))
        s += PW["fingerprint"] * cos
        if s > 0:
            scored.append({"company_id": cid, "score": round(min(0.99, s), 4),
                           "why": why[:4] or ["perfil similar"]})
    scored.sort(key=lambda x: -x["score"])
    top = scored[:k]
    # Enrich with legal_name so callers (Copilot narrator, UI) can name the peers, not raw ids.
    ids = [p["company_id"] for p in top]
    names = {}
    async for m in db.master_companies.find({"master_id": {"$in": ids}},
                                            {"_id": 0, "master_id": 1, "identity.legal_name": 1}):
        names[m["master_id"]] = (m.get("identity") or {}).get("legal_name")
    for p in top:
        p["legal_name"] = names.get(p["company_id"])
    return {"company_id": company_id, "primary_sector": t_primary,
            "universe_size": len(cand), "peers": top}
