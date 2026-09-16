"""Model Provider Layer — Abstract AI interface for Document Intelligence Studio.

Separates analysis/reasoning/narrative from the concrete model used.
Default provider: Claude (decisión 4 del DOCUMENT_STUDIO_UNIFICATION_PLAN — la IA de
los documentos es NARRATIVA y usa Claude). `provider` sigue siendo un parámetro por si
se quiere otro modelo puntualmente. La IA nunca inventa cifras: las calcula el motor
financiero/los engines; la IA solo redacta (fact-lock).
Every call is audited: provider, model, prompt, response, tokens, cost.
"""

import asyncio
import logging
from typing import Dict, Optional
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

# Modelo NVIDIA del tier gratuito para failover (rápido y fiable). Configurable con
# NVIDIA_MODEL_FALLBACK; se usa cuando el modelo primario (NVIDIA_MODEL) no responde.
NVIDIA_FALLBACK_MODEL = "meta/llama-3.1-8b-instruct"
COMPANY_DESCRIPTION_PROMPT_VERSION = 3


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


# Marcadores de fuga de razonamiento (modelos "thinking" que escriben su proceso en vez
# de la descripción). En una descripción en español correcta no aparecen estas frases.
_REASONING_MARKERS = (
    "the user wants", "we need to", "we must", "we can say", "let's count", "let me",
    "i need to", "json object", "okay,", "the object social", "according to the",
    "word count", "```",
)

# Meta-comentario sobre la fuente (defecto típico del fallback): la descripción debe
# describir la actividad, nunca comentar lo que el objeto social dice o deja de decir.
_META_MARKERS = (
    "no menciona", "sin especificar si", "no se especifica", "no queda claro",
    "no se detalla", "objeto social no", "no especifica ",
)


def _reject_description(desc: str, json_failed: bool) -> Optional[str]:
    """Devuelve un motivo si la salida NO es una descripción válida (para no guardarla).
    Protege la caché frente a fugas de razonamiento o respuestas no conformes."""
    if not desc:
        return "empty"
    if json_failed:
        return "json_parse_failed"
    words = desc.split()
    if len(words) < 3:
        return "too_short"
    if len(words) > 120:
        return "too_long"
    low = desc.lower()
    if any(m in low for m in _REASONING_MARKERS):
        return "reasoning_leak"
    if any(m in low for m in _META_MARKERS):
        return "meta_commentary"
    return None


async def generate_company_description(objeto_social: str, cnae_es: Optional[str],
                                       name: Optional[str], provider: str = "nvidia",
                                       document_id: str = None) -> Dict:
    """Reformula el OBJETO SOCIAL registral en una descripción CF breve (2-3 frases, ES).
    FACT-LOCK estricto: la IA SOLO reformula el texto dado; NO añade personas, lugares,
    cifras, fechas, hechos ni productos que no estén en el objeto social/CNAE. No inventa."""
    prompt = f"""Redacta una descripción útil de la actividad de una empresa española para una ficha
de inteligencia empresarial. Escribe 2-3 frases en español natural y correcto.
EXTENSIÓN (importante): alcanza entre 40 y 75 palabras cuando el objeto social o el
CNAE aporten contenido suficiente; en ese caso NO te quedes por debajo de 40 palabras.
Para llegar al rango, desarrolla el alcance de los servicios, el ámbito de actuación o
el tipo de operaciones que YA consten en la fuente, sin inventar. Solo escribe menos de
40 palabras si la fuente es realmente escasa; nunca añadas relleno ni suposiciones.

ESTRUCTURA: primero explica la actividad principal que conste en el objeto social
o en el CNAE. Después explica las actividades secundarias de otra naturaleza y
cómo figuran en el objeto social. Una tercera frase puede aclarar el alcance
de los servicios o instrumentos citados, SOLO si consta expresamente. Si hay
dos líneas distintas (por ejemplo, asesoramiento comercial y tenencia de valores),
no ocultes la segunda ni las presentes como una misma actividad.

ESTILO EDITORIAL: escribe en prosa, no como enumeración registral. Agrupa
instrumentos semejantes sin perder la distinción entre participaciones y otros
valores. Evita copiar listas largas de verbos como "compra, venta, arrendamiento"
si no aportan una idea distintiva. Usa minúsculas en los nombres comunes y las
tildes correctas; conserva las siglas y los nombres propios.
No escribas todo el texto en mayúsculas ni capitalices cada palabra. NO menciones el
nombre, la razón social ni las siglas de la propia empresa dentro de la descripción
(la ficha ya los muestra en la cabecera): empieza siempre por la actividad, nunca por
el nombre. Evita fórmulas vacías como "se dedica a diversas actividades" y evita
afirmaciones comerciales.

REGLA FUNDAMENTAL (FACT-LOCK): usa EXCLUSIVAMENTE la información del objeto social y la actividad CNAE
de abajo. NO añadas ni inventes personas, lugares, fechas, cifras, productos, hechos ni juicios que no
estén explícitos en ese texto. Solo reformula/resume lo dado en prosa legible. Nada de marketing.

EMPRESA: {name or "—"}
ACTIVIDAD (CNAE, español): {cnae_es or "—"}
OBJETO SOCIAL (texto registral a reformular):
{(objeto_social or "").strip()[:1500]}

El objeto social define actividades previstas, no prueba cuáles desarrolla hoy.
No conviertas una facultad de negociar o poseer valores en gestión de carteras,
servicios financieros a clientes o inversiones realizadas. Si el dato no permite
identificar una actividad principal, resume las actividades explícitas sin
elegir una por tu cuenta.

Devuelve SOLO JSON válido: {{"description": "la descripción, 2-3 frases en español"}}"""
    import os
    _desc_model = os.environ.get("NVIDIA_DESC_MODEL", NVIDIA_FALLBACK_MODEL)
    result = await _call_provider(provider, "company_description", prompt, document_id,
                                  model=_desc_model, keep_meta=True)
    if not isinstance(result, dict):
        return {"error": "invalid_provider_result"}
    # `raw_text` presente => el JSON no se pudo parsear (típico de fugas de razonamiento).
    json_failed = bool(result.get("raw_text")) and not result.get("description")
    desc = (result.get("description") or "").strip()
    motivo = _reject_description(desc, json_failed)
    if motivo:
        logger.warning("company_description descartada (%s) model=%s: %r",
                       motivo, result.get("_model"), desc[:120])
        result["description"] = None
        result["error"] = f"description_rejected:{motivo}"
        return result
    result["description"] = desc
    return result


async def _call_provider(provider: str, task: str, prompt: str, document_id: str = None,
                         model: str = None, keep_meta: bool = False) -> Dict:
    """Call the AI provider and audit the result."""
    now = now_iso()
    audit = {
        "audit_id": new_id(),
        "provider": provider,
        "task": task,
        # La regla editorial v3 puede superar 2.000 caracteres antes del objeto social.
        # Guardamos el contexto completo de esta tarea para auditar el fact-lock.
        "prompt": prompt[:4000] if task == "company_description" else prompt[:2000],
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

    # Save audit (best-effort: telemetría; nunca debe romper la generación, y debe tolerar
    # ejecutarse en un event loop de un hilo worker donde el cliente Motor global no aplica).
    try:
        await db.docstudio_ai_audit.insert_one(audit)
    except Exception:
        pass

    # Remove internal metadata. `keep_meta=True` lo conserva SOLO para trazabilidad interna
    # del llamador (p. ej. `resolve_description` guarda `_model`/`_fallback_used` en Mongo);
    # nunca se expone en la respuesta pública de /ficha.
    if not keep_meta:
        result.pop("_model", None)
        result.pop("_tokens", None)
        result.pop("_fallback_used", None)

    return result


async def _send_message_threaded(system_message: str, provider: str, model: str, prompt: str) -> str:
    """Ejecuta la llamada LLM (emergentintegrations) en un hilo con su propio event loop.

    emergentintegrations bloquea el event loop durante la llamada; en uvicorn con un
    único worker eso impide que las tareas diferidas (p. ej. la lectura de mercado)
    devuelvan `pending` de inmediato. Al aislarla en un hilo, el loop principal queda
    libre para responder mientras el modelo genera. No usa Mongo (motor sigue en el
    loop principal), así que no hay problemas de loops cruzados.
    """
    import os as _os

    def _worker():
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        async def _inner():
            chat = LlmChat(
                api_key=_os.environ.get("EMERGENT_LLM_KEY"),
                session_id=f"docstudio_{new_id()[:8]}",
                system_message=system_message,
            ).with_model(provider, model)
            return await chat.send_message(UserMessage(text=prompt))

        return asyncio.run(_inner())

    response = await asyncio.to_thread(_worker)
    return str(response)


async def _call_openai(prompt: str) -> Dict:
    """Call GPT-5.2 via Emergent LLM Key (aislada en hilo, no bloquea el event loop)."""
    try:
        text = await _send_message_threaded(
            "You are a professional financial analyst generating structured intelligence reports in Spanish. Always return valid JSON.",
            "openai", "gpt-5.2", prompt)
        parsed = _extract_json(text)
        parsed["_model"] = "gpt-5.2"
        return parsed
    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        return {"error": str(e), "_model": "gpt-5.2"}


async def _call_claude(prompt: str) -> Dict:
    """Call Claude via Emergent LLM Key (aislada en hilo, no bloquea el event loop)."""
    try:
        text = await _send_message_threaded(
            "You are a professional executive writer generating polished narratives in Spanish. Always return valid JSON.",
            "anthropic", "claude-sonnet-4-6", prompt)
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
        res["_fallback_used"] = False
        return res
    if has_fallback:
        logger.warning(f"NVIDIA primario '{primary}' no responde; failover a '{fallback}'")
        res = await _nvidia_once(prompt, fallback, full_timeout)
        res["_fallback_used"] = True
        return res
    res["_fallback_used"] = False
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
