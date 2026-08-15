"""Model Provider Layer — Abstract AI interface for Document Intelligence Studio.

Separates analysis/reasoning/narrative from the concrete model used.
Default provider: Claude (decisión 4 del DOCUMENT_STUDIO_UNIFICATION_PLAN — la IA de
los documentos es NARRATIVA y usa Claude). `provider` sigue siendo un parámetro por si
se quiere otro modelo puntualmente. La IA nunca inventa cifras: las calcula el motor
financiero/los engines; la IA solo redacta (fact-lock).
Every call is audited: provider, model, prompt, response, tokens, cost.
"""

import logging
from typing import Dict, Optional
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

# Modelo NVIDIA del tier gratuito para failover (rápido y fiable). Configurable con
# NVIDIA_MODEL_FALLBACK; se usa cuando el modelo primario (NVIDIA_MODEL) no responde.
NVIDIA_FALLBACK_MODEL = "meta/llama-3.1-8b-instruct"


async def generate_analysis(data: Dict, instruction: str, provider: str = "claude",
                            document_id: str = None) -> Dict:
    """Generate structured analysis from data. Returns JSON, never HTML/PDF."""
    prompt = f"""Analyze the following data and return a JSON object with your findings.

INSTRUCTION: {instruction}

DATA:
{_truncate_data(data)}

Return ONLY valid JSON with fields: findings (array of strings), metrics (object), risks (array), opportunities (array).
Language: Spanish. Be concise and professional."""

    result = await _call_provider(provider, "analysis", prompt, document_id)
    return result


async def generate_narrative(structured_data: Dict, instruction: str, provider: str = "claude",
                             document_id: str = None) -> Dict:
    """Generate professional narrative text from structured conclusions. Returns text, never HTML."""
    prompt = f"""Transform the following structured data into professional narrative text in Spanish.

INSTRUCTION: {instruction}

DATA:
{_truncate_data(structured_data)}

Return ONLY valid JSON with fields: executive_summary (string), key_findings (array of strings), conclusion (string), recommendations (array of strings).
Write in a professional, executive tone. Be concise. No marketing language."""

    result = await _call_provider(provider, "narrative", prompt, document_id)
    return result


async def generate_summary(context: Dict, doc_type: str = "sector_report",
                           provider: str = "claude", document_id: str = None,
                           fact_lock: bool = True) -> Dict:
    """Generate executive summary, key findings, and conclusion for a document.
    
    fact_lock=True (default): AI can ONLY use data present in context.
    No invented figures, no estimated metrics, no inferred data without source.
    """
    templates = {
        "sector_report": "Generate an executive summary for a sector intelligence report. Include: overview of the sector, key economic indicators, growth trends, main players dynamics, and outlook.",
        "company_profile": "Generate an executive summary for a company profile. Include: company positioning, financial health assessment, competitive landscape, and strategic outlook.",
        "investment_decision": "You are the secretary of an M&A Investment Committee. Write the narrative for a decision ALREADY taken by the committee. The recommendation, score and band are FIXED and given in the context — do NOT change them, do NOT compute or introduce any figure that is not in the context. Only turn the committee's structured conclusions into an executive summary and an investment thesis.",
        "market_reading": ("Escribe una LECTURA DE MERCADO de 2-3 frases, en español, para un "
                           "comprador/analista de M&A. Combina en un texto fluido: la posición de "
                           "la empresa en su sector (ranking, percentil), el estado del sector "
                           "(crecimiento, dinamismo, tendencia), el contexto territorial y la "
                           "concentración del mercado. Empieza por lo más relevante para decidir. "
                           "Tono ejecutivo y claro, sin lenguaje comercial. Devuelve la lectura en "
                           "executive_summary; deja recommendations vacío."),
    }
    instruction = templates.get(doc_type, templates["sector_report"])

    fact_lock_clause = """

CRITICAL RULES (FACT-LOCK MODE):
- ONLY use data explicitly present in the CONTEXT DATA below.
- NEVER invent, estimate, or infer any financial figure not in the data.
- If a metric is missing, state "dato no disponible" — do NOT fabricate a number.
- Every claim must be traceable to a specific data point in the context.
- If you cannot make a statement based on the data, omit it entirely.
""" if fact_lock else ""

    prompt = f"""{instruction}{fact_lock_clause}

CONTEXT DATA:
{_truncate_data(context)}

Return ONLY valid JSON:
{{
  "executive_summary": "2-3 paragraph executive summary in Spanish",
  "key_findings": ["finding 1", "finding 2", "finding 3", "finding 4", "finding 5"],
  "conclusion": "1 paragraph conclusion in Spanish",
  "recommendations": ["rec 1", "rec 2", "rec 3"]
}}

Professional tone. Data-driven. Spanish language. No speculation beyond the data provided."""

    result = await _call_provider(provider, "summary", prompt, document_id)
    if fact_lock:
        result["_fact_locked"] = True
    return result


async def generate_copilot_message(context: Dict, provider: str = "claude",
                                   document_id: str = None) -> Dict:
    """Reescribe un BORRADOR determinista del Copilot en prosa natural, ejecutiva y ágil (ES).
    FACT-LOCK estricto: solo puede reformular el borrador y la evidencia dada; NO puede añadir,
    estimar ni inventar dato alguno. Reutiliza los proveedores existentes (claude/openai/nvidia)."""
    draft = context.get("draft") or ""
    persona = context.get("persona") or "Eres un copiloto senior de M&A conversando con un profesional."
    hist = context.get("history") or []
    hist_block = ""
    if hist:
        lines = "\n".join(f"- Usuario: {h.get('user')}\n  Copilot: {h.get('copilot')}" for h in hist[-6:])
        hist_block = ("\n\nCONVERSACIÓN RECIENTE (para dar continuidad; no la repitas literalmente ni "
                      f"añadas datos nuevos):\n{lines}")
    prompt = f"""{persona}
Reescribe el BORRADOR en una respuesta natural, ejecutiva, técnicamente rigurosa y ágil, en español.
Responde primero a la pregunta; breve no es seco; prioriza lo material; distingue hecho, interpretación
e incertidumbre. Mantén la continuidad con la conversación reciente si la hay (no repitas lo que el
usuario ya sabe).{hist_block}

REGLA FUNDAMENTAL (FACT-LOCK): NO añadas, estimes ni inventes ningún dato. Usa EXCLUSIVAMENTE lo que
aparece en BORRADOR y EVIDENCIA. Si algo no está, no lo afirmes. No cambies cifras, score ni banda.

Perfil del usuario: {context.get('profile')}. Verbosidad: {context.get('verbosity')}.

BORRADOR:
{draft}

EVIDENCIA (solo contexto; no salgas de aquí):
{_truncate_data(context.get('evidence') or {})}

Devuelve SOLO JSON válido: {{"message": "la respuesta reescrita en español"}}"""
    result = await _call_provider(provider, "copilot_voice", prompt, document_id)
    if isinstance(result, dict) and result.get("raw_text") and not result.get("message"):
        result["message"] = result["raw_text"]
    return result


async def generate_company_description(objeto_social: str, cnae_es: Optional[str],
                                       name: Optional[str], provider: str = "nvidia",
                                       document_id: str = None) -> Dict:
    """Reformula el OBJETO SOCIAL registral en una descripción CF breve (2-3 frases, ES).
    FACT-LOCK estricto: la IA SOLO reformula el texto dado; NO añade personas, lugares,
    cifras, fechas, hechos ni productos que no estén en el objeto social/CNAE. No inventa."""
    prompt = f"""Reformula el OBJETO SOCIAL de una empresa española en una descripción breve, clara y
profesional (2-3 frases, en español), apta para una ficha de inteligencia empresarial.

REGLA FUNDAMENTAL (FACT-LOCK): usa EXCLUSIVAMENTE la información del objeto social y la actividad CNAE
de abajo. NO añadas ni inventes personas, lugares, fechas, cifras, productos, hechos ni juicios que no
estén explícitos en ese texto. Solo reformula/resume lo dado en prosa legible. Nada de marketing.

EMPRESA: {name or "—"}
ACTIVIDAD (CNAE, español): {cnae_es or "—"}
OBJETO SOCIAL (texto registral a reformular):
{(objeto_social or "").strip()[:1500]}

Devuelve SOLO JSON válido: {{"description": "la descripción reformulada, 2-3 frases en español"}}"""
    import os
    _desc_model = os.environ.get("NVIDIA_DESC_MODEL", NVIDIA_FALLBACK_MODEL)
    result = await _call_provider(provider, "company_description", prompt, document_id, model=_desc_model)
    if isinstance(result, dict) and not result.get("description") and result.get("raw_text"):
        result["description"] = result["raw_text"].strip()
    return result


async def _call_provider(provider: str, task: str, prompt: str, document_id: str = None,
                         model: str = None) -> Dict:
    """Call the AI provider and audit the result."""
    now = now_iso()
    audit = {
        "audit_id": new_id(),
        "provider": provider,
        "task": task,
        "prompt": prompt[:2000],
        "document_id": document_id,
        "created_at": now,
    }

    try:
        if provider == "openai":
            result = await _call_openai(prompt)
        elif provider == "claude":
            result = await _call_claude(prompt)
        elif provider == "nvidia":
            result = await _call_nvidia(prompt, model)
        else:
            result = {"error": f"Unknown provider: {provider}"}

        audit["response"] = str(result)[:2000]
        audit["status"] = "success" if "error" not in result else "error"
        audit["model"] = result.get("_model", "unknown")
        audit["tokens"] = result.get("_tokens", 0)

    except Exception as e:
        result = {"error": str(e)}
        audit["response"] = str(e)[:500]
        audit["status"] = "error"

    # Save audit
    await db.docstudio_ai_audit.insert_one(audit)

    # Remove internal metadata
    result.pop("_model", None)
    result.pop("_tokens", None)

    return result


async def _call_openai(prompt: str) -> Dict:
    """Call GPT-5.2 via Emergent LLM Key."""
    import json
    import os
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        api_key = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"docstudio_{new_id()[:8]}",
            system_message="You are a professional financial analyst generating structured intelligence reports in Spanish. Always return valid JSON.",
        ).with_model("openai", "gpt-5.2")

        user_msg = UserMessage(text=prompt)
        response = await chat.send_message(user_msg)
        text = str(response)

        parsed = _extract_json(text)
        parsed["_model"] = "gpt-5.2"
        return parsed

    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        return {"error": str(e), "_model": "gpt-5.2"}


async def _call_claude(prompt: str) -> Dict:
    """Call Claude via Emergent LLM Key."""
    import json
    import os
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        api_key = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"docstudio_{new_id()[:8]}",
            system_message="You are a professional executive writer generating polished narratives in Spanish. Always return valid JSON.",
        ).with_model("anthropic", "claude-sonnet-4-6")

        user_msg = UserMessage(text=prompt)
        response = await chat.send_message(user_msg)
        text = str(response)

        parsed = _extract_json(text)
        parsed["_model"] = "claude-sonnet-4-6"
        return parsed

    except Exception as e:
        logger.error(f"Claude call failed: {e}")
        return {"error": str(e), "_model": "claude-sonnet-4-6"}


async def _nvidia_once(prompt: str, model: str, timeout: float) -> Dict:
    """Una llamada a NVIDIA NIM (OpenAI-compatible) con un modelo y timeout concretos."""
    import os
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        return {"error": "NVIDIA_API_KEY no configurada", "_model": model}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "temperature": 0.2, "max_tokens": 900,
                      "messages": [
                          {"role": "system", "content": "You are a professional executive writer generating polished narratives in Spanish. Always return valid JSON."},
                          {"role": "user", "content": prompt}]})
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
        parsed = _extract_json(text)
        parsed["_model"] = model
        return parsed
    except Exception as e:
        logger.error(f"NVIDIA call failed (model={model}): {e!r}")
        return {"error": str(e) or repr(e), "_model": model}


async def _call_nvidia(prompt: str, model: str = None) -> Dict:
    """NVIDIA NIM con FAILOVER automático a un modelo del tier gratuito que responda.
    Primario = `model` (arg) o env NVIDIA_MODEL. Si falla/timeout, reintenta con
    NVIDIA_MODEL_FALLBACK (por defecto meta/llama-3.1-8b-instruct: gratis, rápido, fiable).
    Configurable: para volver al 70B basta poner NVIDIA_MODEL=meta/llama-3.3-70b-instruct;
    el failover al 8b lo protege si vuelve a caer. No altera cifras (fact-lock en el prompt)."""
    import os
    primary = model or os.environ.get("NVIDIA_MODEL", NVIDIA_FALLBACK_MODEL)
    fallback = os.environ.get("NVIDIA_MODEL_FALLBACK", NVIDIA_FALLBACK_MODEL)
    full_timeout = float(os.environ.get("NVIDIA_TIMEOUT", "50"))
    has_fallback = bool(fallback) and fallback != primary
    # Con failover disponible, cortamos antes el intento primario para no colgar la request
    # si el modelo configurado (p. ej. el 70B) está caído en NVIDIA.
    primary_timeout = float(os.environ.get("NVIDIA_PRIMARY_TIMEOUT", "12")) if has_fallback else full_timeout
    res = await _nvidia_once(prompt, primary, primary_timeout)
    if "error" not in res:
        return res
    if has_fallback:
        logger.warning(f"NVIDIA primario '{primary}' no responde; failover a '{fallback}'")
        return await _nvidia_once(prompt, fallback, full_timeout)
    return res


def _extract_json(text: str) -> Dict:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    import json
    import re

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {"raw_text": text}


def _truncate_data(data: Dict, max_len: int = 3000) -> str:
    """Truncate data dict to fit in prompt."""
    import json
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
