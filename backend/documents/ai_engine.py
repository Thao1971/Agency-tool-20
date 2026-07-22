"""AI Engine — LLM-powered content generation for document blocks."""

import os
import json
import uuid
import logging
from typing import Dict
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
MODEL_PRIMARY = {"provider": "openai", "model": "gpt-5.2"}
MODEL_SECONDARY = {"provider": "openai", "model": "gpt-5-mini"}

BLOCK_PROMPTS = {
    "executive_summary": "Write a concise executive summary (2-3 paragraphs) for a company report. Be factual, professional, data-driven.",
    "company_overview": "Write a brief company overview paragraph based on the provided data. Factual, no speculation.",
    "top_strengths": "List the top 3-5 strengths of this company based on the data. Return as JSON array of strings.",
    "top_risks": "List the top 3-5 risks or weaknesses. Return as JSON array of strings.",
    "valuation_commentary": "Write a short valuation commentary paragraph based on the financial data provided.",
    "next_steps": "Suggest 3-5 actionable next steps. Return as JSON array of strings.",
    "market_position": "Write a brief market positioning paragraph based on category, competitors, and metrics.",
    "financial_highlights": "Summarize the key financial highlights in 2-3 sentences.",
    "slide_title": "Generate a concise, impactful slide title (max 8 words).",
    "chart_caption": "Generate a brief chart caption (1 sentence).",
}


async def generate_block(block_type: str, context: Dict, locale: str = "es", model_tier: str = "primary") -> Dict:
    """Generate a structured text block using LLM."""
    model_config = MODEL_PRIMARY if model_tier == "primary" else MODEL_SECONDARY
    prompt_base = BLOCK_PROMPTS.get(block_type, f"Generate content for block type: {block_type}")

    locale_instruction = "Respond in Spanish." if locale == "es" else f"Respond in {locale}."

    prompt = f"""{prompt_base}

{locale_instruction}

Context data:
{json.dumps(context, default=str, ensure_ascii=False)[:6000]}

Return ONLY a valid JSON object with this structure:
{{
  "block_type": "{block_type}",
  "content": "<the generated text or array>",
  "tone": "professional",
  "word_count": <approximate word count>
}}"""

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"docgen-{uuid.uuid4()}",
            system_message="You are a professional business document writer. Return only valid JSON."
        )
        chat.with_model(model_config["provider"], model_config["model"])

        response = await chat.send_message(UserMessage(text=prompt))
        result = _extract_json(response)
        if result:
            return {"status": "ok", "block": result, "model": model_config["model"]}

        return {"status": "ok", "block": {"block_type": block_type, "content": response, "tone": "professional"}, "model": model_config["model"]}

    except Exception as e:
        logger.error(f"AI block generation failed: {e}")
        return {"status": "error", "error": str(e), "block": None}


async def rewrite_block(text: str, instruction: str, locale: str = "es", model_tier: str = "secondary") -> Dict:
    """Rewrite/transform a text block."""
    model_config = MODEL_PRIMARY if model_tier == "primary" else MODEL_SECONDARY
    locale_instruction = "Respond in Spanish." if locale == "es" else f"Respond in {locale}."

    prompt = f"""Transform this text following this instruction: {instruction}

{locale_instruction}

Original text:
{text[:3000]}

Return ONLY a valid JSON object:
{{
  "original_length": <word count>,
  "result": "<transformed text>",
  "result_length": <word count>
}}"""

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"docrewrite-{uuid.uuid4()}",
            system_message="You are a professional text editor. Return only valid JSON."
        )
        chat.with_model(model_config["provider"], model_config["model"])

        response = await chat.send_message(UserMessage(text=prompt))
        result = _extract_json(response)
        if result:
            return {"status": "ok", "result": result, "model": model_config["model"]}
        return {"status": "ok", "result": {"result": response}, "model": model_config["model"]}

    except Exception as e:
        logger.error(f"AI rewrite failed: {e}")
        return {"status": "error", "error": str(e)}


def _extract_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None
