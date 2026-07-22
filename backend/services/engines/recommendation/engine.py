"""Recommendation Intelligence Engine — orchestrator (recommendation-intelligence-v1).

Reuses Financial + Signal + Semantic + Master + KG to produce explainable
recommendations (5 fit dimensions, roles, composites, graph edges, memory/feedback).
Never recreates intelligence; combines it. Boundary First.
"""

import hashlib
import math
import statistics
from typing import Dict, List, Optional

from database import db
from models import now_iso
from services.engines.financial import engine as fin_engine
from services.engines.signal import engine as sig_engine
from services.engines.semantic import engine as sem_engine
from services.engines.recommendation import scoring as S
from services.engines.recommendation import memory as MEM

ENGINE_VERSION = "recommendation-intelligence-v1"
EVIDENCE_VERSION = {"master": "master-v1", "financial": "financial-intelligence-v1",
                    "signal": "signal-intelligence-v1", "semantic": "semantic-intelligence-v1",
                    "knowledge_graph": "knowledge-graph-v1"}
CURRENT_SOURCE_VERSION = "20260519"
ACTIONS_BY_ROLE = {
    "strategic_buyer": ["analyze", "compare", "contact"],
    "financial_buyer": ["analyze", "value", "contact"],
    "roll_up_candidate": ["analyze", "compare", "add_to_watchlist"],
    "acquisition_target": ["analyze", "value", "request_due_diligence", "contact"],
    "divestment_candidate": ["analyze", "value", "consult_advisor"],
    "merger_candidate": ["analyze", "compare", "consult_advisor"],
    "partnership_candidate": ["analyze", "contact"],
    None: ["analyze", "compare"],
}


def _rec_id(target: str, candidate: str, rtype: str) -> str:
    raw = f"{target}|{candidate}|{rtype}|{S.SCORE_METHOD}|{'/'.join(EVIDENCE_VERSION.values())}"
    return "rec_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


async def _load_master(identifier: str) -> Optional[Dict]:
    return await db.master_companies.find_one(
        {"$or": [{"master_id": identifier}, {"cif_normalized": identifier}]}, {"_id": 0})


def _fin_latest(doc: Dict) -> Dict:
    return ((doc.get("financials") or {}).get("latest") or {})


def _size_prox(a, b) -> Optional[float]:
    if not a or not b or a <= 0 or b <= 0:
        return None
    return max(0.0, 1 - min(1.0, abs(math.log(a / b)) / math.log(10)))


def _margin_prox(a, b) -> Optional[float]:
    if a is None or b is None:
        return None
    return max(0.0, 1 - min(1.0, abs(a - b) / 0.3))


async def _candidate_signal_fit(master_id: str) -> float:
    vals = []
    async for s in db.signals.find({"master_id": master_id,
                                    "polarity": "positive"}, {"_id": 0, "dimensions": 1}).limit(20):
        vals.append((s.get("dimensions") or {}).get("impact", 0))
    return round(sum(vals) / len(vals), 4) if vals else 0.5


def _is_consolidator(doc: Dict) -> bool:
    return len((doc.get("ownership") or {}).get("investees") or []) >= 2


def _is_standalone(doc: Dict) -> bool:
    own = doc.get("ownership") or {}
    return not (own.get("parents") or own.get("group_id"))


async def _build_rec(target: Dict, cand: Dict, rtype: str, semantic_score: float,
                     role: Optional[str], target_ctx: Dict) -> Dict:
    tf, cf = _fin_latest(target), _fin_latest(cand)
    t_sec = (target.get("classification") or {}).get("cnae_section")
    c_sec = (cand.get("classification") or {}).get("cnae_section")
    same_prov = (target.get("location") or {}).get("provincia") == (cand.get("location") or {}).get("provincia")
    same_group = ((target.get("ownership") or {}).get("group_id")
                  and (target.get("ownership") or {}).get("group_id") == (cand.get("ownership") or {}).get("group_id"))

    # ── financial_fit ──
    sp = _size_prox(tf.get("revenue"), cf.get("revenue"))
    mp = _margin_prox(tf.get("ebitda_margin"), cf.get("ebitda_margin"))
    fin_vals = [v for v in (sp, mp) if v is not None]
    fin_val = sum(fin_vals) / len(fin_vals) if fin_vals else 0.3
    fin_dim = S.fit_dimension(fin_val,
        [f"size_proximity={sp}" if sp is not None else "size:n/a",
         f"margin_proximity={mp}" if mp is not None else "margin:n/a"], ["master-v1", "financial-intelligence-v1"])

    # ── semantic_fit ──
    sem_dim = S.fit_dimension(semantic_score, [f"embedding_cosine={semantic_score}",
                              f"same_section={t_sec == c_sec}"], ["semantic-intelligence-v1"])

    # ── signal_fit (candidate momentum) ──
    sig_val = await _candidate_signal_fit(cand["master_id"])
    sig_dim = S.fit_dimension(sig_val, [f"candidate_positive_signal_impact={sig_val}"], ["signal-intelligence-v1"])

    # ── strategic_fit ──
    strat = 0.4 if (t_sec and t_sec == c_sec) else 0.1
    if _is_consolidator(cand):
        strat += 0.3
    if not same_group:
        strat += 0.2
    strat_dim = S.fit_dimension(min(1.0, strat),
        [f"same_sector={t_sec == c_sec}", f"candidate_consolidator={_is_consolidator(cand)}",
         f"same_group={bool(same_group)}"], ["knowledge-graph-v1", "master-v1"])

    # ── execution_fit ──
    exe = 0.0 + (0.4 if same_prov else 0.15) + (0.3 if cf.get("revenue") else 0.0) + \
          (0.3 if (cand.get("identity") or {}).get("legal_name") else 0.0)
    exe_dim = S.fit_dimension(min(1.0, exe),
        [f"same_province={same_prov}", f"has_financials={bool(cf.get('revenue'))}"], ["master-v1"])

    fit = {"strategic_fit": strat_dim, "financial_fit": fin_dim, "semantic_fit": sem_dim,
           "signal_fit": sig_dim, "execution_fit": exe_dim}
    score = S.derive_score(fit)

    vals = [d["value"] for d in fit.values()]
    consistency = round(1 - min(1.0, statistics.pstdev(vals) / 0.5), 4) if len(vals) > 1 else 0.5
    recency = 1.0 if (cand.get("sources") or [{}])[-1].get("source_version") == CURRENT_SOURCE_VERSION else 0.7
    conf = S.confidence(coverage=target_ctx.get("semantic_coverage"),
                        data_quality=target_ctx.get("financial_quality"),
                        cross_engine_consistency=consistency, recency=recency,
                        profile_completeness=target_ctx.get("semantic_coverage"))

    rid = _rec_id(target["master_id"], cand["master_id"], rtype)
    expl = (f"{(cand.get('identity') or {}).get('legal_name')} es {rtype} "
            f"(rol: {role or 'n/a'}) para {(target.get('identity') or {}).get('legal_name')}: "
            f"semejanza semántica {semantic_score}, ajuste financiero {round(fin_val,2)}, "
            f"sector { 'igual' if t_sec==c_sec else 'distinto'}, "
            f"{'consolidador' if _is_consolidator(cand) else 'no consolidador'}.")
    return {
        "recommendation_id": rid,
        "target": {"master_id": target["master_id"], "name": (target.get("identity") or {}).get("legal_name")},
        "candidate": {"entity_type": "company", "master_id": cand["master_id"],
                      "name": (cand.get("identity") or {}).get("legal_name")},
        "recommendation_type": rtype, "recommendation_role": role,
        "score": score, "fit_dimensions": fit, "score_method": "derived_from_fit_dimensions",
        "composed_of": [],
        "graph_edges": [{"from": target["master_id"], "to": cand["master_id"],
                         "relation": rtype, "rec_id": rid}],
        "evidence": {
            "engines_used": ["semantic-intelligence-v1", "financial-intelligence-v1",
                             "signal-intelligence-v1", "master-v1", "knowledge-graph-v1"],
            "semantic_profile_used": {"similarity": semantic_score, "same_section": t_sec == c_sec},
            "financial_metrics_used": {"target_revenue": tf.get("revenue"),
                                       "candidate_revenue": cf.get("revenue"),
                                       "target_ebitda_margin": tf.get("ebitda_margin"),
                                       "candidate_ebitda_margin": cf.get("ebitda_margin")},
            "signals_relevant": target_ctx.get("signals_brief", []),
            "structural": {"same_group": bool(same_group), "is_consolidator": _is_consolidator(cand),
                           "candidate_standalone": _is_standalone(cand)},
        },
        "confidence": conf, "explanation": expl,
        "recommended_actions": ACTIONS_BY_ROLE.get(role, ACTIONS_BY_ROLE[None]),
        "recommendation_version": ENGINE_VERSION, "recommendation_method": S.SCORE_METHOD,
        "engines_used": list(EVIDENCE_VERSION.keys()), "evidence_version": EVIDENCE_VERSION,
        "generated_at": now_iso(),
    }


async def _target_context(identifier: str) -> Dict:
    ctx: Dict = {}
    fin = await fin_engine.analyze(identifier)
    if fin and fin.get("has_financials"):
        ctx["financial_quality"] = (fin.get("financial_quality") or {}).get("score")
    try:
        sig = await sig_engine.analyze(identifier, persist=False)
        ctx["signals_brief"] = [{"signal_id": s["signal_id"], "signal_type": s["signal_type"],
                                 "dimensions": s["dimensions"]} for s in (sig or {}).get("signals", [])[:5]]
    except Exception:
        ctx["signals_brief"] = []
    try:
        prof = await sem_engine.build_profile(identifier)
        ctx["semantic_coverage"] = (prof or {}).get("coverage", {}).get("score")
    except Exception:
        ctx["semantic_coverage"] = None
    return ctx


async def _similar_candidates(identifier: str, limit: int, same_section: bool) -> List[Dict]:
    sim = await sem_engine.similar(identifier, limit=limit, same_section=same_section)
    if not sim or not sim.get("similar"):
        return []
    ids = [r["master_id"] for r in sim["similar"]]
    score_by = {r["master_id"]: r["score"] for r in sim["similar"]}
    out = []
    async for d in db.master_companies.find({"master_id": {"$in": ids}}, {"_id": 0}):
        d["_semantic_score"] = score_by.get(d["master_id"], 0.0)
        out.append(d)
    out.sort(key=lambda d: d["_semantic_score"], reverse=True)
    return out


async def comparables(identifier: str, limit: int = 10) -> Optional[Dict]:
    target = await _load_master(identifier)
    if not target:
        return None
    ctx = await _target_context(identifier)
    cands = await _similar_candidates(identifier, limit, same_section=True)
    recs = [await _build_rec(target, c, "comparable", c["_semantic_score"], None, ctx) for c in cands]
    recs.sort(key=lambda r: r["score"], reverse=True)
    return _wrap(target, "comparable", recs)


async def buyers(identifier: str, limit: int = 10) -> Optional[Dict]:
    target = await _load_master(identifier)
    if not target:
        return None
    ctx = await _target_context(identifier)
    t_rev = _fin_latest(target).get("revenue") or 0
    cands = await _similar_candidates(identifier, limit * 2, same_section=False)
    recs = []
    for c in cands:
        c_rev = _fin_latest(c).get("revenue") or 0
        if _is_consolidator(c):
            role = "roll_up_candidate"
        elif c_rev >= t_rev * 1.2:
            role = "strategic_buyer" if (c.get("classification") or {}).get("cnae_section") == \
                   (target.get("classification") or {}).get("cnae_section") else "financial_buyer"
        else:
            continue
        recs.append(await _build_rec(target, c, "buyer", c["_semantic_score"], role, ctx))
    recs.sort(key=lambda r: r["score"], reverse=True)
    return _wrap(target, "buyer", recs[:limit])


async def sellers(identifier: str, limit: int = 10) -> Optional[Dict]:
    target = await _load_master(identifier)
    if not target:
        return None
    ctx = await _target_context(identifier)
    t_rev = _fin_latest(target).get("revenue") or 0
    cands = await _similar_candidates(identifier, limit * 2, same_section=False)
    recs = []
    for c in cands:
        c_rev = _fin_latest(c).get("revenue") or 0
        if _is_standalone(c) and (t_rev == 0 or c_rev <= t_rev * 1.0):
            role = "acquisition_target"
        elif not _is_standalone(c):
            role = "divestment_candidate"
        else:
            role = "merger_candidate"
        recs.append(await _build_rec(target, c, "seller", c["_semantic_score"], role, ctx))
    recs.sort(key=lambda r: r["score"], reverse=True)
    return _wrap(target, "seller", recs[:limit])


async def opportunities(identifier: str, limit: int = 10) -> Optional[Dict]:
    """Reuses Signal opportunity signals + fit (does not recompute signals)."""
    target = await _load_master(identifier)
    if not target:
        return None
    ctx = await _target_context(identifier)
    cands = await _similar_candidates(identifier, limit, same_section=True)
    recs = []
    for c in cands:
        # role from candidate structure
        role = "acquisition_target" if _is_standalone(c) else "merger_candidate"
        rec = await _build_rec(target, c, "opportunity", c["_semantic_score"], role, ctx)
        recs.append(rec)
    recs.sort(key=lambda r: (r["fit_dimensions"]["signal_fit"]["value"], r["score"]), reverse=True)
    return _wrap(target, "opportunity", recs[:limit])


async def matching(a: str, b: str) -> Optional[Dict]:
    ma, mb = await _load_master(a), await _load_master(b)
    if not ma or not mb:
        return None
    ctx = await _target_context(a)
    emb_a = await sem_engine.get_embedding(a)
    emb_b = await sem_engine.get_embedding(b)
    from services.engines.semantic import embeddings as E
    va = (emb_a.get("embedding") or {}).get("vector") if emb_a else None
    vb = (emb_b.get("embedding") or {}).get("vector") if emb_b else None
    sem_score = E.cosine(va, vb) if (va and vb) else 0.0
    mb["_semantic_score"] = sem_score
    rec = await _build_rec(ma, mb, "match", sem_score, "merger_candidate", ctx)
    return {"a": {"master_id": ma["master_id"], "name": (ma.get("identity") or {}).get("legal_name")},
            "b": {"master_id": mb["master_id"], "name": (mb.get("identity") or {}).get("legal_name")},
            "recommendation_type": "match", "match": rec,
            "recommendation_version": ENGINE_VERSION, "generated_at": now_iso()}


def unavailable(rtype: str) -> Dict:
    return {"recommendation_type": rtype, "status": "unavailable",
            "reason": "source_not_available", "recommendations": [],
            "recommendation_version": ENGINE_VERSION, "generated_at": now_iso()}


def _wrap(target: Dict, rtype: str, recs: List[Dict]) -> Dict:
    return {"target": {"master_id": target["master_id"],
                       "name": (target.get("identity") or {}).get("legal_name")},
            "recommendation_type": rtype, "status": "available", "count": len(recs),
            "recommendations": recs, "method": S.SCORE_METHOD,
            "recommendation_version": ENGINE_VERSION, "evidence_version": EVIDENCE_VERSION,
            "generated_at": now_iso()}
