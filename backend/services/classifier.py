"""LLM Classifier: uses GPT-5.2 via emergentintegrations to classify and extract structured data.
Acts ONLY on content already extracted by the scraper and parser. Never scrapes on its own."""

import os
import json
import logging
import uuid
from typing import Dict, List, Optional
from emergentintegrations.llm.chat import LlmChat, UserMessage
from database import db

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
MODEL_PROVIDER = "openai"
MODEL_NAME = "gpt-5.2"


async def get_active_taxonomy() -> Dict:
    """Fetch active taxonomy from DB."""
    categories = await db.taxonomy_categories.find(
        {"active": True}, {"_id": 0}
    ).sort("order", 1).to_list(100)

    for cat in categories:
        subs = await db.taxonomy_subcategories.find(
            {"category_id": cat["id"], "active": True}, {"_id": 0}
        ).sort("order", 1).to_list(100)
        cat["subcategories"] = [s["name"] for s in subs]

    return categories


def format_taxonomy_for_prompt(taxonomy: List[Dict]) -> str:
    lines = []
    for cat in taxonomy:
        lines.append(f"- {cat['name']}")
        for sub in cat.get("subcategories", []):
            lines.append(f"  - {sub}")
    return "\n".join(lines)


async def classify_agency(
    scraped_content: str,
    parsed_data: Dict,
    url: str,
    pages_visited: List[str]
) -> Dict:
    """Use LLM to classify and extract structured data from scraped content."""

    taxonomy = await get_active_taxonomy()
    taxonomy_text = format_taxonomy_for_prompt(taxonomy)

    emails_str = ", ".join(parsed_data.get("emails", [])) or "None found"
    phones_str = ", ".join(parsed_data.get("phones", [])) or "None found"
    addresses_str = ", ".join(parsed_data.get("addresses", [])) or "None found"
    pages_str = ", ".join(pages_visited) or url

    # Truncate content to fit context
    max_content = 12000
    content = scraped_content[:max_content] if len(scraped_content) > max_content else scraped_content

    prompt = f"""You are an agency data extraction and classification engine. Analyze the following website content from an advertising/marketing/communications agency and extract structured information.

CRITICAL RULES:
1. Only extract information that is CLEARLY present in the provided content
2. If information cannot be determined with reasonable confidence, return null
3. Category and subcategory MUST be selected from the TAXONOMY below - never invent new ones
4. If no category fits well, return null for both category and subcategory
5. Tags must reflect actual website content, not industry stereotypes
6. main_clients: only include if explicitly mentioned by name on the website
7. has_awards: only true if specific awards, prizes or recognitions are mentioned
8. Confidence scores: 0 = no evidence found, 50 = partial/ambiguous evidence, 100 = clearly and explicitly stated
9. Description must be brief, factual, and based solely on website content
10. Never invent or guess information not present in the content

AVAILABLE TAXONOMY:
{taxonomy_text}

WEBSITE URL: {url}
PAGES SCRAPED: {pages_str}

EXTRACTED BY PARSER (verified data):
- Emails found: {emails_str}
- Phones found: {phones_str}
- Addresses found: {addresses_str}

WEBSITE CONTENT:
{content}

Return a valid JSON object with exactly these fields (no additional text before or after the JSON):
{{
  "company_name": "string or null",
  "description": "brief factual description based on website content, or null",
  "category": "exact category name from taxonomy or null",
  "subcategory": "exact subcategory name from taxonomy or null",
  "tags": ["array of relevant tags derived from actual content"],
  "has_awards": false,
  "awards_evidence": ["list of specific awards/prizes mentioned"],
  "main_clients": ["list of explicitly mentioned client names only"],
  "main_contact_name": "string or null",
  "main_contact_role": "string or null",
  "address_street": "string or null",
  "address_city": "string or null",
  "address_province": "string or null",
  "postal_code": "string or null",
  "country": "string or null",
  "confidence_overall": 0,
  "confidence_category": 0,
  "confidence_clients": 0,
  "confidence_contact": 0,
  "confidence_awards": 0,
  "confidence_address": 0,
  "confidence_description": 0,
  "evidence_notes": {{
    "category": "reason for category choice or null",
    "clients": "where clients were found or null",
    "awards": "what awards evidence was found or null",
    "contact": "where contact info was found or null",
    "address": "where address was found or null",
    "description": "what the description is based on or null"
  }}
}}"""

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"classify-{uuid.uuid4()}",
            system_message="You are a precise data extraction engine. Return only valid JSON. Never invent data."
        )
        chat.with_model(MODEL_PROVIDER, MODEL_NAME)

        user_msg = UserMessage(text=prompt)
        response = await chat.send_message(user_msg)

        # Parse JSON from response
        result = _extract_json(response)
        if result:
            return result

        logger.warning(f"Could not parse LLM response as JSON for {url}")
        return _empty_classification()

    except Exception as e:
        logger.error(f"LLM classification failed for {url}: {e}")
        return _empty_classification()


def _extract_json(text: str) -> Optional[Dict]:
    """Try to extract JSON from LLM response."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def _empty_classification() -> Dict:
    return {
        "company_name": None,
        "description": None,
        "category": None,
        "subcategory": None,
        "tags": [],
        "has_awards": False,
        "awards_evidence": [],
        "main_clients": [],
        "main_contact_name": None,
        "main_contact_role": None,
        "address_street": None,
        "address_city": None,
        "address_province": None,
        "postal_code": None,
        "country": None,
        "confidence_overall": 0,
        "confidence_category": 0,
        "confidence_clients": 0,
        "confidence_contact": 0,
        "confidence_awards": 0,
        "confidence_address": 0,
        "confidence_description": 0,
        "evidence_notes": {}
    }
