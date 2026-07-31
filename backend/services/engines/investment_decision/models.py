"""Modelos (constructores de objetos estructurados) del Investment Decision Engine.

Se usan dicts JSON-serializables (coherente con el resto del repo). Cada constructor
garantiza la forma del objeto definida en el DESIGN (§2)."""

from typing import Any, Dict, List, Optional

# Recomendaciones a nivel especialista
REC_PROCEED = "proceed"
REC_CONDITIONS = "proceed_with_conditions"
REC_EXPLORE = "explore"
REC_PASS = "pass"
REC_ABSTAIN = "abstain"

# Bandas a nivel consenso
BAND_PROCEED = "PROCEED"
BAND_CONDITIONS = "PROCEED_WITH_CONDITIONS"
BAND_EXPLORE = "EXPLORE"
BAND_PASS = "PASS"
BAND_REJECT = "REJECT"

VETO_NONE = "none"
VETO_BLOCKING = "blocking"
VETO_EXISTENTIAL = "existential"

BUYER_PROFILES = (
    "strategic", "private_equity", "family_office",
    "search_fund", "holding", "corporate_venture",
)


def evidence(source: str, engine: str, data_point: str, value: Any,
             confidence: float = 1.0, engine_version: str = "") -> Dict:
    """Átomo de trazabilidad — ninguna conclusión sin uno de estos."""
    return {"source": source, "engine": engine, "engine_version": engine_version,
            "data_point": data_point, "value": value, "confidence": round(float(confidence), 4)}


def finding(text: str, ev: Optional[List[Dict]] = None) -> Dict:
    """Un strength/weakness/risk/question con su evidencia."""
    return {"text": text, "evidence": ev or []}


def opinion(specialist: str, recommendation: str, score: Optional[float],
            confidence: Dict, *, strengths=None, weaknesses=None, risks=None,
            questions=None, conditions=None, veto: bool = False,
            veto_kind: str = VETO_NONE, evidence_list=None,
            weight_base: float = 0.0, weight_applied: float = 0.0) -> Dict:
    """SpecialistOpinion — SIEMPRE estructurado, nunca texto libre."""
    return {
        "specialist": specialist,
        "recommendation": recommendation,
        "score": (None if score is None else round(float(score), 4)),
        "confidence": confidence,
        "weight_base": round(float(weight_base), 4),
        "weight_applied": round(float(weight_applied), 4),
        "strengths": strengths or [], "weaknesses": weaknesses or [],
        "risks": risks or [], "questions": questions or [],
        "conditions": conditions or [],
        "veto": bool(veto), "veto_kind": veto_kind,
        "evidence": evidence_list or [],
    }


def buyer_profile(ptype: str, mandate: Optional[Dict] = None,
                  capacity_eur: Optional[float] = None) -> Dict:
    pt = (ptype or "strategic").lower()
    if pt not in BUYER_PROFILES:
        pt = "strategic"
    return {"type": pt, "mandate": mandate or {}, "capacity_eur": capacity_eur}
