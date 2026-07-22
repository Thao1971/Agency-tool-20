"""Optional, traceable AI semantic extraction (D-S1).

Reglas primero; la IA SOLO se invoca cuando aporta extracción semántica (capacidades,
tecnologías, propuesta de valor, resumen) desde el objeto social. Toda salida IA es
trazable (method='ai' + ai_model + evidence) y NUNCA inventa sin evidencia: si no hay
objeto_social, no se llama. Resiliente: ante cualquier error, devuelve None (fallback a reglas).
"""

import json
import os
from typing import Dict, Optional

AI_MODEL = ("openai", "gpt-5.4")

_SYSTEM = (
    "Eres un analista que EXTRAE información semántica de empresas españolas a partir "
    "EXCLUSIVAMENTE del texto proporcionado (objeto social y descripción CNAE). "
    "NO inventes datos. Si algo no aparece en el texto, devuélvelo como lista vacía. "
    "Responde SOLO con JSON válido."
)


async def extract(objeto_social: str, cnae_description: str, name: str) -> Optional[Dict]:
    if not (objeto_social or "").strip():
        return None
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        prompt = (
            f"Empresa: {name}\nCNAE: {cnae_description or ''}\nObjeto social: {objeto_social}\n\n"
            "Devuelve JSON con esta forma exacta:\n"
            '{"capabilities": ["..."], "technologies": ["..."], '
            '"value_proposition": "una frase", "summary": "2-3 frases"}\n'
            "Solo incluye elementos respaldados por el texto."
        )
        chat = LlmChat(api_key=key, session_id=f"sem-{abs(hash(name)) % 10**8}",
                       system_message=_SYSTEM).with_model(*AI_MODEL)
        resp = await chat.send_message(UserMessage(text=prompt))
        text = resp if isinstance(resp, str) else getattr(resp, "content", str(resp))
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].replace("json", "", 1).strip()
        data = json.loads(text)
        return {"capabilities": data.get("capabilities") or [],
                "technologies": data.get("technologies") or [],
                "value_proposition": data.get("value_proposition"),
                "summary": data.get("summary"), "ai_model": f"{AI_MODEL[0]}/{AI_MODEL[1]}"}
    except Exception:
        return None
