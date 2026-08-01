"""ARROBA Copilot — voz/personalización de la respuesta (copilot-voice-v1).

Traduce el ROL del usuario y el NIVEL DE AUTONOMÍA en directivas para la voz única:
- Rol → verbosidad/tono (analista: detalle; partner/inversor: síntesis ejecutiva; asesor: equilibrado).
- Autonomía → estado CIM máximo que el Copilot puede tomar de forma PROACTIVA (0 conversación …
  4 ejecutor acotado). NO afecta a la respuesta a una pregunta directa (siempre permitida) ni salta el
  gate de autorización de acciones con efecto externo.

Regla dura: la verbosidad solo puede ACORTAR/enfatizar; NUNCA inventa ni añade hechos. No toca scores.
Ver memory/ARROBA_COPILOT_MEMORY_SESSIONS_PERSONALIZATION.md (§3.2, §3.3).
"""

import re
from typing import Dict, Optional

VOICE_VERSION = "copilot-voice-v1"

# Rol → verbosidad
_ROLE_VERBOSITY = {
    "analyst": "detailed", "analista": "detailed",
    "partner": "executive", "director": "executive", "partner_director": "executive",
    "investor": "executive", "inversor": "executive",
    "advisor": "balanced", "asesor": "balanced",
}
_DEFAULT_VERBOSITY = "balanced"

# Verbosidad → tope de caracteres del cuerpo (solo acorta; tamaños conversacionales, no telegráficos:
# ejecutivo ~2-4 frases, analista varios párrafos). Es una red de seguridad; el narrador ya dimensiona.
_LIMITS = {"detailed": 2000, "balanced": 1100, "executive": 700}

# Nivel de autonomía → estado CIM máximo PROACTIVO (A Observador/B Informador/C Recomendador/
# D Conversación/E Director/F Ejecutor). Etiquetas alineadas con el Orquestador.
_AUTONOMY_CIM = {0: "conversation", 1: "informer", 2: "recommender", 3: "director", 4: "executor"}


def resolve(role: Optional[str], autonomy_level) -> Dict:
    verbosity = _ROLE_VERBOSITY.get((role or "").strip().lower(), _DEFAULT_VERBOSITY)
    try:
        a = int(autonomy_level)
    except Exception:
        a = 1
    return {"voice_version": VOICE_VERSION, "verbosity": verbosity,
            "detail_limit": _LIMITS[verbosity], "tone": "profesional",
            "autonomy_level": a, "max_proactive_state": _AUTONOMY_CIM.get(a, "informer")}


def _truncate(text: str, limit: int) -> str:
    """Acorta por frontera de frase sin superar `limit`. Nunca añade contenido nuevo."""
    if not text or len(text) <= limit:
        return text
    window = text[:limit]
    # última puntuación de cierre de frase dentro de la ventana
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut >= int(limit * 0.5):
        return window[:cut + 1].strip()
    return window.rstrip() + "…"


def apply_verbosity(answer: Optional[Dict], directives: Dict) -> Optional[Dict]:
    """Acorta el cuerpo natural (message/detail) al tope de la verbosidad. Muta y devuelve el dict."""
    if not isinstance(answer, dict):
        return answer
    limit = directives.get("detail_limit", _LIMITS["balanced"])
    for field in ("message", "detail"):
        if isinstance(answer.get(field), str):
            answer[field] = _truncate(answer[field], limit)
    return answer
