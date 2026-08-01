"""ARROBA Copilot — autonomía proactiva (nudges), copilot-voice-v1.

Deja que el Copilot **avise por su cuenta** de algo relevante que ha notado, gobernado por el nivel de
autonomía del usuario. Reglas duras:
  - nivel 0 (silencioso): nunca.
  - nivel ≥1 (informa): avisos SOLO informativos (evolución a peor, cobertura baja).
  - nivel ≥2 (propone): además puede sugerir un siguiente paso (nunca acción con efecto externo).
Un solo nudge, y solo cuando aporte. Nunca inventa: se apoya en la evidencia ya calculada. Nada se
ejecuta solo. Ver ARROBA_COPILOT_MEMORY_SESSIONS_PERSONALIZATION.md (§3.3) y el CIM.
"""

from typing import Dict, Optional


def build(out: Dict, ctx: Dict) -> Optional[Dict]:
    try:
        autonomy = int(ctx.get("autonomy_level"))
    except Exception:
        autonomy = 1
    if autonomy <= 0 or out.get("degraded"):
        return None

    name = ctx.get("name") or "esta compañía"
    delta = ((ctx.get("entity_history") or {}).get("delta")) or {}
    coverage = ctx.get("coverage")

    # Informativos (nivel ≥1)
    if delta and not delta.get("first") and delta.get("direction") == "worsened":
        return {"kind": "inform",
                "message": f"Aviso: {name} ha perdido atractivo desde el último análisis; "
                           "convendría revisar qué ha cambiado."}
    if isinstance(coverage, (int, float)) and coverage < 0.5:
        return {"kind": "inform",
                "message": f"Ojo: esta lectura se apoya en datos parciales (cobertura "
                           f"{round(coverage*100)}%); tómala como preliminar."}

    # Sugerencia (solo nivel ≥2)
    if autonomy >= 2 and delta and delta.get("direction") == "improved":
        return {"kind": "suggest",
                "message": f"{name} ha mejorado desde la última vez; si encaja, puedo convocar al "
                           "comité para actualizar la tesis."}
    return None
