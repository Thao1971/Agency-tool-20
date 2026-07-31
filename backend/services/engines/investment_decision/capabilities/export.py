"""Export-payload (GET /decision/{id}/export-payload). Devuelve una estructura NEUTRA
render-ready (secciones/bloques + índice de evidencia). El motor NO genera el binario
PDF/Word: eso lo hace un renderer externo. Así el export queda contemplado sin romper la
restricción «No implementar PDF»."""

from typing import Dict, List
from services.engines.investment_decision import store


def _texts(items) -> List[str]:
    return [f.get("text") for f in (items or []) if f.get("text")]


async def export_payload(decision_id: str, fmt: str = "pdf") -> Dict:
    rec = await store.get(decision_id)
    if not rec:
        return {"decision_id": decision_id, "error": "decision_not_found"}
    r = rec.get("result") or {}

    sections = [
        {"title": "Recomendación", "blocks": [
            {"type": "verdict", "recommendation": r.get("recommendation"),
             "investment_score": r.get("investment_score"), "confidence": r.get("confidence")}]},
        {"title": "Resumen ejecutivo", "blocks": [{"type": "text", "text": r.get("executive_summary")}]},
        {"title": "Tesis de inversión", "blocks": [{"type": "text", "text": r.get("investment_thesis")}]},
        {"title": "Fortalezas", "blocks": [{"type": "list", "items": _texts(r.get("strengths"))}]},
        {"title": "Riesgos", "blocks": [{"type": "list", "items": _texts(r.get("risks"))}]},
        {"title": "Condiciones para proceder", "blocks": [{"type": "list", "items": r.get("conditions_to_proceed") or []}]},
        {"title": "Preguntas abiertas", "blocks": [{"type": "list", "items": _texts(r.get("open_questions"))}]},
        {"title": "Comité", "blocks": [{"type": "committee", "items": [
            {"specialist": o["specialist"], "recommendation": o["recommendation"],
             "score": o.get("score"), "weight_applied": o.get("weight_applied"),
             "veto": o.get("veto")} for o in (r.get("committee") or [])]}]},
    ]
    evidence_index = []
    for o in r.get("committee") or []:
        evidence_index.extend(o.get("evidence") or [])

    return {"decision_id": decision_id, "format": (fmt or "pdf"),
            "meta": r.get("meta", {}), "sections": sections,
            "evidence_index": evidence_index,
            "note": "Estructura render-ready; el binario PDF/Word lo produce un renderer externo."}
