"""Scoring del Investment Decision Engine — config VERSIONADA y separada de la lógica
(patrón services/engines/recommendation/scoring.py). Recalibrable sin tocar el código de
decisión. Todo determinista.

Parámetros validados con Daniel (2026-07-31): ver INVESTMENT_DECISION_ENGINE_CONSTITUTION.md.
"""

from typing import Dict, List, Optional

SCORE_METHOD = "committee-weighted-v1"

# Pesos base del comité (Σ = 1.0). CFO · Valuation · Strategy = voces de mayor peso (0.15).
COMMITTEE_WEIGHTS: Dict[str, float] = {
    "cfo": 0.15, "valuation": 0.15, "strategy": 0.15,
    "investment_director": 0.11, "market": 0.11, "commercial": 0.09,
    "operations": 0.08, "hr": 0.05, "legal": 0.055, "risk": 0.055,
}

# Moduladores por perfil de comprador (deltas sobre la base; se renormaliza a 1.0).
BUYER_PROFILE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "strategic":       {"strategy": +0.04, "commercial": +0.03, "operations": +0.02, "valuation": -0.05, "market": -0.02, "hr": -0.02},
    "private_equity":  {"valuation": +0.05, "cfo": +0.03, "risk": +0.03, "strategy": -0.06, "commercial": -0.03, "hr": -0.02},
    "family_office":   {"cfo": +0.04, "risk": +0.03, "hr": +0.03, "strategy": -0.05, "market": -0.03, "commercial": -0.02},
    "search_fund":     {"operations": +0.05, "hr": +0.04, "cfo": +0.03, "market": -0.05, "strategy": -0.04, "valuation": -0.03},
    "holding":         {"strategy": +0.04, "cfo": +0.03, "commercial": -0.04, "market": -0.03},
    "corporate_venture": {"strategy": +0.05, "market": +0.04, "cfo": -0.04, "valuation": -0.05},
}

# Umbrales de banda (score 0..100) + reglas duras (ver decide_band).
RECOMMENDATION_BANDS = {"proceed": 70, "conditions": 55, "explore": 45}
MIN_CONFIDENCE_FOR_PROCEED = 0.6
CONFIDENCE_FLOOR = 0.4          # < 0.4 ⇒ nunca PROCEED
MIN_COVERAGE = 0.34            # cobertura mínima para no forzar EXPLORE
MAX_DISPERSION_FOR_PROCEED = 0.28


def clamp(x, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return round(max(lo, min(hi, float(x))), 4)
    except (TypeError, ValueError):
        return lo


def apply_buyer_profile(base: Dict[str, float], profile_type: str) -> Dict[str, float]:
    """Aplica los deltas del perfil y renormaliza a Σ=1.0 (nunca pesos negativos)."""
    deltas = BUYER_PROFILE_WEIGHTS.get((profile_type or "strategic").lower(), {})
    w = {k: max(0.0, v + deltas.get(k, 0.0)) for k, v in base.items()}
    total = sum(w.values()) or 1.0
    return {k: round(v / total, 4) for k, v in w.items()}


def committee_score(opinions: List[Dict], weights: Dict[str, float]) -> float:
    """Media ponderada (0..1) de los especialistas que NO se abstienen. Renormaliza los
    pesos sobre los presentes para que la ausencia de una voz no penalice artificialmente."""
    active = [o for o in opinions if o.get("score") is not None and o.get("recommendation") != "abstain"]
    if not active:
        return 0.0
    wsum = sum(weights.get(o["specialist"], 0.0) for o in active) or 1.0
    return round(sum(weights.get(o["specialist"], 0.0) * o["score"] for o in active) / wsum, 4)


def dispersion(opinions: List[Dict]) -> float:
    """Desviación estándar (0..1) de los scores activos → proxy de desacuerdo del comité."""
    import statistics
    scores = [o["score"] for o in opinions if o.get("score") is not None and o.get("recommendation") != "abstain"]
    if len(scores) < 2:
        return 0.0
    return round(min(1.0, statistics.pstdev(scores)), 4)


def confidence(coverage: Optional[float], data_quality: Optional[float],
               cross_engine_consistency: float, recency: float,
               committee_agreement: float) -> Dict:
    """Confianza multifactor (patrón recommendation.scoring.confidence)."""
    factors = {
        "coverage": clamp(coverage),
        "data_quality": clamp(data_quality),
        "cross_engine_consistency": clamp(cross_engine_consistency),
        "recency": clamp(recency),
        "committee_agreement": clamp(committee_agreement),
    }
    return {"value": round(sum(factors.values()) / len(factors), 4), "factors": factors}


def decide_band(score_0_100: float, conf: float, disp: float, vetoes: List[Dict],
                coverage: float) -> str:
    """Traduce score + confianza + dispersión + vetos + cobertura a una banda (Constitución §6)."""
    from services.engines.investment_decision import models as M
    # Reglas duras
    if any(v.get("veto_kind") == M.VETO_EXISTENTIAL for v in vetoes):
        return M.BAND_REJECT
    if coverage < MIN_COVERAGE:
        return M.BAND_EXPLORE
    blocking = any(v.get("veto_kind") == M.VETO_BLOCKING for v in vetoes)

    if score_0_100 >= RECOMMENDATION_BANDS["proceed"] and not blocking \
            and conf >= MIN_CONFIDENCE_FOR_PROCEED and disp <= MAX_DISPERSION_FOR_PROCEED \
            and conf >= CONFIDENCE_FLOOR:
        return M.BAND_PROCEED
    if score_0_100 >= RECOMMENDATION_BANDS["conditions"]:
        return M.BAND_CONDITIONS if (blocking or conf < MIN_CONFIDENCE_FOR_PROCEED
                                     or disp > MAX_DISPERSION_FOR_PROCEED) else M.BAND_CONDITIONS
    if score_0_100 >= RECOMMENDATION_BANDS["explore"]:
        return M.BAND_EXPLORE
    return M.BAND_PASS
