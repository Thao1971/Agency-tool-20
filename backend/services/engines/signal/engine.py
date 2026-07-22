"""Signal Intelligence Engine — orchestrator (signal-intelligence-v1).

Boundary First: consumes ONLY the Master Layer + Financial Intelligence Engine +
Knowledge Graph (ownership). Deterministic, explainable (D8: no UI), thresholds
resolved by config (D1), 4 independent dimensions (D2), canonical actions (D4),
versioned taxonomy (D6), composites (D7), persisted history (D5). No AI in v1.
"""

import hashlib
from typing import Dict, List, Optional

from database import db
from models import now_iso
from services.engines.financial import engine as fin_engine
from services.engines.signal import taxonomy as T
from services.engines.signal import thresholds as TH
from services.engines.signal import actions as A
from services.engines.signal import composites as C
from services.engines.signal import persistence as P
from services.engines.signal import borme_bridge as BB
from services.engines.signal import baselines as BL

ENGINE_VERSION = "signal-intelligence-v1"


def _clamp01(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 4)


def _signal_id(master_id: str, signal_type: str, source_version: str) -> str:
    raw = f"{master_id}|{signal_type}|{source_version}|{ENGINE_VERSION}|{TH.THRESHOLDS_VERSION}"
    return "sig_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _dimensions(meta: Dict, exceedance: float, confidence: float, persistence: float) -> Dict:
    impact = _clamp01(meta["base_impact"] + 0.3 * exceedance)
    return {"impact": impact, "confidence": _clamp01(confidence),
            "urgency": _clamp01(meta["base_urgency"]), "persistence": _clamp01(persistence)}


def _make(master_id, source_version, stype, value, threshold, tsource, baseline,
          exceedance, confidence, persistence, explanation, window="latest"):
    meta = T.SIGNAL_TYPES[stype]
    dims = _dimensions(meta, exceedance, confidence, persistence)
    return {
        "signal_id": _signal_id(master_id, stype, source_version),
        "master_id": master_id, "signal_type": stype, "category": meta["category"],
        "severity": meta["severity"], "polarity": meta["polarity"],
        "dimensions": dims, "confidence": dims["confidence"],
        "detected_at": now_iso(), "is_composite": False,
        "source": {"engine": ",".join(meta["dependencies"]),
                   "fields": [TH.DEFAULT_THRESHOLDS.get(stype, {}).get("metric", stype)],
                   "source_version": source_version},
        "evidence": {"metric": TH.DEFAULT_THRESHOLDS.get(stype, {}).get("metric", stype),
                     "value": value, "window": window},
        "rule": {"id": stype, "expression": f"{stype.split('.')[-1]} {TH.DEFAULT_THRESHOLDS.get(stype, {}).get('operator','?')} threshold",
                 "threshold": threshold, "threshold_source": tsource, "baseline": baseline,
                 "thresholds_version": TH.THRESHOLDS_VERSION, "passed": True},
        "recommended_actions": A.validate(meta["actions"]),
        "explanation": explanation,
        "engine_version": ENGINE_VERSION, "taxonomy_version": T.TAXONOMY_VERSION,
    }


async def _evaluate(master: Dict, fin: Dict, source_version: str) -> List[Dict]:
    mid = master["master_id"]
    out: List[Dict] = []
    kpis = fin.get("kpis") or {}
    fq = (fin.get("financial_quality") or {}).get("score")
    base_conf = _clamp01(0.4 + 0.6 * ((fq or 50) / 100))
    bs = (fin.get("statements") or {}).get("balance_sheet") or {}
    comp = fin.get("comparables") or {}
    evol = fin.get("evolution") or {}

    # Q3 — contextual baselines: resolve, once, which signal types have a real
    # sector x size_band percentile for this company (falls back to thr-v1 default
    # for any type absent here — insufficient sample size or no baseline yet).
    sector_ctx = await BL.context_map(master)

    async def num(stype):
        cfg = TH.DEFAULT_THRESHOLDS.get(stype, {})
        ctx = sector_ctx.get(stype)
        context = {"sector": ctx[0]} if ctx else None
        thr, src, base = await TH.resolve(stype, context=context)
        if ctx and base:
            base = {**base, "sample_size": ctx[1]}
        return cfg, thr, src, base

    def exc(value, thr):
        if not thr:
            return 0.5
        return min(1.0, abs(value - thr) / abs(thr)) if thr else 0.5

    # ── financial / growth / risk / market / operational (numeric, threshold-driven) ──
    em = kpis.get("ebitda_margin")
    if em is not None:
        for stype in ("financial.margin_strong", "financial.margin_weak"):
            _, thr, src, base = await num(stype)
            cond = em > thr if "strong" in stype else em < thr
            if cond:
                out.append(_make(mid, source_version, stype, em, thr, src, base,
                                 exc(em, thr), base_conf, 0.5,
                                 f"Margen EBITDA {em:.1%} {'>' if 'strong' in stype else '<'} umbral {thr:.0%}."))
    cr = kpis.get("current_ratio")
    if cr is not None:
        _, thr, src, base = await num("financial.low_liquidity")
        if cr < thr:
            out.append(_make(mid, source_version, "financial.low_liquidity", cr, thr, src, base,
                             exc(cr, thr), base_conf, 0.6, f"Ratio de liquidez {cr:.2f} < {thr}."))
    de = kpis.get("debt_to_equity")
    if de is not None:
        _, thr, src, base = await num("financial.high_leverage")
        if de > thr:
            out.append(_make(mid, source_version, "financial.high_leverage", de, thr, src, base,
                             exc(de, thr), base_conf, 0.6, f"Deuda/Fondos propios {de:.2f} > {thr}."))
    eq = bs.get("equity")
    if eq is not None and eq < 0:
        _, thr, src, base = await num("financial.negative_equity")
        out.append(_make(mid, source_version, "financial.negative_equity", eq, thr, src, base,
                         1.0, base_conf, 0.7, "Patrimonio neto negativo (riesgo de insolvencia técnica)."))
    ni = kpis.get("net_income")
    if ni is not None and ni < 0:
        _, thr, src, base = await num("financial.net_loss")
        out.append(_make(mid, source_version, "financial.net_loss", ni, thr, src, base,
                         0.6, base_conf, 0.5, "Resultado neto negativo en el último ejercicio."))
    if fq is not None:
        _, thr, src, base = await num("financial.quality_low")
        if fq < thr:
            out.append(_make(mid, source_version, "financial.quality_low", fq, thr, src, base,
                             exc(fq, thr), base_conf, 0.5, f"Calidad financiera {fq} < {thr}."))

    rg = kpis.get("revenue_growth_yoy")
    if rg is not None:
        _, thr, src, base = await num("growth.revenue_surge")
        if rg > thr:
            out.append(_make(mid, source_version, "growth.revenue_surge", rg, thr, src, base,
                             exc(rg, thr), base_conf, 0.5, f"Ingresos {rg:+.1%} interanual (> {thr:.0%}).", "yoy"))
        _, thr2, src2, base2 = await num("risk.revenue_decline")
        if rg < thr2:
            out.append(_make(mid, source_version, "risk.revenue_decline", rg, thr2, src2, base2,
                             exc(rg, thr2), base_conf, 0.6, f"Ingresos {rg:+.1%} interanual (< {thr2:.0%}).", "yoy"))
        _, thra, srca, basea = await num("risk.revenue_anomaly")
        if abs(rg) > thra:
            out.append(_make(mid, source_version, "risk.revenue_anomaly", abs(rg), thra, srca, basea,
                             exc(abs(rg), thra), base_conf * 0.8, 0.4,
                             f"Salto anómalo de ingresos ({rg:+.0%}, > {thra:.0%}).", "yoy"))
    eg = kpis.get("ebitda_growth_yoy")
    if eg is not None:
        _, thr, src, base = await num("growth.ebitda_expansion")
        if eg > thr:
            out.append(_make(mid, source_version, "growth.ebitda_expansion", eg, thr, src, base,
                             exc(eg, thr), base_conf, 0.5, f"EBITDA {eg:+.1%} interanual (> {thr:.0%}).", "yoy"))
    cagr = kpis.get("revenue_cagr")
    if cagr is not None:
        _, thr, src, base = await num("growth.sustained")
        if cagr > thr:
            out.append(_make(mid, source_version, "growth.sustained", cagr, thr, src, base,
                             exc(cagr, thr), base_conf, 0.8, f"CAGR de ingresos {cagr:+.1%} (> {thr:.0%}).", "3y"))

    # sustained_decline (structural, multi-year)
    pts = [p.get("revenue") for p in (evol.get("points") or []) if p.get("revenue") is not None]
    if len(pts) >= 3 and pts[0] < pts[1] < pts[2]:
        out.append(_make(mid, source_version, "risk.sustained_decline", pts[0], None, "structural", None,
                         0.7, base_conf, 0.8, "Ingresos a la baja en >=2 ejercicios consecutivos.", "3y"))

    # balance inconsistency
    ta = bs.get("total_assets")
    if eq is not None and ta is not None and ta > 0 and eq > ta:
        out.append(_make(mid, source_version, "risk.balance_inconsistency", eq, ta, "structural", None,
                         0.5, base_conf, 0.4, "Inconsistencia de balance (PN > Activo total)."))

    # market (peer percentile + fragmentation)
    pct = comp.get("subject_ebitda_margin_percentile")
    if pct is not None:
        _, thr, src, base = await num("market.outperforms_peers")
        if pct > thr:
            out.append(_make(mid, source_version, "market.outperforms_peers", pct, thr, src, base,
                             exc(pct, thr), base_conf, 0.6, f"Margen en percentil {pct:.0%} vs peers (> {thr:.0%})."))
        _, thr2, src2, base2 = await num("market.underperforms_peers")
        if pct < thr2:
            out.append(_make(mid, source_version, "market.underperforms_peers", pct, thr2, src2, base2,
                             exc(pct, thr2), base_conf, 0.5, f"Margen en percentil {pct:.0%} vs peers (< {thr2:.0%})."))
    pcount = comp.get("count")
    if pcount is not None:
        _, thr, src, base = await num("market.fragmented_sector")
        if pcount > thr:
            out.append(_make(mid, source_version, "market.fragmented_sector", pcount, thr, src, base,
                             0.5, base_conf, 0.5, f"Sector fragmentado ({pcount} comparables)."))

    # operational
    rpe = kpis.get("revenue_per_employee")
    if rpe is not None:
        _, thr, src, base = await num("operational.productivity_high")
        if rpe > thr:
            out.append(_make(mid, source_version, "operational.productivity_high", rpe, thr, src, base,
                             exc(rpe, thr), base_conf, 0.5, f"Ingresos/empleado {rpe:,.0f}EUR (> {thr:,.0f})."))
        _, thr2, src2, base2 = await num("operational.productivity_low")
        if rpe < thr2:
            out.append(_make(mid, source_version, "operational.productivity_low", rpe, thr2, src2, base2,
                             exc(rpe, thr2), base_conf, 0.5, f"Ingresos/empleado {rpe:,.0f}EUR (< {thr2:,.0f})."))
    ci = kpis.get("capital_intensity")
    if ci is not None:
        _, thr, src, base = await num("operational.capital_intensive")
        if ci > thr:
            out.append(_make(mid, source_version, "operational.capital_intensive", ci, thr, src, base,
                             exc(ci, thr), base_conf, 0.5, f"Intensidad de capital {ci:.2f} (> {thr})."))

    # ── ownership (structural, from Master + KG) ──
    own = master.get("ownership") or {}
    up = own.get("ultimate_parent") or {}
    parents = own.get("parents") or []
    investees = own.get("investees") or []
    gid = own.get("group_id")
    if up and up.get("country") and str(up["country"]).upper() not in ("ES", "ESP", "ESPAÑA", "SPAIN"):
        out.append(_make(mid, source_version, "ownership.foreign_parent", up.get("country"), None,
                         "structural", None, 0.4, 0.9, 0.7,
                         f"Matriz última en {up.get('country')} (participada extranjera)."))
    if gid:
        gsize = await db.master_companies.count_documents({"ownership.group_id": gid})
        _, thr, src, base = await num("ownership.group_member")
        if gsize >= (thr or 2):
            out.append(_make(mid, source_version, "ownership.group_member", gsize, thr, src, base,
                             0.4, 0.9, 0.8, f"Miembro de grupo societario ({gsize} entidades)."))
    if investees:
        _, thr, src, base = await num("ownership.consolidator")
        if len(investees) >= (thr or 2):
            out.append(_make(mid, source_version, "ownership.consolidator", len(investees), thr, src, base,
                             exc(len(investees), thr), 0.9, 0.6,
                             f"Posee {len(investees)} participadas (posible consolidador/roll-up)."))
    if not parents and not gid:
        out.append(_make(mid, source_version, "ownership.standalone", True, None, "structural", None,
                         0.45, 0.9, 0.7, "Sin matrices ni grupo (target independiente)."))
    return out


def _score(signals: List[Dict]) -> Dict:
    if not signals:
        agg = {"impact": 0.0, "confidence": 0.0, "urgency": 0.0, "persistence": 0.0}
        return {"signal_score": 0, "aggregate_dimensions": agg,
                "method": "derived_from_dimensions", "formula_version": "score-v1"}
    n = len(signals)
    agg = {d: round(sum(s["dimensions"][d] for s in signals) / n, 4)
           for d in ("impact", "confidence", "urgency", "persistence")}
    # derived score: impact & urgency weighted by confidence (documented formula score-v1)
    score = round(100 * (0.45 * agg["impact"] + 0.25 * agg["urgency"]
                         + 0.15 * agg["persistence"] + 0.15 * agg["confidence"]))
    return {"signal_score": int(score), "aggregate_dimensions": agg,
            "method": "derived_from_dimensions", "formula_version": "score-v1"}


async def analyze(identifier: str, windows: Optional[List[str]] = None, persist: bool = True) -> Optional[Dict]:
    """Full signal profile for a company. identifier = master_id or cif_normalized."""
    master = await db.master_companies.find_one(
        {"$or": [{"master_id": identifier}, {"cif_normalized": identifier}]}, {"_id": 0})
    if not master:
        return None
    fin = await fin_engine.analyze(identifier) or {}
    source_version = (master.get("sources") or [{}])[-1].get("source_version", "unknown")

    base = await _evaluate(master, fin, source_version) if fin.get("has_financials") is not False else []
    # ownership runs even without financials
    if not base:
        base = await _evaluate(master, fin, source_version)
    # Q1 — BORME corporate events + Iberinform administrator tenure (real data, no new source).
    base += await BB.evaluate(master, source_version, ENGINE_VERSION)
    composite = C.build(base)
    for c in composite:
        c["signal_id"] = _signal_id(master["master_id"], c["signal_type"], source_version)
        c["detected_at"] = now_iso()
        c["engine_version"] = ENGINE_VERSION
        c["taxonomy_version"] = T.TAXONOMY_VERSION
    signals = base + composite

    if persist:
        await P.persist(master["master_id"], source_version, signals)

    counts: Dict[str, int] = {}
    for s in signals:
        counts[s["category"]] = counts.get(s["category"], 0) + 1

    return {
        "master_id": master["master_id"], "cif_normalized": master["cif_normalized"],
        "identity": {"name": (master.get("identity") or {}).get("legal_name"),
                     "cnae_code": (master.get("classification") or {}).get("cnae_code"),
                     "cnae_section": (master.get("classification") or {}).get("cnae_section"),
                     "provincia": (master.get("location") or {}).get("provincia")},
        "signals": signals, "score": _score(signals), "counts_by_category": counts,
        "dependencies": ["master-v1", "financial-intelligence-v1", "knowledge-graph-v1",
                         "borme", "iberinform-officers"],
        "windows_evaluated": windows or ["latest", "yoy", "3y"],
        "engine_version": ENGINE_VERSION, "taxonomy_version": T.TAXONOMY_VERSION,
        "thresholds_version": TH.THRESHOLDS_VERSION, "actions_version": A.ACTIONS_VERSION,
        "composites_version": C.COMPOSITES_VERSION,
        "generated_at": now_iso(), "confidence": _score(signals)["aggregate_dimensions"]["confidence"],
    }
