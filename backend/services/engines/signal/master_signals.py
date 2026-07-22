"""Signal Engine (P3) — derives company signals from the unified master record.

Boundary First, internal-only evolution. Computes Growth / Profitability / Size /
Activity / Similarity signals + a 0-100 signal_score, persisted in companies_master.
Consumed by Analyze (fills signals[]), Recommend (signal_similarity weight) and
Search (optional internal use_signals boost). Public contracts stay immutable.
"""

import logging
import uuid
from bisect import bisect_left
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from database import db
from models import now_iso
from services.data_layer.accessors import (
    financials_latest, financials_history, sector_of, revenue_of,
)

logger = logging.getLogger(__name__)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _signal(stype: str, title: str, desc: str, severity: str, score: float,
            confidence: float, source: str = "inferred") -> Dict:
    return {
        "signal_id": str(uuid.uuid4()),
        "signal_type": stype,
        "title": title,
        "description": desc,
        "severity": severity,
        "score": round(_clamp01(score), 4),
        "confidence": round(_clamp01(confidence), 4),
        "created_at": now_iso(),
        "lineage": {"source": source},
    }


def _pct_label(v: float) -> str:
    return "alto" if v >= 0.66 else ("medio" if v >= 0.33 else "bajo")


def _growth_signals(history: List[Dict]) -> Tuple[List[Dict], float]:
    if len(history) < 2:
        return [], 0.5
    y0, y1 = history[0], history[1]
    out, comps = [], []
    for field, label in (("revenue", "ingresos"), ("ebitda", "EBITDA"), ("employees", "empleados")):
        cur, prev = y0.get(field), y1.get(field)
        if cur is None or prev in (None, 0):
            continue
        g = (cur - prev) / abs(prev)
        comps.append(_clamp01(g + 0.5))
        sev = "positive" if g > 0.02 else ("negative" if g < -0.02 else "neutral")
        out.append(_signal(
            f"growth.{field}", f"Crecimiento de {label} {g*100:+.1f}%",
            f"{label.capitalize()} {y1.get('year')}→{y0.get('year')}: {prev:,.0f} → {cur:,.0f}",
            sev, _clamp01(g + 0.5), 0.8,
        ))
    return out, (sum(comps) / len(comps) if comps else 0.5)


def _profitability_signals(fin: Optional[Dict]) -> Tuple[List[Dict], float]:
    if not fin:
        return [], 0.4
    out, comps = [], []
    rev, ebitda, emp = fin.get("revenue"), fin.get("ebitda"), fin.get("employees")
    margin = fin.get("ebitda_margin") or ((ebitda / rev) if (ebitda and rev) else None)
    if margin is not None:
        norm = _clamp01(margin / 0.3)
        comps.append(norm)
        sev = "positive" if margin > 0.15 else ("negative" if margin < 0.05 else "neutral")
        out.append(_signal("profitability.ebitda_margin", f"Margen EBITDA {margin*100:.1f}%",
                           "Rentabilidad operativa relativa al sector estándar.", sev, norm, 0.85))
    if rev and emp:
        rpe = rev / emp
        norm = _clamp01(rpe / 300000)
        comps.append(norm)
        out.append(_signal("profitability.revenue_per_employee",
                           f"Ingresos por empleado {rpe:,.0f}€",
                           "Productividad por empleado.", "info", norm, 0.7))
    if ebitda and emp:
        epe = ebitda / emp
        out.append(_signal("profitability.ebitda_per_employee",
                           f"EBITDA por empleado {epe:,.0f}€",
                           "Eficiencia por empleado.", "info", _clamp01(epe / 60000), 0.7))
    return out, (sum(comps) / len(comps) if comps else 0.4)


def _size_signals(doc: Dict, rev_pct: Optional[float]) -> Tuple[List[Dict], float]:
    if rev_pct is None:
        return [], 0.5
    sev = "positive" if rev_pct >= 0.66 else "neutral"
    return [_signal("size.sector_position",
                    f"Posición sectorial {_pct_label(rev_pct)} (P{int(rev_pct*100)})",
                    f"Tamaño relativo por ingresos dentro de su cluster/sector ({sector_of(doc) or 'n/d'}).",
                    sev, rev_pct, 0.75)], rev_pct


def _activity_signals(doc: Dict) -> Tuple[List[Dict], float]:
    sources = doc.get("sources") or {}
    present = sum(1 for s in sources.values() if isinstance(s, dict) and s.get("present")) or len(sources)
    fin_present = bool((doc.get("financials") or {}).get("latest"))
    richness = _clamp01((present / 3) * 0.6 + (0.4 if fin_present else 0.0))
    out = [_signal("activity.data_sources", f"{present} fuente(s) de datos integradas",
                   "Riqueza de datos y trazabilidad del master record.",
                   "info", richness, 0.8, source="normalized")]
    return out, richness


def _similarity_signals(doc: Dict) -> List[Dict]:
    cls = doc.get("classification") or {}
    cid = cls.get("cluster_id")
    tags = cls.get("cluster_tags") or []
    if cid is None:
        return []
    return [_signal("similarity.cluster", f"Segmento semántico #{cid}",
                    "Tags: " + (", ".join(tags) if tags else "n/d"),
                    "info", 0.6, 0.7, source="ai_generated")]


def compute_signals(doc: Dict, rev_pct: Optional[float]) -> Tuple[List[Dict], int]:
    fin = financials_latest(doc)
    history = financials_history(doc)

    g_sig, g_comp = _growth_signals(history)
    p_sig, p_comp = _profitability_signals(fin)
    s_sig, s_comp = _size_signals(doc, rev_pct)
    a_sig, a_comp = _activity_signals(doc)
    sim_sig = _similarity_signals(doc)

    signals = g_sig + p_sig + s_sig + a_sig + sim_sig
    data_comp = float(doc.get("confidence_score") or 0.5)
    signal_score = int(round(
        100 * (0.25 * g_comp + 0.25 * p_comp + 0.20 * s_comp + 0.15 * a_comp + 0.15 * data_comp)
    ))
    return signals, signal_score


async def rebuild_signals() -> Dict:
    """Compute + persist signals[] and signal_score for every master record."""
    docs = await db.companies_master.find({"merge_status": {"$ne": "merged"}}, {"_id": 0}).to_list(100000)

    # Sector/cluster revenue benchmarks for relative-size percentile
    rev_by_cluster = defaultdict(list)
    for d in docs:
        r = revenue_of(d)
        cl = (d.get("classification") or {}).get("cluster_id")
        if r and cl is not None:
            rev_by_cluster[cl].append(r)
    for cl in rev_by_cluster:
        rev_by_cluster[cl].sort()

    total = with_signals = 0
    for d in docs:
        total += 1
        r = revenue_of(d)
        cl = (d.get("classification") or {}).get("cluster_id")
        rev_pct = None
        arr = rev_by_cluster.get(cl)
        if r and arr and len(arr) > 1:
            rev_pct = round(bisect_left(arr, r) / (len(arr) - 1), 4)

        signals, score = compute_signals(d, rev_pct)
        await db.companies_master.update_one(
            {"master_company_id": d["master_company_id"]},
            {"$set": {"signals": signals, "signal_score": score, "signals_updated_at": now_iso()}},
        )
        if signals:
            with_signals += 1

    return {"total": total, "with_signals": with_signals}


def signal_similarity(seed: Dict, cand: Dict) -> float:
    """0..1 affinity from cluster match + signal_score proximity."""
    s_cluster = (seed.get("classification") or {}).get("cluster_id")
    c_cluster = (cand.get("classification") or {}).get("cluster_id")
    cluster_match = 1.0 if (s_cluster is not None and s_cluster == c_cluster) else 0.0
    s_score = seed.get("signal_score")
    c_score = cand.get("signal_score")
    if s_score is None or c_score is None:
        proximity = 0.5
    else:
        proximity = 1 - abs(s_score - c_score) / 100.0
    return round(0.5 * cluster_match + 0.5 * proximity, 4)
