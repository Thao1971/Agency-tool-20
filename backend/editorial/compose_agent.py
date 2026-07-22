"""Compose Agent — editorial bullet, entity detection, anchor text."""

import re
import os
import json
import uuid
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


def compose_bullet(title: str, action: Optional[str], entities: List[Dict] = None) -> Dict:
    """Generate editorial bullet and anchor text from title + detected action."""
    clean_title = _clean_title(title)

    # Build anchor text from action
    anchor = action or _extract_first_verb(clean_title)

    # Primary entity
    primary_entity = entities[0]["entity_name_raw"] if entities else None

    # Build bullet: keep it short, link the action verb
    bullet = clean_title
    if len(bullet) > 120:
        bullet = bullet[:117] + "..."

    return {
        "editorial_bullet": bullet,
        "anchor_text": anchor,
        "primary_entity": primary_entity,
    }


def detect_entities(title: str, text: str = "") -> List[Dict]:
    """Detect companies, people, brands from title and text."""
    combined = f"{title} {text}"
    entities = []

    # Pattern: capitalized multi-word names (likely company/brand)
    # e.g. "Good Rebels", "Havas Media", "McCann Worldgroup"
    company_patterns = re.findall(r'\b([A-Z][a-záéíóúñ]*(?:\s+[A-Z][a-záéíóúñ]*){0,4})\b', combined)
    seen = set()
    for name in company_patterns:
        if len(name) < 3 or name.lower() in _STOP_WORDS or name in seen:
            continue
        seen.add(name)
        entities.append({
            "entity_type": "company",
            "entity_name_raw": name,
            "match_confidence": 0.6,
            "match_method": "pattern",
            "is_primary": len(entities) == 0,
        })
        if len(entities) >= 5:
            break

    return entities


def detect_facts(title: str, text: str = "") -> List[Dict]:
    """Detect numerical facts (revenue, percentages, amounts)."""
    combined = f"{title} {text}"
    facts = []

    # Money patterns
    for match in re.finditer(r'(\d+(?:[.,]\d+)?)\s*(millones|M|mill\.?|€|EUR|USD)\b', combined, re.IGNORECASE):
        facts.append({
            "fact_type": "amount",
            "value": match.group(1).replace(",", "."),
            "unit": match.group(2),
            "label": f"{match.group(1)} {match.group(2)}",
            "confidence": 0.8,
        })

    # Percentage patterns
    for match in re.finditer(r'(\d+(?:[.,]\d+)?)\s*%', combined):
        facts.append({
            "fact_type": "percentage",
            "value": match.group(1).replace(",", "."),
            "unit": "%",
            "label": f"{match.group(1)}%",
            "confidence": 0.9,
        })

    return facts[:5]


async def compose_with_llm(title: str, text: str, section: str, action: str = None, locale: str = "es") -> Dict:
    """LLM-enhanced composition for editorial bullet."""
    EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=EMERGENT_KEY, session_id=f"compose-{uuid.uuid4()}", system_message="Editorial writer for marketing/advertising industry. Brief, factual, Spanish.")
        chat.with_model("openai", "gpt-5.2")

        prompt = f"""Write a brief editorial bullet (max 15 words) in Spanish for this news item.
Title: {title}
Section: {section}
Text: {text[:300]}

Return ONLY JSON:
{{"bullet": "short editorial bullet in Spanish", "anchor_text": "main action verb", "primary_entity": "main company or person mentioned"}}"""

        response = await chat.send_message(UserMessage(text=prompt))
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(response[start:end])
            return {
                "editorial_bullet": result.get("bullet", title[:100]),
                "anchor_text": result.get("anchor_text", action),
                "primary_entity": result.get("primary_entity"),
                "composition_method": "llm",
            }
    except Exception as e:
        logger.warning(f"LLM composition failed: {e}")

    return {"editorial_bullet": title[:100], "anchor_text": action, "composition_method": "fallback"}


def _clean_title(title: str) -> str:
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'^[\s\-–—]+', '', title)
    return title


def _extract_first_verb(text: str) -> Optional[str]:
    verbs = ["compra", "adquiere", "lanza", "presenta", "nombra", "gana", "abre",
             "factura", "crece", "firma", "cierra", "vende", "fusiona", "inaugura"]
    for v in verbs:
        if v in text.lower():
            return v
    return None


_STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "con", "por",
    "que", "se", "su", "al", "es", "como", "para", "más", "pero", "sus",
    "The", "New", "And", "For", "With", "From", "This", "That", "News",
}
