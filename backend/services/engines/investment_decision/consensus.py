"""Consensus Engine — combina las opiniones del comité en una recomendación explicable.
Determinista. La narrativa (executive_summary/thesis) es una plantilla reglada en Fase 1;
la IA fact-lock se añade en Fase 6 sin alterar números ni banda."""

from typing import Dict, List
from services.engines.investment_decision import models as M


def _collect(opinions: List[Dict], key: str) -> List[Dict]:
    out = []
    for o in opinions:
        for f in o.get(key) or []:
            out.append({**f, "by": o["specialist"]})
    return out


def build_consensus(opinions: List[Dict], weights: Dict[str, float], score_0_100: int,
                    conf: Dict, band: str, disp: float, vetoes: List[Dict],
                    ev_meta: Dict, profile: Dict) -> Dict:
    active = [o for o in opinions if o.get("recommendation") != M.REC_ABSTAIN]
    strengths = _collect(active, "strengths")
    weaknesses = _collect(active, "weaknesses")
    risks = _collect(active, "risks")
    questions = _collect(opinions, "questions")
    conditions = sorted({c for o in active for c in (o.get("conditions") or [])})

    val_op = next((o for o in opinions if o["specialist"] == "valuation"
                   and o["recommendation"] != M.REC_ABSTAIN), None)

    verdict_txt = {
        M.BAND_PROCEED: "Avanzar hacia due diligence confirmatoria.",
        M.BAND_CONDITIONS: "Avanzar sujeto a condiciones (ver lista).",
        M.BAND_EXPLORE: "Explorar / ampliar due diligence antes de decidir.",
        M.BAND_PASS: "No avanzar con la tesis actual.",
        M.BAND_REJECT: "Rechazar: veto por riesgo existencial.",
    }.get(band, "")

    name = (ev_meta.get("bundle_name") or "La compañía")
    summary = (f"Recomendación del comité: {band} (score {score_0_100}/100, confianza "
               f"{conf['value']:.0%}). {verdict_txt} "
               f"Basado en {len(active)} especialistas con datos y una cobertura del "
               f"{ev_meta.get('coverage',0):.0%}.")
    if vetoes:
        summary += f" Atención: {len(vetoes)} veto(s) del comité de riesgo/legal."

    thesis_bits = [f["text"] for f in strengths[:3]]
    thesis = (" ".join(thesis_bits) if thesis_bits else
              "Tesis pendiente de más evidencia; el comité recomienda ampliar información.")

    negotiation = []
    if val_op:
        negotiation += (val_op.get("conditions") or [])
    if any("apalancamiento" in (c.lower()) for c in conditions):
        negotiation.append("Reflejar la deuda en el precio (ajuste de EV a Equity) o vincular earn-out.")

    return {
        "recommendation": band,
        "investment_score": score_0_100,
        "confidence": conf["value"],
        "executive_summary": summary,
        "investment_thesis": thesis,
        "strengths": strengths, "weaknesses": weaknesses, "risks": risks,
        "opportunities": [],                      # Fase 2 (Strategy/Market/Operations)
        "open_questions": questions,
        "conditions_to_proceed": conditions,
        "valuation": (val_op or {}).get("evidence", []),
        "negotiation": sorted(set(negotiation)),
        "committee": opinions,
        "reasoning": {
            "weights_applied": weights,
            "dispersion": disp,
            "vetoes": [{"specialist": v["specialist"], "veto_kind": v["veto_kind"]} for v in vetoes],
            "engines_used": ev_meta.get("engines_used", []),
            "engines_missing": ev_meta.get("engines_missing", []),
            "coverage": ev_meta.get("coverage", 0),
            "confidence_factors": conf["factors"],
            "score_method": "committee-weighted-v1",
        },
    }
