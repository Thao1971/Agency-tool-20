"""Identity & classification normalization for the canonical master record."""

import re
import unicodedata
from typing import List, Optional

from services.cnae_catalog import CNAE_SECTIONS, CNAE_DIVISIONS, resolve_cnae_to_section

SECTION_LABELS = {s["code"]: s["label"] for s in CNAE_SECTIONS}

# Legal-form tokens stripped when building the dedupe name key.
_LEGAL_TOKENS = {
    "sl", "sa", "slu", "sau", "scp", "sc", "sll", "slne", "coop", "aie", "ag",
    "sociedad", "limitada", "anonima", "unipersonal", "cooperativa", "sociedad civil",
    "sl.", "sa.", "s.l", "s.a", "s.l.", "s.a.", "s.l.u", "s.a.u",
}


def strip_accents(text: str) -> str:
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_cif(cif: Optional[str]) -> Optional[str]:
    if not cif:
        return None
    c = re.sub(r"[^A-Za-z0-9]", "", cif).upper()
    return c or None


def name_key(name: Optional[str]) -> Optional[str]:
    """Canonical dedupe key: lowercased, deaccented, legal forms & punctuation removed."""
    if not name:
        return None
    s = strip_accents(name).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    tokens = [t for t in s.split() if t and t not in _LEGAL_TOKENS]
    key = " ".join(tokens).strip()
    return key or None


def section_label(section_code: Optional[str]) -> Optional[str]:
    return SECTION_LABELS.get(section_code) if section_code else None


def division_of(cnae_code: Optional[str]) -> Optional[str]:
    if not cnae_code:
        return None
    digits = re.sub(r"[^0-9]", "", str(cnae_code))
    return digits[:2].zfill(2) if digits else None


def division_label(division: Optional[str]) -> Optional[str]:
    if not division:
        return None
    return (CNAE_DIVISIONS.get(division) or {}).get("label")


def resolve_section(cnae_code: Optional[str], explicit_section: Optional[str] = None) -> Optional[str]:
    if explicit_section:
        return explicit_section
    div = division_of(cnae_code)
    return resolve_cnae_to_section(div) if div else None


def build_aliases(*names) -> List[str]:
    """Deduplicated, order-preserving alias list from any name-ish inputs (str or list)."""
    seen = set()
    out = []
    for n in names:
        items = n if isinstance(n, list) else [n]
        for item in items:
            if not item or not isinstance(item, str):
                continue
            v = item.strip()
            k = v.lower()
            if v and k not in seen:
                seen.add(k)
                out.append(v)
    return out
