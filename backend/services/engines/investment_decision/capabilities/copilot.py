"""Copilot Q&A (POST /decision/{id}/ask). Responde SOLO con la evidencia de una decisión ya
almacenada (fact-lock). Si la pregunta excede lo soportado ⇒ unsupported=True (no inventa).
La UI conversacional vive fuera; aquí está la respuesta fundamentada."""

import os
from typing import Dict, List
from services.engines.investment_decision import store

_STOP = {"de", "la", "el", "los", "las", "y", "o", "que", "cual", "cuál", "es", "en", "un", "una",
         "por", "para", "the", "of", "is", "what", "how", "and", "a"}


def _tokens(q: str) -> List[str]:
    import re
    return [t for t in re.findall(r"[a-záéíóúñ0-9]+", (q or "").lower()) if t not in _STOP and len(t) > 2]


def _all_findings(result: Dict) -> List[Dict]:
    out = []
    for key in ("strengths", "weaknesses", "risks", "open_questions"):
        for f in result.get(key) or []:
            out.append(f)
    for o in result.get("committee") or []:
        for key in ("strengths", "weaknesses", "risks"):
            for f in o.get(key) or []:
                out.append(f)
    return out


async def ask(decision_id: str, question: str) -> Dict:
    rec = await store.get(decision_id)
    if not rec:
        return {"decision_id": decision_id, "question": question, "answer": "",
                "evidence": [], "confidence": 0.0, "unsupported": True,
                "error": "decision_not_found"}
    result = rec.get("result") or {}
    toks = set(_tokens(question))

    # Coincidencia por palabras clave sobre las conclusiones (determinista)
    matches, evid = [], []
    for f in _all_findings(result):
        txt = (f.get("text") or "").lower()
        if toks & set(_tokens(txt)):
            matches.append(f.get("text"))
            evid.extend(f.get("evidence") or [])

    # Preguntas frecuentes mapeadas a campos del resultado
    if any(t in toks for t in ("recomendacion", "recomendación", "veredicto", "banda", "proceed")):
        matches.insert(0, f"Recomendación: {result.get('recommendation')} "
                          f"(score {result.get('investment_score')}/100, confianza {result.get('confidence')}).")
    if any(t in toks for t in ("condicion", "condiciones", "conditions")):
        matches += (result.get("conditions_to_proceed") or [])
    if any(t in toks for t in ("valoracion", "valoración", "precio", "multiplo", "múltiplo")):
        evid += result.get("valuation") or []

    supported = bool(matches or evid)
    answer_det = (" ".join(dict.fromkeys([m for m in matches if m]))[:800]
                  if supported else "No hay evidencia en esta decisión para responder a esa pregunta.")

    # Redacción IA opcional (fact-lock) si el provider tiene clave; si no, respuesta determinista.
    answer = answer_det
    try:
        from services.engines.investment_decision.engine import NARRATIVE_PROVIDER, _PROVIDER_KEY
        if supported and os.environ.get(_PROVIDER_KEY.get(NARRATIVE_PROVIDER, "")):
            from docstudio.model_provider import generate_summary
            ai = await generate_summary(
                {"question": question, "supported_facts": matches,
                 "instruction_extra": "Responde SOLO con los hechos soportados; en español, breve."},
                doc_type="investment_decision", provider=NARRATIVE_PROVIDER, fact_lock=True) or {}
            if ai.get("executive_summary") and "error" not in ai and "raw_text" not in ai:
                answer = ai["executive_summary"]
    except Exception:
        pass

    return {"decision_id": decision_id, "question": question, "answer": answer,
            "evidence": evid[:12], "confidence": round(result.get("confidence", 0.0), 4),
            "unsupported": not supported}
