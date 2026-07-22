"""BORME parser — PDF text extraction + structured event segmentation."""

import re
import io
import hashlib
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════
# TEXT EXTRACTION (primary + fallback)
# ══════════════════════════════════════════

def extract_text_from_pdf(pdf_bytes: bytes) -> Tuple[str, str]:
    """Extract text from PDF. Returns (text, method_used).
    Tries PyPDF2 first, falls back to pdfminer.six."""

    # Primary: PyPDF2
    text = _extract_pypdf2(pdf_bytes)
    if text and len(text.strip()) > 100:
        return text, "pypdf2"

    # Fallback: pdfminer.six
    text = _extract_pdfminer(pdf_bytes)
    if text and len(text.strip()) > 100:
        return text, "pdfminer"

    return "", "failed"


def _extract_pypdf2(pdf_bytes: bytes) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_text = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages_text.append(t)
        return "\n".join(pages_text)
    except Exception as e:
        logger.debug(f"PyPDF2 extraction failed: {e}")
        return ""


def _extract_pdfminer(pdf_bytes: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text
        return extract_text(io.BytesIO(pdf_bytes))
    except Exception as e:
        logger.debug(f"pdfminer extraction failed: {e}")
        return ""


# ══════════════════════════════════════════
# SEGMENTATION (split text into entries)
# ══════════════════════════════════════════

# Pattern: 6-digit number + dash + company name (ending with legal form + period)
ENTRY_PATTERN = re.compile(r'^(\d{5,6})\s*-\s*(.+)', re.MULTILINE)

# Registry data pattern (marks end of entry)
REGISTRY_PATTERN = re.compile(r'Datos registrales\.\s*(.+?)(?:\.|$)', re.IGNORECASE)


def segment_entries(text: str) -> List[Dict]:
    """Segment PDF text into individual company entries."""
    # Pre-process: rejoin lines broken by PDF column wrapping
    lines = text.split('\n')
    rejoined = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r'^\d{5,6}\s*-\s*', stripped):
            rejoined.append(stripped)
        elif rejoined:
            rejoined[-1] = rejoined[-1] + ' ' + stripped
        else:
            rejoined.append(stripped)
    clean_text = '\n'.join(rejoined)

    entries = []
    matches = list(ENTRY_PATTERN.finditer(clean_text))

    for i, match in enumerate(matches):
        entry_number = match.group(1)
        company_start = match.group(2).strip()

        start_pos = match.start()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(clean_text)
        full_text = clean_text[start_pos:end_pos].strip()

        company_name = _extract_company_name(company_start)

        if not company_name or len(full_text) < 20:
            continue

        has_registry = bool(REGISTRY_PATTERN.search(full_text))

        entries.append({
            "entry_number": entry_number,
            "company_name_raw": company_name,
            "full_text": full_text,
            "has_registry_data": has_registry,
        })

    return entries


def _extract_company_name(text: str) -> str:
    """Extract company name from the first part of an entry line."""
    # Company name ends at first period after a legal form or at first newline
    legal_forms = r'(?:SL|SA|SLU|SLNE|SLP|SAU|SC|SCCL|SLL|SCOOP|SE)\b'
    match = re.search(rf'(.+?{legal_forms})\.?\s', text, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip('.')

    # Fallback: take text up to first period
    dot_pos = text.find('.')
    if dot_pos > 0 and dot_pos < 200:
        return text[:dot_pos].strip()

    # Last fallback: first line
    nl_pos = text.find('\n')
    if nl_pos > 0:
        return text[:nl_pos].strip().rstrip('.')

    return text[:150].strip()


# ══════════════════════════════════════════
# EVENT DETECTION (keyword-based)
# ══════════════════════════════════════════

EVENT_KEYWORDS = {
    # Governance
    "Nombramientos": ("governance", "appointment"),
    "Ceses/Dimisiones": ("governance", "cessation"),
    "Ceses": ("governance", "cessation"),
    "Dimisiones": ("governance", "cessation"),
    "Reelecciones": ("governance", "reelection"),
    "Revocaciones": ("governance", "revocation"),

    # Capital
    "Ampliación de capital": ("capital", "capital_increase"),
    "Ampliación del objeto social": ("corporate", "purpose_change"),
    "Reducción de capital": ("capital", "capital_decrease"),

    # Corporate changes
    "Constitución": ("corporate", "constitution"),
    "Cambio de denominación social": ("corporate", "name_change"),
    "Cambio de denominación": ("corporate", "name_change"),
    "Cambio de domicilio social": ("corporate", "address_change"),
    "Cambio de domicilio": ("corporate", "address_change"),
    "Cambio de objeto social": ("corporate", "purpose_change"),
    "Cambio del Organo de Administración": ("governance", "governance_change"),

    # Dissolution
    "Disolución": ("dissolution", "dissolution"),
    "Extinción": ("dissolution", "extinction"),
    "Liquidación": ("dissolution", "liquidation"),
    "Concurso": ("dissolution", "insolvency"),

    # M&A
    "Fusión": ("ma", "merger"),
    "Absorción": ("ma", "absorption"),
    "Escisión": ("ma", "spin_off"),

    # Powers
    "Apoderamiento": ("governance", "power_of_attorney"),
    "Apo.Manc.": ("governance", "joint_power"),
    "Apo.Sol.": ("governance", "sole_power"),

    # Other
    "Fe de erratas": ("correction", "errata"),
    "Declaración de unipersonalidad": ("corporate", "sole_shareholder"),
    "Socio único": ("corporate", "sole_shareholder"),
    "Auditor": ("corporate", "auditor"),
    "Depósito de cuentas": ("corporate", "accounts_filing"),

    # Previously unclassified — now covered
    "Modificaciones estatutarias": ("corporate", "bylaws_amendment"),
    "Modificacion estatutaria": ("corporate", "bylaws_amendment"),
    "Cierre provisional hoja registral": ("dissolution", "provisional_closure"),
    "Cierre provisional": ("dissolution", "provisional_closure"),
    "Otros conceptos": ("corporate", "other_corporate"),
    "Situación concursal": ("dissolution", "insolvency"),
    "Cancelaciones": ("corporate", "cancellation"),
    "Transformación de sociedad": ("corporate", "corporate_transformation"),
    "Emisión de obligaciones": ("capital", "bond_issuance"),
}


def detect_events(entry: Dict) -> List[Dict]:
    """Detect all events within a single company entry."""
    text = entry.get("full_text", "")
    detected = []

    for keyword, (event_type, event_subtype) in EVENT_KEYWORDS.items():
        if keyword in text:
            # Extract excerpt around the keyword
            idx = text.find(keyword)
            excerpt_start = max(0, idx)
            excerpt_end = min(len(text), idx + 300)
            excerpt = text[excerpt_start:excerpt_end].strip()

            detected.append({
                "event_type": event_type,
                "event_subtype": event_subtype,
                "event_title": keyword,
                "event_text_excerpt": excerpt[:500],
            })

    # If no known keyword matched, register as "other"
    if not detected:
        detected.append({
            "event_type": "other",
            "event_subtype": "unknown",
            "event_title": "Unclassified event",
            "event_text_excerpt": text[:500],
        })

    return detected


def build_idempotency_key(publication_date: str, official_identifier: str,
                          entry_number: str, company_name_raw: str) -> str:
    """Generate unique key for deduplication."""
    raw = f"{publication_date}|{official_identifier}|{entry_number}|{company_name_raw}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ══════════════════════════════════════════
# COMPANY NAME NORMALIZATION
# ══════════════════════════════════════════

def normalize_company_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""
    n = name.upper().strip()
    # Remove legal forms
    for form in [' SL', ' SA', ' SLU', ' SLNE', ' SLP', ' SAU', ' SC', ' SLL', ' SE',
                 ' S.L.', ' S.A.', ' S.L.U.', ' S.C.', ',SL', ',SA', ', SL', ', SA']:
        n = n.replace(form, '')
    # Remove punctuation
    n = re.sub(r'[.,;:\-\'\"()]', ' ', n)
    # Collapse spaces
    n = re.sub(r'\s+', ' ', n).strip()
    # Remove accents
    import unicodedata
    n = ''.join(c for c in unicodedata.normalize('NFD', n) if unicodedata.category(c) != 'Mn')
    return n
