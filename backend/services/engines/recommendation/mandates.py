"""Buyer Mandates (E1 — G1: Buyer Intelligence por mandato).

The gap this closes: `recommendation/engine.py::buyers()` only infers a buyer role
(strategic/financial/roll_up) reactively from companies that happen to be semantically
similar and bigger than ONE target — it has no idea what a real buyer is actually
looking for. This module adds the entity that was missing: a persisted, reusable
`BuyerMandate` (sector, geography, size range, ownership preference, exclusions),
and matches it against the real company universe in both directions:

- `find_targets_for_mandate`: given a mandate, rank real candidates against it.
- `find_mandates_for_target`: given a target (e.g. one Q1 just flagged with
  `opportunity.succession_signal`), which active mandates would want it.

Rules-based and explainable, same contract as the rest of the platform (D-style):
5 independent fit dimensions, versioned weights, no AI. Reuses real data only —
`master_companies` (sector/geo/size/ownership), the Q2 ownership graph
(`master_relationships`, to exclude a buyer's own existing portfolio) and Q1's
persisted Signal opportunity signals (to boost genuinely ripe targets) — no new
data source, exactly like every other quick win this session.
"""

import uuid
from typing import Dict, List, Optional

from database import db
from models import now_iso
from services.engines.recommendation import scoring as S

MANDATE_TYPES = ["strategic", "financial", "roll_up"]
OWNERSHIP_PREFERENCES = ["any", "standalone_only"]
MANDATE_FIT_WEIGHTS = {
    "sector_fit": 0.25, "size_fit": 0.20, "geo_fit": 0.15,
    "ownership_fit": 0.15, "opportunity_fit": 0.25,
}
PORTFOLIO_RELATIONSHIP_TYPES = ["parent_of", "ultimate_parent_of", "investee_of", "shareholder_of"]

_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    await db.buyer_mandates.create_index("mandate_id", unique=True)
    await db.buyer_mandates.create_index("status")
    await db.buyer_mandates.create_index("created_by")
    _INDEXED = True


# ── CRUD ──

async def create_mandate(payload: Dict, created_by: Optional[str]) -> Dict:
    await ensure_indexes()
    mandate_id = "bm_" + uuid.uuid4().hex[:12]
    now = now_iso()
    doc = {**payload, "mandate_id": mandate_id, "status": "active",
           "created_by": created_by, "created_at": now, "updated_at": now}
    await db.buyer_mandates.insert_one(dict(doc))
    return doc


async def get_mandate(mandate_id: str) -> Optional[Dict]:
    return await db.buyer_mandates.find_one({"mandate_id": mandate_id}, {"_id": 0})


async def list_mandates(status: Optional[str] = None, created_by: Optional[str] = None,
                        limit: int = 100) -> List[Dict]:
    q: Dict = {}
    if status:
        q["status"] = status
    if created_by:
        q["created_by"] = created_by
    return await db.buyer_mandates.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)


async def update_mandate(mandate_id: str, patch: Dict) -> Optional[Dict]:
    patch = {k: v for k, v in patch.items() if v is not None}
    if not patch:
        return await get_mandate(mandate_id)
    patch["updated_at"] = now_iso()
    result = await db.buyer_mandates.update_one({"mandate_id": mandate_id}, {"$set": patch})
    if result.matched_count == 0:
        return None
    return await get_mandate(mandate_id)


# ── Exclusion (hard filter, not part of the score) ──

async def _excluded(mandate: Dict, candidate: Dict) -> bool:
    cid = candidate["master_id"]
    if cid in (mandate.get("exclude_master_ids") or []):
        return True
    buyer_id = mandate.get("buyer_master_id")
    if not buyer_id:
        return False
    if cid == buyer_id:
        return True
    # Already connected via a REAL ownership edge (Q2 graph) -> already part of the
    # buyer's portfolio/parent, not a new target.
    edge = await db.master_relationships.find_one({"$or": [
        {"src_master_id": buyer_id, "dst_master_id": cid,
         "relationship_type": {"$in": PORTFOLIO_RELATIONSHIP_TYPES}},
        {"src_master_id": cid, "dst_master_id": buyer_id,
         "relationship_type": {"$in": ["parent_of", "ultimate_parent_of"]}},
    ]})
    if edge:
        return True
    buyer_doc = await db.master_companies.find_one({"master_id": buyer_id}, {"_id": 0, "ownership.group_id": 1})
    buyer_gid = (buyer_doc.get("ownership") or {}).get("group_id") if buyer_doc else None
    cand_gid = (candidate.get("ownership") or {}).get("group_id")
    return bool(buyer_gid and buyer_gid == cand_gid)


# ── Fit dimensions (rules-based, explainable) ──

def _sector_fit(mandate: Dict, candidate: Dict):
    codes = mandate.get("target_cnae_codes") or []
    sections = mandate.get("target_cnae_sections") or []
    if not codes and not sections:
        return 0.5, ["sin_criterio_sector"]
    cls = candidate.get("classification") or {}
    c_code, c_section = cls.get("cnae_code"), cls.get("cnae_section")
    if codes and c_code in codes:
        return 1.0, [f"cnae_code={c_code} coincide"]
    if sections and c_section in sections:
        return 0.7, [f"cnae_section={c_section} coincide (código exacto no)"]
    return 0.0, [f"sin coincidencia (candidato: {c_code}/{c_section})"]


def _size_fit(mandate: Dict, candidate: Dict):
    rmin, rmax = mandate.get("revenue_min"), mandate.get("revenue_max")
    if rmin is None and rmax is None:
        return 0.5, ["sin_criterio_tamaño"]
    rev = ((candidate.get("financials") or {}).get("latest") or {}).get("revenue")
    if rev is None:
        return 0.0, ["facturación del candidato desconocida"]
    lo = rmin if rmin is not None else 0.0
    hi = rmax if rmax is not None else float("inf")
    if lo <= rev <= hi:
        return 1.0, [f"facturación {rev:,.0f} dentro de [{lo:,.0f}, {hi if hi != float('inf') else '∞'}]"]
    dist = (lo - rev) / lo if (rev < lo and lo > 0) else (1.0 if hi == float("inf") else (rev - hi) / hi)
    return max(0.0, 1 - min(1.0, dist)), [f"facturación {rev:,.0f} fuera del rango mandato"]


def _geo_fit(mandate: Dict, candidate: Dict):
    provs = mandate.get("target_provincias") or []
    if not provs:
        return 0.5, ["sin_criterio_geografico"]
    c_prov = (candidate.get("location") or {}).get("provincia")
    if c_prov in provs:
        return 1.0, [f"provincia={c_prov} coincide"]
    return 0.0, [f"provincia={c_prov} fuera del criterio"]


def _ownership_fit(mandate: Dict, candidate: Dict):
    pref = mandate.get("ownership_preference", "any")
    own = candidate.get("ownership") or {}
    standalone = not (own.get("parents") or own.get("group_id"))
    if pref == "standalone_only":
        return (1.0, ["target sin matriz ni grupo (preferencia cumplida)"]) if standalone \
            else (0.0, ["target ya pertenece a un grupo (preferencia no cumplida)"])
    return 0.5, ["sin preferencia de propiedad"]


async def _opportunity_fit(mandate: Dict, candidate: Dict):
    mid = candidate["master_id"]
    sigs = await db.signals.find(
        {"master_id": mid, "category": "opportunity", "status": "active"},
        {"_id": 0, "signal_type": 1, "dimensions": 1},
    ).to_list(20)
    if not sigs:
        return 0.3, ["sin señales de oportunidad activas"]
    impacts = [(s.get("dimensions") or {}).get("impact", 0) for s in sigs]
    base = sum(impacts) / len(impacts)
    types = {s["signal_type"] for s in sigs}
    mtype = mandate.get("mandate_type", "strategic")
    boost = 0.0
    if mtype == "roll_up" and "market.fragmented_sector" in types:
        boost += 0.15
    if "opportunity.succession_signal" in types:
        boost += 0.1
    if mtype == "strategic" and any(t.startswith("opportunity.") for t in types):
        boost += 0.05
    return min(1.0, base + boost), [f"señales activas: {sorted(types)}"]


def _explain(mandate: Dict, candidate: Dict, fit: Dict, score: float) -> str:
    name = (candidate.get("identity") or {}).get("legal_name")
    return (f"{name} encaja en el mandato \"{mandate.get('name')}\" con score {score}: "
            f"sector {fit['sector_fit']['value']}, tamaño {fit['size_fit']['value']}, "
            f"geografía {fit['geo_fit']['value']}, propiedad {fit['ownership_fit']['value']}, "
            f"oportunidad {fit['opportunity_fit']['value']}.")


async def mandate_fit(mandate: Dict, candidate: Dict) -> Dict:
    sf, sf_ev = _sector_fit(mandate, candidate)
    zf, zf_ev = _size_fit(mandate, candidate)
    gf, gf_ev = _geo_fit(mandate, candidate)
    of, of_ev = _ownership_fit(mandate, candidate)
    pf, pf_ev = await _opportunity_fit(mandate, candidate)
    fit = {
        "sector_fit": S.fit_dimension(sf, sf_ev, ["master-v1"]),
        "size_fit": S.fit_dimension(zf, zf_ev, ["master-v1"]),
        "geo_fit": S.fit_dimension(gf, gf_ev, ["master-v1"]),
        "ownership_fit": S.fit_dimension(of, of_ev, ["master-v1", "ownership-graph-v1"]),
        "opportunity_fit": S.fit_dimension(pf, pf_ev, ["signal-intelligence-v1"]),
    }
    score = S.derive_score_with_weights(fit, MANDATE_FIT_WEIGHTS)
    rec = {"master_id": candidate["master_id"],
           "name": (candidate.get("identity") or {}).get("legal_name"),
           "score": score, "fit_dimensions": fit, "score_method": "weighted-blend-v1"}
    rec["explanation"] = _explain(mandate, candidate, fit, score)
    return rec


# ── Matching entrypoints ──

async def find_targets_for_mandate(mandate_id: str, limit: int = 20) -> Optional[Dict]:
    mandate = await get_mandate(mandate_id)
    if not mandate:
        return None
    query: Dict = {"status": "active"}
    if mandate.get("target_cnae_codes"):
        query["classification.cnae_code"] = {"$in": mandate["target_cnae_codes"]}
    elif mandate.get("target_cnae_sections"):
        query["classification.cnae_section"] = {"$in": mandate["target_cnae_sections"]}
    if mandate.get("target_provincias"):
        query["location.provincia"] = {"$in": mandate["target_provincias"]}
    rmin, rmax = mandate.get("revenue_min"), mandate.get("revenue_max")
    if rmin is not None or rmax is not None:
        # Widen the DB pre-filter (0.5x-1.5x) so _size_fit's taper still scores
        # near-miss candidates instead of hard-excluding them before scoring.
        rq: Dict = {}
        if rmin is not None:
            rq["$gte"] = rmin * 0.5
        if rmax is not None:
            rq["$lte"] = rmax * 1.5
        query["financials.latest.revenue"] = rq

    candidates = await db.master_companies.find(query, {"_id": 0}).to_list(limit * 10)
    scored = []
    for c in candidates:
        if await _excluded(mandate, c):
            continue
        scored.append(await mandate_fit(mandate, c))
    scored.sort(key=lambda r: r["score"], reverse=True)
    return {"mandate_id": mandate_id, "mandate_name": mandate.get("name"),
            "candidates_scanned": len(candidates), "count": len(scored[:limit]),
            "targets": scored[:limit]}


async def find_mandates_for_target(master_id: str, limit: int = 10) -> Optional[Dict]:
    candidate = await db.master_companies.find_one({"master_id": master_id}, {"_id": 0})
    if not candidate:
        return None
    mandates = await db.buyer_mandates.find({"status": "active"}, {"_id": 0}).to_list(1000)
    scored = []
    for m in mandates:
        if await _excluded(m, candidate):
            continue
        rec = await mandate_fit(m, candidate)
        rec["mandate_id"] = m["mandate_id"]
        rec["mandate_name"] = m.get("name")
        scored.append(rec)
    scored.sort(key=lambda r: r["score"], reverse=True)
    return {"master_id": master_id, "mandates_scanned": len(mandates),
            "count": len(scored[:limit]), "mandates": scored[:limit]}
