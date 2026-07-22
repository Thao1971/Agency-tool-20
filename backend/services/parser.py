"""Deterministic parser: extracts emails, phones, addresses from text using regex."""

import re
import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Patterns
EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'
)

PHONE_PATTERN = re.compile(
    r'(?:\+?\d{1,3}[\s\-]?)?'
    r'(?:\(?\d{1,4}\)?[\s\-]?)?'
    r'\d{2,4}[\s\-]?\d{2,4}[\s\-]?\d{2,4}'
)

# Spanish postal codes
POSTAL_CODE_PATTERN = re.compile(r'\b\d{5}\b')

# Common address indicators
ADDRESS_INDICATORS = [
    r'(?:calle|c/|avda\.?|avenida|paseo|plaza|pza\.?|ronda|travesía|camino)',
    r'(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?)',
]
ADDRESS_PATTERN = re.compile(
    r'(?:' + '|'.join(ADDRESS_INDICATORS) + r')\s+[^,\n]{3,50}',
    re.IGNORECASE
)


def extract_emails(text: str) -> List[str]:
    emails = list(set(EMAIL_PATTERN.findall(text)))
    # Filter out image/file extensions mistaken as emails
    filtered = [e for e in emails if not e.endswith(('.png', '.jpg', '.gif', '.svg', '.webp'))]
    return filtered[:10]


def extract_phones(text: str) -> List[str]:
    raw = PHONE_PATTERN.findall(text)
    phones = []
    for p in raw:
        clean = re.sub(r'[\s\-]', '', p)
        if 7 <= len(clean) <= 15 and not clean.startswith('0000'):
            phones.append(p.strip())
    return list(set(phones))[:5]


def extract_addresses(text: str) -> List[str]:
    matches = ADDRESS_PATTERN.findall(text)
    return [m.strip() for m in matches][:5]


def extract_postal_codes(text: str) -> List[str]:
    return list(set(POSTAL_CODE_PATTERN.findall(text)))[:5]


def find_relevant_links(links: List[Dict], base_url: str, priority_patterns: List[str]) -> List[Dict]:
    """Filter internal links that match priority patterns."""
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower()
    relevant = []
    seen_paths = set()

    for link in links:
        href = link.get("href", "")
        if not href:
            continue

        parsed = urlparse(href)
        link_domain = parsed.netloc.lower() if parsed.netloc else base_domain

        # Only internal links
        if link_domain != base_domain and parsed.netloc:
            continue

        path = parsed.path.lower().rstrip("/")
        if not path or path == "/" or path in seen_paths:
            continue

        # Check if path matches any priority pattern
        text_lower = link.get("text", "").lower()
        for pattern in priority_patterns:
            pat = pattern.lower()
            if pat in path or pat in text_lower:
                seen_paths.add(path)
                full_url = f"{parsed_base.scheme}://{base_domain}{parsed.path}"
                relevant.append({
                    "url": full_url,
                    "path": path,
                    "text": link.get("text", ""),
                    "matched_pattern": pattern
                })
                break

    return relevant


def parse_page_content(text: str, page_url: str) -> Dict:
    """Extract structured data from a single page's text."""
    return {
        "url": page_url,
        "emails": extract_emails(text),
        "phones": extract_phones(text),
        "addresses": extract_addresses(text),
        "postal_codes": extract_postal_codes(text),
        "text_length": len(text),
        "text_preview": text[:500] if text else ""
    }


def aggregate_parsed_data(pages_data: List[Dict]) -> Dict:
    """Aggregate parsed data from multiple pages."""
    all_emails = []
    all_phones = []
    all_addresses = []
    all_postal_codes = []
    all_text = []

    for page in pages_data:
        all_emails.extend(page.get("emails", []))
        all_phones.extend(page.get("phones", []))
        all_addresses.extend(page.get("addresses", []))
        all_postal_codes.extend(page.get("postal_codes", []))
        all_text.append(f"--- PAGE: {page['url']} ---\n{page.get('text_preview', '')}")

    return {
        "emails": list(set(all_emails))[:10],
        "phones": list(set(all_phones))[:5],
        "addresses": list(set(all_addresses))[:5],
        "postal_codes": list(set(all_postal_codes))[:5],
        "combined_text": "\n\n".join(all_text)
    }
