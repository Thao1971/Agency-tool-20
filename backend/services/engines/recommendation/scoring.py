"""Scoring (DR2) — five INDEPENDENT fit dimensions, always visible. The final score
is DERIVED from them with versioned weights (no hardcode in logic). Confidence is
multifactor (DR5). Everything explainable.
"""

from typing import Dict, Optional

SCORE_METHOD = "weighted-blend-v1"

# Versioned weights (config; recalibratable without changing logic). Sum = 1.0
WEIGHTS = {
    "strategic_fit": 0.20, "financial_fit": 0.25, "semantic_fit": 0.25,
    "signal_fit": 0.15, "execution_fit": 0.15,
}


def _clamp(x) -> float:
    try:
        return round(max(0.0, min(1.0, float(x))), 4)
    except Exception:
        return 0.0


def derive_score(fit: Dict[str, Dict]) -> float:
    return round(sum(WEIGHTS[k] * _clamp(fit[k]["value"]) for k in WEIGHTS), 4)


def derive_score_with_weights(fit: Dict[str, Dict], weights: Dict[str, float]) -> float:
    """Same derivation as `derive_score`, but for a different fit-dimension set (E1 —
    Buyer Mandate matching uses sector_fit/size_fit/geo_fit/ownership_fit/opportunity_fit,
    not the 5 generic dimensions `WEIGHTS` hardcodes). Kept separate rather than
    overloading `WEIGHTS` so the original 5-dimension contract stays unchanged."""
    return round(sum(weights.get(k, 0) * _clamp(fit[k]["value"]) for k in weights), 4)


def confidence(coverage: Optional[float], data_quality: Optional[float],
               cross_engine_consistency: float, recency: float,
               profile_completeness: Optional[float]) -> Dict:
    factors = {
        "coverage": _clamp((coverage or 0) / 100 if coverage and coverage > 1 else coverage),
        "data_quality": _clamp((data_quality or 0) / 100 if data_quality and data_quality > 1 else data_quality),
        "cross_engine_consistency": _clamp(cross_engine_consistency),
        "recency": _clamp(recency),
        "profile_completeness": _clamp((profile_completeness or 0) / 100
                                       if profile_completeness and profile_completeness > 1 else profile_completeness),
    }
    value = round(sum(factors.values()) / len(factors), 4)
    return {"value": value, "factors": factors}


def fit_dimension(value, evidence, sources) -> Dict:
    return {"value": _clamp(value), "evidence": evidence, "sources": sources}
