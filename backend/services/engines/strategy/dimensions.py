"""Strategic dimensions (DT2) + derived score + multifactor confidence (DT5).

Five official dimensions; score is DERIVED and never replaces them. risk_exposure is a
RISK LEVEL (1=high) and contributes negatively to the derived score.
"""
from typing import Dict

DIMENSION_NAMES = ["strategic_attractiveness", "execution_feasibility",
                   "value_creation_potential", "risk_exposure", "timing"]
SCORE_METHOD = "evidence-composition-v1"
# versioned weights (config; recalibratable). risk applied as (1 - risk_exposure).
WEIGHTS = {"strategic_attractiveness": 0.25, "execution_feasibility": 0.20,
           "value_creation_potential": 0.25, "risk_exposure": 0.15, "timing": 0.15}


def clamp(x) -> float:
    try:
        return round(max(0.0, min(1.0, float(x))), 4)
    except Exception:
        return 0.0


def dim(value, evidence) -> Dict:
    return {"value": clamp(value), "evidence": evidence}


def derive_score(dims: Dict[str, Dict]) -> float:
    s = 0.0
    for k, w in WEIGHTS.items():
        v = clamp(dims[k]["value"])
        s += w * ((1 - v) if k == "risk_exposure" else v)
    return round(s, 4)


def confidence(evidence_quality, cross_engine_consistency, coverage,
               recency, hypotheses_count) -> Dict:
    factors = {
        "evidence_quality": clamp((evidence_quality or 0) / 100 if (evidence_quality or 0) > 1 else evidence_quality),
        "cross_engine_consistency": clamp(cross_engine_consistency),
        "coverage": clamp((coverage or 0) / 100 if (coverage or 0) > 1 else coverage),
        "recency": clamp(recency),
        "hypotheses_count": clamp(1.0 / (1 + (hypotheses_count or 0))),
    }
    return {"value": round(sum(factors.values()) / len(factors), 4), "factors": factors}
