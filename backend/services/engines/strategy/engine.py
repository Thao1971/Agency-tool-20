"""Strategy Intelligence Engine — orchestrator (strategy-intelligence-v1).

Deterministic composition of prior intelligence into canonical Strategic Thesis
entities (DT15). Reuses Financial/Signal/Semantic/Recommendation/Memory/Master/KG by
reference (DT7), never recreates. Explainable, traceable, reproducible. No black box.
"""
import hashlib
from typing import Dict, List, Optional

from database import db
from models import now_iso
from services.engines.financial import engine as fin_engine
from services.engines.signal import engine as sig_engine
from services.engines.semantic import engine as sem_engine
from services.engines.recommendation import engine as rec_engine
from services.engines.strategy import dimensions as D
from services.engines.strategy import memory as MEM

ENGINE_VERSION = "strategy-intelligence-v1"
THESIS_TYPES = ["strategic", "consolidation", "acquisition", "divestment",
                "partnership", "capital_raising", "growth", "risk"]
EVIDENCE_VERSION = {"master": "master-v1", "financial": "financial-intelligence-v1",
                    "signal": "signal-intelligence-v1", "semantic": "semantic-intelligence-v1",
                    "recommendation": "recommendation-intelligence-v1",
                    "knowledge_graph": "knowledge-graph-v1"}
CURRENT_SOURCE_VERSION = "20260519"


def _thesis_id(master_id: str, ttype: str) -> str:
    raw = f"{master_id}|{ttype}|{D.SCORE_METHOD}|{'/'.join(EVIDENCE_VERSION.values())}"
    return "ths_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


async def _load_master(identifier: str) -> Optional[Dict]:
    return await db.master_companies.find_one(
        {"$or": [{"master_id": identifier}, {"cif_normalized": identifier}]}, {"_id": 0})


async def _context(identifier: str) -> Dict:
    """Gather REFERENCES + light metrics from producers (reuse, not recompute)."""
    fin = await fin_engine.analyze(identifier)
    try:
        sig = await sig_engine.analyze(identifier, persist=False)
    except Exception:
        sig = None
    try:
        sem = await sem_engine.build_profile(identifier)
    except Exception:
        sem = None
    recs = {}
    for kind, fn in (("comparables", rec_engine.comparables),
                     ("buyers", rec_engine.buyers), ("sellers", rec_engine.sellers)):
        try:
            r = await fn(identifier, limit=5)
            recs[kind] = r.get("recommendations", []) if r else []
        except Exception:
            recs[kind] = []
    return {"financial": fin, "signal": sig, "semantic": sem, "recs": recs}


def _metrics(ctx: Dict) -> Dict:
    fin, sig, sem = ctx.get("financial") or {}, ctx.get("signal") or {}, ctx.get("semantic") or {}
    kpis = fin.get("kpis") or {}
    fq = (fin.get("financial_quality") or {}).get("score")
    counts = sig.get("counts_by_category") or {}
    sig_score = (sig.get("score") or {}).get("signal_score")
    coverage = (sem.get("coverage") or {}).get("score")
    pos_impact = [s["dimensions"]["impact"] for s in sig.get("signals", []) if s.get("polarity") == "positive"]
    neg_impact = [s["dimensions"]["impact"] for s in sig.get("signals", []) if s.get("polarity") == "negative"]
    urgency = [s["dimensions"]["urgency"] for s in sig.get("signals", [])]
    return {
        "ebitda_margin": kpis.get("ebitda_margin"), "revenue_growth": kpis.get("revenue_growth_yoy"),
        "revenue_cagr": kpis.get("revenue_cagr"), "debt_to_equity": kpis.get("debt_to_equity"),
        "current_ratio": kpis.get("current_ratio"), "revenue": kpis.get("revenue"),
        "financial_quality": fq, "signal_score": sig_score, "coverage": coverage,
        "growth_momentum": round(sum(pos_impact) / len(pos_impact), 3) if pos_impact else 0.3,
        "risk_level": round(sum(neg_impact) / len(neg_impact), 3) if neg_impact else 0.2,
        "urgency": round(sum(urgency) / len(urgency), 3) if urgency else 0.3,
        "opportunities": counts.get("opportunity", 0), "has_financials": fin.get("has_financials"),
    }


def _structural(master: Dict) -> Dict:
    own = master.get("ownership") or {}
    return {"standalone": not (own.get("parents") or own.get("group_id")),
            "consolidator": len(own.get("investees") or []) >= 2,
            "group_id": own.get("group_id")}


def _refs(ctx: Dict) -> Dict:
    sig = ctx.get("signal") or {}
    rec_ids = []
    for lst in (ctx.get("recs") or {}).values():
        rec_ids += [r["recommendation_id"] for r in lst]
    return {"recommendation_ids": rec_ids[:15],
            "signal_ids": [s["signal_id"] for s in sig.get("signals", [])][:15]}


# ── thesis-type specific dimension shaping (deterministic) ──
def _dimensions(ttype: str, m: Dict, st: Dict) -> Dict:
    gm, rl, mg = m["growth_momentum"], m["risk_level"], (m["ebitda_margin"] or 0)
    q = (m["financial_quality"] or 50) / 100
    attr = D.clamp(0.4 + 0.4 * gm + 0.2 * min(1, max(0, mg / 0.2)))
    feas = D.clamp(0.3 + 0.5 * q + (0.2 if m["has_financials"] else 0))
    valc = D.clamp(0.3 + 0.4 * gm + (0.3 if st["consolidator"] else 0.1))
    risk = D.clamp(0.2 + 0.6 * rl + (0.2 if (m["debt_to_equity"] or 0) > 3 else 0))
    timing = D.clamp(0.3 + 0.5 * m["urgency"] + 0.2 * min(1, m["opportunities"] / 3))

    if ttype == "consolidation":
        valc = D.clamp(valc + 0.2 if st["consolidator"] else valc)
        attr = D.clamp(attr + 0.1 if st["consolidator"] else attr)
    elif ttype == "capital_raising":
        feas = D.clamp(feas - (0.2 if (m["current_ratio"] or 1) < 1 else 0))
        valc = D.clamp(0.3 + 0.5 * gm)
    elif ttype == "divestment":
        attr = D.clamp(0.6 - 0.4 * gm)
        valc = D.clamp(0.4 + 0.3 * rl)
    elif ttype == "risk":
        risk = D.clamp(max(risk, 0.4 + 0.5 * rl))
    return {
        "strategic_attractiveness": D.dim(attr, ["signal:growth_momentum", "financial:ebitda_margin"]),
        "execution_feasibility": D.dim(feas, ["financial:financial_quality", "master:has_financials"]),
        "value_creation_potential": D.dim(valc, ["signal:growth", "kg:consolidator"]),
        "risk_exposure": D.dim(risk, ["signal:risk_level", "financial:debt_to_equity"]),
        "timing": D.dim(timing, ["signal:urgency", "signal:opportunities"]),
    }


_STATEMENTS = {
    "strategic": "Estrategia general recomendada para {name} dado su perfil de crecimiento, riesgo y posición.",
    "consolidation": "{name} es candidata a liderar/participar en una consolidación sectorial.",
    "acquisition": "Justificación de una adquisición por parte de {name} reutilizando comparables y buyers.",
    "divestment": "Justificación de una desinversión total/parcial de {name}.",
    "partnership": "{name} encaja en una alianza estratégica complementaria.",
    "capital_raising": "{name} debería evaluar una ampliación de capital/financiación para sostener su plan.",
    "growth": "Plan de crecimiento para {name} con escenarios alternativos.",
    "risk": "Estrategia de mitigación de riesgos estratégicos de {name}.",
}


def _constraints(ttype: str, m: Dict, st: Dict) -> List[str]:
    c = []
    if ttype in ("acquisition", "consolidation", "growth", "capital_raising"):
        if (m["current_ratio"] or 1) < 1 or (m["debt_to_equity"] or 0) > 2:
            c.append("requires_financing")
    if ttype in ("acquisition", "consolidation"):
        c += ["requires_regulatory_approval", "requires_tech_integration"]
    if ttype == "partnership":
        c.append("requires_partners")
    if ttype == "growth" and (m["revenue_cagr"] or 0) < 0.05:
        c.append("requires_prior_growth")
    return c or ["none"]


def _hypotheses(ttype: str, m: Dict) -> List[Dict]:
    h = []
    if m["revenue_growth"] is None:
        h.append({"assumption": "Crecimiento futuro en línea con el sector", "basis": ["semantic:sector"], "confidence": 0.4})
    if ttype == "acquisition":
        h.append({"assumption": "Sinergias alcanzables tras integración", "basis": ["recommendation:comparables"], "confidence": 0.5})
    if ttype == "capital_raising":
        h.append({"assumption": "Apetito inversor para el sector", "basis": ["signal:opportunity"], "confidence": 0.45})
    return h


def _time_horizon(ttype: str, m: Dict) -> Dict:
    chosen = "mid"
    if ttype in ("risk", "capital_raising"):
        chosen = "short"
    elif ttype in ("consolidation", "growth"):
        chosen = "long" if (m["revenue_cagr"] or 0) > 0.1 else "mid"
    return {"chosen": chosen,
            "justification": f"Horizonte {chosen} acorde a momentum ({m['growth_momentum']}) y urgencia ({m['urgency']}).",
            "by_horizon": {"short": "Acciones inmediatas de bajo riesgo.",
                           "mid": "Ejecución del núcleo de la tesis.",
                           "long": "Captura plena del valor estratégico."}}


def _recommend_type(m: Dict, st: Dict) -> str:
    if m["risk_level"] > 0.5 or (m["debt_to_equity"] or 0) > 3:
        return "risk"
    if st["consolidator"] and m["growth_momentum"] > 0.4:
        return "consolidation"
    if m["growth_momentum"] > 0.5 and (m["current_ratio"] or 1) < 1.2:
        return "capital_raising"
    if m["growth_momentum"] > 0.4:
        return "growth"
    if (m["ebitda_margin"] or 0) < 0.05:
        return "divestment"
    return "strategic"


async def _build(master: Dict, ttype: str, ctx: Dict, opportunity_id: Optional[str] = None,
                 owner: str = "system", persist: bool = True) -> Dict:
    m, st, refs = _metrics(ctx), _structural(master), _refs(ctx)
    name = (master.get("identity") or {}).get("legal_name")
    insufficient = not m["has_financials"] and (m["coverage"] or 0) < 20

    dims = _dimensions(ttype, m, st)
    score = D.derive_score(dims)
    hyps = _hypotheses(ttype, m)
    consistency = round(1 - abs(m["growth_momentum"] - (1 - m["risk_level"])), 3)
    recency = 1.0 if (master.get("sources") or [{}])[-1].get("source_version") == CURRENT_SOURCE_VERSION else 0.7
    conf = D.confidence(m["financial_quality"], consistency, m["coverage"], recency, len(hyps))

    tid = _thesis_id(master["master_id"], ttype)
    statement = _STATEMENTS[ttype].format(name=name)
    rationale = [
        f"Atractivo estratégico {dims['strategic_attractiveness']['value']} y creación de valor {dims['value_creation_potential']['value']}.",
        f"Viabilidad de ejecución {dims['execution_feasibility']['value']} (calidad financiera {m['financial_quality']}).",
        f"Exposición a riesgo {dims['risk_exposure']['value']}; timing {dims['timing']['value']}.",
        f"Estructura: {'standalone' if st['standalone'] else 'en grupo'}, {'consolidador' if st['consolidator'] else 'no consolidador'}.",
    ]
    evidence_tree = {
        "thesis": tid, "hypotheses": [h["assumption"] for h in hyps],
        "recommendations": refs["recommendation_ids"], "signals": refs["signal_ids"],
        "evidence": [f"financial:{EVIDENCE_VERSION['financial']}", f"semantic:{EVIDENCE_VERSION['semantic']}",
                     f"structural:{EVIDENCE_VERSION['knowledge_graph']}"],
        "source_data": [f"master_id:{master['master_id']}",
                        f"source_version:{(master.get('sources') or [{}])[-1].get('source_version')}"],
    }
    graph_edges = [{"from": tid, "to": master["master_id"], "relation": "targets"}]
    for rid in refs["recommendation_ids"][:5]:
        graph_edges.append({"from": tid, "to": rid, "relation": "derived_from"})

    thesis = {
        "thesis_id": tid, "thesis_type": ttype,
        "status": "insufficient_evidence" if insufficient else "available",
        "company_master_id": master["master_id"], "opportunity_id": opportunity_id,
        "subject": {"master_id": master["master_id"], "name": name},
        "statement": statement, "rationale": rationale, "narrative_method": "rules",
        "hypotheses": hyps, "time_horizon": _time_horizon(ttype, m),
        "strategic_dimensions": dims, "score": score,
        "constraints": _constraints(ttype, m, st),
        "recommendation_ids": refs["recommendation_ids"], "signal_ids": refs["signal_ids"],
        "semantic_profile_version": "semantic-profile-v1",
        "financial_snapshot_version": (master.get("sources") or [{}])[-1].get("source_version"),
        "evidence_tree": evidence_tree, "graph_edges": graph_edges,
        "recommended_actions": _actions(ttype),
        "confidence": conf, "owner": owner, "converts_to": None,
        "representation": {"statement": statement, "rationale": rationale, "narrative_method": "rules"},
        "strategy_version": ENGINE_VERSION, "strategy_method": D.SCORE_METHOD,
        "engines_used": list(EVIDENCE_VERSION.keys()),
        "recommendation_version": EVIDENCE_VERSION["recommendation"],
        "evidence_version": EVIDENCE_VERSION, "generated_at": now_iso(),
    }
    if insufficient:
        thesis["insufficient"] = {
            "missing_evidence": ["financial statements", "semantic coverage"],
            "needed_hypotheses": ["sector growth proxy"],
            "additional_info_required": ["latest accounts", "business description"]}
    if persist:
        saved = await MEM.save(thesis)
        thesis["lifecycle"] = saved.get("lifecycle")
        thesis["created_at"] = saved.get("created_at")
        thesis["updated_at"] = saved.get("updated_at")
    return thesis


def _actions(ttype: str) -> List[str]:
    base = {"acquisition": ["analyze", "value", "request_due_diligence", "contact"],
            "divestment": ["analyze", "value", "consult_advisor"],
            "capital_raising": ["raise_capital", "value", "consult_advisor"],
            "consolidation": ["analyze", "compare", "contact"],
            "partnership": ["analyze", "contact"], "risk": ["investigate", "monitor"],
            "growth": ["analyze", "add_to_watchlist"], "strategic": ["analyze", "compare"]}
    return base.get(ttype, ["analyze"])


# ── public capabilities ──
async def thesis(identifier: str, thesis_type: Optional[str] = None,
                 opportunity_id: Optional[str] = None, owner: str = "system") -> Optional[Dict]:
    master = await _load_master(identifier)
    if not master:
        return None
    ctx = await _context(identifier)
    m, st = _metrics(ctx), _structural(master)
    chosen = thesis_type if thesis_type in THESIS_TYPES else _recommend_type(m, st)
    primary = await _build(master, chosen, ctx, opportunity_id, owner)
    # DT11 — always at least one alternative + why preferred
    alt_type = "growth" if chosen != "growth" else "consolidation"
    alt = await _build(master, alt_type, ctx, opportunity_id, owner, persist=False)
    primary["alternatives"] = [{"thesis_type": alt["thesis_type"], "statement": alt["statement"],
                                "score": alt["score"],
                                "why_not_preferred": f"Score {alt['score']} < {primary['score']} en las dimensiones estratégicas."}]
    primary["preferred_rationale"] = (f"La tesis '{chosen}' es preferible por mayor score derivado "
                                      f"({primary['score']}) y mejor balance riesgo/creación de valor.")
    return primary


async def by_type(identifier: str, thesis_type: str, **kw) -> Optional[Dict]:
    master = await _load_master(identifier)
    if not master:
        return None
    return await _build(master, thesis_type, await _context(identifier), **kw)


async def scenarios(identifier: str, scenario_types: Optional[List[str]] = None) -> Optional[Dict]:
    master = await _load_master(identifier)
    if not master:
        return None
    ctx = await _context(identifier)
    m = _metrics(ctx)
    types = scenario_types or ["conservative", "base", "aggressive"]
    factor = {"conservative": 0.7, "base": 1.0, "aggressive": 1.3}
    scens = []
    for stype in types:
        f = factor.get(stype, 1.0)
        gm = D.clamp(m["growth_momentum"] * f)
        score = D.clamp(0.3 + 0.5 * gm)
        scens.append({
            "scenario": stype, "narrative_method": "rules",
            "narrative": f"Escenario {stype}: crecimiento ajustado x{f} (momentum {gm}).",
            "assumptions": [f"growth_factor={f}"],
            "implied_strategy": "growth" if gm > 0.4 else "strategic",
            "time_horizon": _time_horizon("growth", m),
            "strategic_dimensions": {"strategic_attractiveness": D.dim(0.4 + 0.4 * gm, ["signal:growth"]),
                                     "value_creation_potential": D.dim(score, ["scenario"])},
            "score": score, "constraints": _constraints("growth", m, _structural(master)),
            "confidence": D.confidence(m["financial_quality"], 0.6, m["coverage"], 0.9, 1)})
    scens.sort(key=lambda s: s["score"], reverse=True)
    best = scens[0]
    runner = scens[1] if len(scens) > 1 else scens[0]
    return {"subject": {"master_id": master["master_id"], "name": (master.get("identity") or {}).get("legal_name")},
            "scenario_types_requested": types, "scenarios": scens,
            "decision_support": {"preferred": best["scenario"],
                                 "ranking": [s["scenario"] for s in scens],
                                 "comparison": {
                                     "advantages": [f"{best['scenario']} maximiza creación de valor ({best['score']})."],
                                     "disadvantages": [f"{best['scenario']} exige mayores supuestos de crecimiento."],
                                     "risks": [f"Si no se cumplen, converge a {runner['scenario']}."],
                                     "hypotheses": ["Crecimiento sostenible", "Acceso a financiación"],
                                     "success_conditions": ["Ejecución disciplinada", "Capital disponible"]}},
            "strategy_version": ENGINE_VERSION, "generated_at": now_iso()}


async def decision(identifier: str, type_a: str, type_b: str) -> Optional[Dict]:
    master = await _load_master(identifier)
    if not master:
        return None
    ctx = await _context(identifier)
    a = await _build(master, type_a, ctx, persist=False)
    b = await _build(master, type_b, ctx, persist=False)
    winner, loser = (a, b) if a["score"] >= b["score"] else (b, a)
    return {"subject": {"master_id": master["master_id"]},
            "preferred": winner["thesis_type"], "alternative": loser["thesis_type"],
            "comparison": {
                "advantages": [f"{winner['thesis_type']} score {winner['score']} > {loser['thesis_type']} {loser['score']}."],
                "disadvantages": [f"{winner['thesis_type']} constraints: {winner['constraints']}."],
                "risks": [f"Exposición a riesgo {winner['strategic_dimensions']['risk_exposure']['value']}."],
                "hypotheses": [h["assumption"] for h in winner["hypotheses"]],
                "success_conditions": ["Cumplimiento de hipótesis", "Disponibilidad de recursos"]},
            "theses": {type_a: {"score": a["score"], "dimensions": a["strategic_dimensions"]},
                       type_b: {"score": b["score"], "dimensions": b["strategic_dimensions"]}},
            "strategy_version": ENGINE_VERSION, "generated_at": now_iso()}
