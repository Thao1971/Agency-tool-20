"""Model Provider Layer — Abstract AI interface for Document Intelligence Studio.

Separates analysis/reasoning/narrative from the concrete model used.
Providers: GPT-5.2 (analysis), Claude (narrative), future models.
Every call is audited: provider, model, prompt, response, tokens, cost.
"""

import logging
from typing import Dict, Optional
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)


async def generate_analysis(data: Dict, instruction: str, provider: str = "openai",
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


async def generate_narrative(structured_data: Dict, instruction: str, provider: str = "openai",
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
                           provider: str = "openai", document_id: str = None,
                           fact_lock: bool = True) -> Dict:
    """Generate executive summary, key findings, and conclusion for a document.
    
    fact_lock=True (default): AI can ONLY use data present in context.
    No invented figures, no estimated metrics, no inferred data without source.
    """
    templates = {
        "sector_report": "Generate an executive summary for a sector intelligence report. Include: overview of the sector, key economic indicators, growth trends, main players dynamics, and outlook.",
        "company_profile": "Generate an executive summary for a company profile. Include: company positioning, financial health assessment, competitive landscape, and strategic outlook.",
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


async def _call_provider(provider: str, task: str, prompt: str, document_id: str = None) -> Dict:
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
