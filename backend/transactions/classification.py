"""Transaction Classification Copilot — GPT-5.2 powered sector classification suggestions.

Principle: The AI proposes a hypothesis. The human decides.
- Always returns requires_human_review = true
- Validates against closed CIS taxonomy
- Persists every suggestion with full audit trail
- Never auto-applies classification
"""

import os
import json
import logging
from typing import Dict, List, Optional
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
MODEL_PROVIDER = "openai"
MODEL_NAME = "gpt-5.2"
PROMPT_VERSION = "v1.0"


async def get_taxonomy_map() -> Dict:
    """Fetch active taxonomy and build lookup structures."""
    categories = await db.taxonomy_categories.find(
        {"active": True}, {"_id": 0}
    ).sort("order", 1).to_list(100)

    cat_names = set()
    sub_map = {}  # category_name -> [subcategory_names]
    all_subs = set()

    for cat in categories:
        cat_names.add(cat["name"])
        subs = await db.taxonomy_subcategories.find(
            {"category_id": cat["id"], "active": True}, {"_id": 0}
        ).sort("order", 1).to_list(100)
        sub_names = [s["name"] for s in subs]
        sub_map[cat["name"]] = sub_names
        for s in sub_names:
            all_subs.add(s)

    return {
        "categories": categories,
        "cat_names": cat_names,
        "sub_map": sub_map,
        "all_subs": all_subs,
    }


def _format_taxonomy(tax_map: Dict) -> str:
    """Format taxonomy map as text for the LLM prompt."""
    lines = []
    for cat_name, sub_names in tax_map["sub_map"].items():
        lines.append(f"- {cat_name}")
        for sub in sub_names:
            lines.append(f"  - {sub}")
    return "\n".join(lines)


def _build_context(tx: Dict, company_data: Optional[Dict] = None) -> str:
    """Build context string from transaction and linked company data."""
    parts = []

    if tx.get("target_name"):
        parts.append(f"Target: {tx['target_name']}")
    if tx.get("buyer_name"):
        parts.append(f"Buyer: {tx['buyer_name']}")
    if tx.get("seller_name"):
        parts.append(f"Seller: {tx['seller_name']}")
    if tx.get("transaction_type"):
        parts.append(f"Transaction type: {tx['transaction_type']}")
    if tx.get("geography_primary"):
        parts.append(f"Country: {tx['geography_primary']}")
    if tx.get("sector_original"):
        parts.append(f"Original sector: {tx['sector_original']}")
    if tx.get("sector_original_label"):
        parts.append(f"Original sector label: {tx['sector_original_label']}")
    if tx.get("observations"):
        parts.append(f"Description: {tx['observations']}")
    if tx.get("value_eurm"):
        parts.append(f"Deal value: {tx['value_eurm']} EUR million")
    if tx.get("source"):
        parts.append(f"Source: {tx['source']}")
    if tx.get("buyer_type"):
        parts.append(f"Buyer type: {tx['buyer_type']}")

    if company_data:
        if company_data.get("company_name"):
            parts.append(f"Linked CIS company: {company_data['company_name']}")
        if company_data.get("category"):
            parts.append(f"CIS company category: {company_data['category']}")
        if company_data.get("subcategory"):
            parts.append(f"CIS company subcategory: {company_data['subcategory']}")
        if company_data.get("description"):
            parts.append(f"CIS company description: {company_data['description'][:300]}")
        if company_data.get("tags"):
            tags = company_data["tags"]
            if isinstance(tags, list):
                parts.append(f"CIS company tags: {', '.join(tags[:10])}")

    return "\n".join(parts)


async def suggest_classification(tx: Dict) -> Dict:
    """
    Call GPT-5.2 to suggest CIS category and subcategory for a transaction.
    Returns structured suggestion with reasoning, never auto-applies.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    tax_map = await get_taxonomy_map()
    taxonomy_text = _format_taxonomy(tax_map)

    # Get linked company data for the target if available
    company_data = None
    target_link = await db.transaction_company_links.find_one(
        {"transaction_id": tx["transaction_id"], "entity_role": "target",
         "match_status": {"$in": ["manual_confirmed", "auto_strong_candidate"]}},
        {"_id": 0}
    )
    if target_link and target_link.get("matched_company_id"):
        company_data = await db.agency_results.find_one(
            {"id": target_link["matched_company_id"]},
            {"_id": 0, "company_name": 1, "category": 1, "subcategory": 1,
             "description": 1, "tags": 1, "input_url": 1}
        )

    context = _build_context(tx, company_data)
    signals_used = []
    if tx.get("target_name"):
        signals_used.append("target_name")
    if tx.get("sector_original"):
        signals_used.append("original_sector")
    if tx.get("observations"):
        signals_used.append("transaction_description")
    if company_data:
        signals_used.append("matched_cis_company")
        if company_data.get("description"):
            signals_used.append("company_description")
        if company_data.get("category"):
            signals_used.append("company_existing_category")

    system_prompt = f"""Eres un asistente de clasificación sectorial para transacciones de M&A del sector marketing, publicidad, comunicación, tecnología publicitaria y servicios profesionales relacionados.

Tu trabajo es sugerir la categoría y subcategoría CIS más adecuada para una transacción.

REGLAS ESTRICTAS:
1. Debes elegir una categoría y subcategoría ÚNICAMENTE de la taxonomía oficial proporcionada abajo.
2. NO puedes inventar categorías ni subcategorías. Solo las que aparecen en la lista.
3. Si no hay evidencia suficiente, indica confianza baja.
4. Explica brevemente por qué sugieres esa clasificación.
5. Indica qué señales del contexto has usado.
6. Propón hasta 2 alternativas SOLO si existen dentro de la taxonomía oficial.
7. Devuelve EXCLUSIVAMENTE JSON válido, sin texto adicional.

TAXONOMÍA OFICIAL CIS:
{taxonomy_text}

FORMATO DE RESPUESTA (JSON estricto):
{{
  "suggested_category": "nombre exacto de la categoría",
  "suggested_subcategory": "nombre exacto de la subcategoría",
  "confidence": 0.0 a 1.0,
  "reasoning": "explicación breve de por qué esta clasificación",
  "signals_used": ["lista", "de", "señales"],
  "alternatives": [
    {{
      "category": "nombre exacto",
      "subcategory": "nombre exacto",
      "confidence": 0.0 a 1.0,
      "reasoning": "explicación breve"
    }}
  ]
}}"""

    user_prompt = f"""Clasifica esta transacción M&A:

{context}

Responde SOLO con JSON válido."""

    try:
        import uuid
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"classify-tx-{uuid.uuid4()}",
            system_message=system_prompt
        )
        chat.with_model(MODEL_PROVIDER, MODEL_NAME)

        user_msg = UserMessage(text=user_prompt)
        response = await chat.send_message(user_msg)
        raw_response = response.strip() if isinstance(response, str) else str(response)

        # Parse JSON from response (handle markdown code blocks)
        json_text = raw_response
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(json_text)

        # Validate against taxonomy
        suggested_cat = parsed.get("suggested_category", "")
        suggested_sub = parsed.get("suggested_subcategory", "")
        validation_status = "valid"
        validation_errors = []

        if suggested_cat not in tax_map["cat_names"]:
            validation_status = "invalid"
            validation_errors.append(f"Category '{suggested_cat}' not in CIS taxonomy")

        if suggested_cat in tax_map["sub_map"]:
            valid_subs = tax_map["sub_map"][suggested_cat]
            if suggested_sub not in valid_subs:
                validation_status = "invalid"
                validation_errors.append(f"Subcategory '{suggested_sub}' not valid for category '{suggested_cat}'")
        elif validation_status != "invalid":
            validation_status = "invalid"
            validation_errors.append(f"Cannot validate subcategory for unknown category '{suggested_cat}'")

        # Validate alternatives
        validated_alternatives = []
        for alt in parsed.get("alternatives", [])[:2]:
            alt_cat = alt.get("category", "")
            alt_sub = alt.get("subcategory", "")
            if alt_cat in tax_map["cat_names"] and alt_cat in tax_map["sub_map"] and alt_sub in tax_map["sub_map"][alt_cat]:
                validated_alternatives.append(alt)

        confidence = parsed.get("confidence", 0.5)
        if validation_status == "invalid":
            confidence = 0.0

        confidence_label = "low" if confidence < 0.5 else ("medium" if confidence < 0.8 else "high")

        return {
            "suggested_category": suggested_cat,
            "suggested_subcategory": suggested_sub,
            "confidence": round(confidence, 3),
            "confidence_label": confidence_label,
            "reasoning": parsed.get("reasoning", ""),
            "signals_used": signals_used,
            "alternative_suggestions": validated_alternatives,
            "model_used": f"{MODEL_PROVIDER}/{MODEL_NAME}",
            "prompt_version": PROMPT_VERSION,
            "raw_model_response": raw_response,
            "validation_status": validation_status,
            "validation_errors": validation_errors,
            "requires_human_review": True,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Classification LLM returned invalid JSON: {e}")
        return {
            "suggested_category": None,
            "suggested_subcategory": None,
            "confidence": 0.0,
            "confidence_label": "low",
            "reasoning": f"Model returned invalid JSON: {str(e)[:200]}",
            "signals_used": signals_used,
            "alternative_suggestions": [],
            "model_used": f"{MODEL_PROVIDER}/{MODEL_NAME}",
            "prompt_version": PROMPT_VERSION,
            "raw_model_response": raw_response if 'raw_response' in dir() else "",
            "validation_status": "invalid",
            "validation_errors": ["Model returned invalid JSON"],
            "requires_human_review": True,
        }

    except Exception as e:
        logger.error(f"Classification LLM error: {e}")
        return {
            "suggested_category": None,
            "suggested_subcategory": None,
            "confidence": 0.0,
            "confidence_label": "low",
            "reasoning": f"LLM call failed: {str(e)[:200]}",
            "signals_used": signals_used,
            "alternative_suggestions": [],
            "model_used": f"{MODEL_PROVIDER}/{MODEL_NAME}",
            "prompt_version": PROMPT_VERSION,
            "raw_model_response": "",
            "validation_status": "invalid",
            "validation_errors": [f"LLM error: {str(e)[:100]}"],
            "requires_human_review": True,
        }
