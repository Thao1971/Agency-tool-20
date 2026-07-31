"""Contexto fact-lock para la capa narrativa (Fase 6). Se pasa al redactor SOLO la decisión ya
tomada por el comité (banda/score/confianza + conclusiones estructuradas). El redactor no puede
cambiar cifras ni banda; solo convierte esto en prosa ejecutiva."""

from typing import Dict


def narrative_context(consensus: Dict, profile: Dict) -> Dict:
    def _texts(items, n=6):
        return [f.get("text") for f in (items or [])[:n] if f.get("text")]
    return {
        "decision_fixed": {
            "recommendation_band": consensus.get("recommendation"),
            "investment_score_0_100": consensus.get("investment_score"),
            "confidence_0_1": consensus.get("confidence"),
        },
        "buyer_profile": (profile or {}).get("type"),
        "strengths": _texts(consensus.get("strengths")),
        "weaknesses": _texts(consensus.get("weaknesses")),
        "risks": _texts(consensus.get("risks")),
        "conditions_to_proceed": consensus.get("conditions_to_proceed"),
        "open_questions": _texts(consensus.get("open_questions")),
        "vetoes": consensus.get("reasoning", {}).get("vetoes"),
        "coverage": consensus.get("reasoning", {}).get("coverage"),
        "instruction_extra": ("Escribe un executive_summary (2-3 frases) y una conclusion que sea la "
                              "tesis de inversión, coherentes con la banda y el score FIJOS. No inventes "
                              "cifras. Menciona condiciones y riesgos si los hay."),
    }
