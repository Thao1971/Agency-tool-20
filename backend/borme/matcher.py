"""BORME matcher — Preliminary matching against company candidates."""

import logging
from typing import Dict, List, Optional
from difflib import SequenceMatcher
from borme.parser import normalize_company_name

logger = logging.getLogger(__name__)


def match_event_to_company(event: Dict, company: Dict) -> Optional[Dict]:
    """Try to match a BORME event to a company candidate.
    Returns match info dict or None if no match."""

    event_name_raw = event.get("company_name_raw", "")
    event_name_norm = event.get("company_name_normalized") or normalize_company_name(event_name_raw)
    event_province = (event.get("registry_province") or "").upper().strip()

    company_cif = (company.get("cif") or "").strip().upper()
    company_name = company.get("company_name") or company.get("name", "")
    company_name_norm = normalize_company_name(company_name)
    company_province = (company.get("province") or "").upper().strip()

    # Province boost (not a barrier)
    province_match = event_province and company_province and event_province == company_province
    province_boost = 0.08 if province_match else 0.0

    # Level 1: CIF exact match (if CIF present in event text)
    event_text = event.get("event_text_raw") or event.get("full_text", "")
    if company_cif and len(company_cif) >= 8 and company_cif in event_text.upper():
        return {
            "match_method": "cif_exact",
            "confidence_match": min(0.95 + province_boost, 1.0),
        }

    # Level 2: Exact normalized name
    if company_name_norm and event_name_norm and company_name_norm == event_name_norm:
        return {
            "match_method": "name_exact",
            "confidence_match": min(0.80 + province_boost, 1.0),
        }

    # Level 3: Fuzzy name match
    if company_name_norm and event_name_norm:
        ratio = SequenceMatcher(None, company_name_norm, event_name_norm).ratio()
        if ratio >= 0.85:
            return {
                "match_method": "name_fuzzy_high",
                "confidence_match": min(0.55 + province_boost + (ratio - 0.85) * 2, 0.80),
            }
        elif ratio >= 0.70:
            # Weak match — return as candidate, not confirmed match
            return {
                "match_method": "name_fuzzy_weak",
                "confidence_match": round(0.30 + province_boost + (ratio - 0.70) * 1.5, 2),
            }

    return None


def match_events_batch(events: List[Dict], company: Dict, min_confidence: float = 0.40) -> tuple:
    """Match a list of events against a company.
    Returns (matches, unmatched_candidates)."""
    matches = []
    candidates = []

    for event in events:
        result = match_event_to_company(event, company)
        if result:
            enriched = {**event, **result}
            if result["confidence_match"] >= min_confidence:
                if result["match_method"] != "name_fuzzy_weak":
                    matches.append(enriched)
                else:
                    candidates.append(enriched)
            else:
                candidates.append(enriched)

    # Sort by confidence descending
    matches.sort(key=lambda x: x.get("confidence_match", 0), reverse=True)
    candidates.sort(key=lambda x: x.get("confidence_match", 0), reverse=True)

    return matches, candidates
