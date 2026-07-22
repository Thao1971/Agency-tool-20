"""HTML-entity normalization for the ingestion pipeline.

Some sources (notably CNMV scraping and PLACSP feeds) deliver text with HTML
entities (`&#211;`, `&amp;`, `&aacute;`). We MUST store clean, decoded text so
that search, filters, matching, exports, embeddings, Universal Search and RAG all
operate on canonical strings. Normalization happens at ingestion time, never at
the presentation layer.

Usage:
    from services.text_normalize import normalize_strings
    doc = normalize_strings(doc)        # recursively decodes every str field
"""

import html
from typing import Any

# Heuristic: only touch strings that actually contain an HTML entity, so the
# function is a cheap no-op for already-clean data and safe to run repeatedly.
def _has_entity(s: str) -> bool:
    return "&" in s and ";" in s


def clean_text(value: Any) -> Any:
    """Decode HTML entities in a single value (no-op for non-strings)."""
    if isinstance(value, str) and _has_entity(value):
        return html.unescape(value)
    return value


def normalize_strings(obj: Any) -> Any:
    """Recursively decode HTML entities across dicts, lists and strings."""
    if isinstance(obj, str):
        return clean_text(obj)
    if isinstance(obj, list):
        return [normalize_strings(x) for x in obj]
    if isinstance(obj, dict):
        return {k: normalize_strings(v) for k, v in obj.items()}
    return obj
