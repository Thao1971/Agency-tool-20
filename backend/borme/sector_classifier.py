"""BORME sector classifier — CNAE-2025 extraction, resolution and inference."""

import re
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Load CNAE-2025 taxonomy
CNAE_FILE = Path(__file__).parent / "cnae2025.json"
CNAE_TAXONOMY = {}
CNAE_SECTIONS = {}
CNAE_DIVISIONS = {}
CNAE_GROUPS = {}
CNAE_CLASSES = {}

def _load_cnae():
    global CNAE_TAXONOMY, CNAE_SECTIONS, CNAE_DIVISIONS, CNAE_GROUPS, CNAE_CLASSES
    if CNAE_TAXONOMY:
        return
    with open(CNAE_FILE, "r", encoding="utf-8") as f:
        CNAE_TAXONOMY = json.load(f)
    for code, title in CNAE_TAXONOMY.items():
        if len(code) == 1 and code.isalpha():
            CNAE_SECTIONS[code] = title
        elif len(code) == 2 and code.isdigit():
            CNAE_DIVISIONS[code] = title
        elif '.' in code:
            parts = code.split('.')
            if len(parts[1]) == 1:
                CNAE_GROUPS[code] = title
            elif len(parts[1]) >= 2:
                CNAE_CLASSES[code] = title

_load_cnae()


# ══════════════════════════════════════════
# CNAE code patterns in BORME text
# ══════════════════════════════════════════

CNAE_EXPLICIT_PATTERNS = [
    re.compile(r'CNAE[:\s\-]*(\d{2,4}(?:\.\d{1,2})?)', re.IGNORECASE),
    re.compile(r'C\.?N\.?A\.?E\.?[:\s\-]*(\d{2,4}(?:\.\d{1,2})?)', re.IGNORECASE),
    re.compile(r'actividad\s+principal[:\s\-]*(\d{2,4}(?:\.\d{1,2})?)', re.IGNORECASE),
    re.compile(r'CNAE\s+actividad\s+principal[:\s\-]*(\d{2,4}(?:\.\d{1,2})?)', re.IGNORECASE),
]

OBJECT_SOCIAL_PATTERNS = [
    re.compile(r'(?:Objeto\s+social|Constituye\s+el\s+objeto\s+social|La\s+sociedad\s+tiene\s+por\s+objeto|objeto\s+de\s+la\s+sociedad)[:\.\s]*(.*?)(?:Datos\s+registrales|Nombramientos|Ceses|\.\s*\d{5,6}\s*-|\Z)', re.IGNORECASE | re.DOTALL),
]


def classify_event(event: Dict, company_profiles_cache: Dict = None) -> Dict:
    """Main entry point: classify a BORME event with CNAE sector data.
    Returns sector fields to merge into the event."""

    text = event.get("event_text_raw", "") or event.get("full_text", "")
    excerpt = event.get("event_text_excerpt", "")
    company_name = event.get("company_name_raw", "")
    company_norm = event.get("company_name_normalized", "")

    # Level 1: Explicit CNAE in text
    result = _extract_explicit_cnae(text)
    if not result:
        result = _extract_explicit_cnae(excerpt)
    if result:
        return _build_sector_result(result["code"], "verified", "borme_text", 0.99, result.get("evidence", ""))

    # Level 2: Prior company record (cache lookup)
    if company_profiles_cache and company_norm:
        cached = company_profiles_cache.get(company_norm)
        if cached and cached.get("sector_status") == "verified":
            return _build_sector_result(
                cached["canonical_cnae_code"], "verified", "prior_company_record",
                0.93, f"From prior record: {cached.get('evidence_text', '')}"
            )

    # Level 3: Infer from object social text
    object_text = _extract_object_social(text)
    if not object_text:
        object_text = _extract_object_social(excerpt)
    if object_text:
        inferred = _infer_cnae_from_object(object_text)
        if inferred:
            return _build_sector_result(
                inferred["code"], "inferred", "object_text_inference",
                inferred["confidence"], f"Object: {object_text[:200]}"
            )

    # Level 4: Unavailable
    return {
        "cnae_code": None, "cnae_title": None,
        "cnae_section": None, "cnae_division": None, "cnae_group": None,
        "cnae_level": None,
        "sector_status": "unavailable", "sector_source": "none",
        "sector_confidence": None, "sector_evidence_text": None,
        "sector_extraction_version": "v1"
    }


def _extract_explicit_cnae(text: str) -> Optional[Dict]:
    """Try to find an explicit CNAE code in text."""
    if not text:
        return None
    for pattern in CNAE_EXPLICIT_PATTERNS:
        match = pattern.search(text)
        if match:
            raw_code = match.group(1).strip()
            normalized = _normalize_cnae_code(raw_code)
            if normalized and _validate_cnae_code(normalized):
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 50)
                return {"code": normalized, "evidence": text[start:end].strip()}
    return None


def _normalize_cnae_code(raw: str) -> Optional[str]:
    """Normalize a raw CNAE code to standard format (XX.XX)."""
    raw = raw.replace(" ", "").replace("-", "")
    if '.' in raw:
        return raw
    if len(raw) == 4:
        return f"{raw[:2]}.{raw[2:]}"
    if len(raw) == 3:
        return f"{raw[:2]}.{raw[2]}"
    if len(raw) == 2:
        return raw  # Division level
    return None


def _validate_cnae_code(code: str) -> bool:
    """Check if code exists in CNAE-2025 taxonomy."""
    return code in CNAE_TAXONOMY or code in CNAE_CLASSES or code in CNAE_GROUPS or code in CNAE_DIVISIONS


def _extract_object_social(text: str) -> Optional[str]:
    """Extract the 'objeto social' description from BORME text."""
    if not text:
        return None
    for pattern in OBJECT_SOCIAL_PATTERNS:
        match = pattern.search(text)
        if match:
            obj = match.group(1).strip()
            if len(obj) > 15:
                return obj[:500]
    return None


# Keyword → CNAE mapping for inference (priority sector)
OBJECT_KEYWORDS_MAP = [
    # Advertising & marketing
    (["agencia de publicidad", "publicidad y marketing", "servicios publicitarios", "campañas publicitarias"], "73.11"),
    (["representación de medios", "planificación de medios", "compra de medios"], "73.12"),
    (["estudios de mercado", "investigación de mercado", "encuestas"], "73.20"),
    (["relaciones públicas", "comunicación corporativa", "comunicación empresarial", "gestión de reputación"], "73.30"),
    (["marketing", "marketing directo", "trade marketing", "activaciones de marketing", "servicios de marketing"], "74.91"),
    # Design
    (["diseño gráfico", "comunicación visual", "branding", "identidad visual"], "74.12"),
    (["diseño de productos", "diseño industrial", "diseño de moda"], "74.11"),
    (["diseño de interiores"], "74.13"),
    # Audiovisual
    (["producción cinematográfica", "producción de vídeo", "producción audiovisual"], "59.15"),
    (["producción de programas de televisión", "producción televisiva"], "59.16"),
    (["posproducción", "postproducción"], "59.12"),
    (["radiodifusión", "emisora de radio"], "60.10"),
    (["programación de televisión", "emisión televisiva"], "60.20"),
    # Software & IT
    (["desarrollo de software", "programación informática", "desarrollo de aplicaciones", "programas informáticos"], "62.01"),
    (["consultoría informática", "consultoría tecnológica", "consultoría de sistemas"], "62.02"),
    (["gestión de recursos informáticos", "servicios informáticos"], "62.03"),
    (["procesamiento de datos", "hosting", "servicios en la nube", "centros de datos"], "63.10"),
    (["portales web", "plataformas digitales"], "63.91"),
    # Consulting
    (["consultoría de gestión", "consultoría empresarial", "asesoramiento empresarial", "consultoría de dirección"], "70.22"),
    # Events
    (["organización de eventos", "organización de ferias", "organización de congresos", "convenciones"], "82.30"),
    # Photography
    (["fotografía", "servicios fotográficos"], "74.20"),
    # Editing
    (["edición de libros", "editorial de libros"], "58.11"),
    (["edición de revistas", "publicaciones periódicas"], "58.13"),
]


def _infer_cnae_from_object(object_text: str) -> Optional[Dict]:
    """Infer CNAE from object social text using keyword matching."""
    text_lower = object_text.lower()
    best_match = None
    best_score = 0

    for keywords, cnae_code in OBJECT_KEYWORDS_MAP:
        for kw in keywords:
            if kw in text_lower:
                # Score based on keyword specificity (longer = more specific)
                score = len(kw) / 50.0
                score = min(score + 0.45, 0.85)  # Cap at 0.85 for inference
                if score > best_score:
                    best_score = score
                    best_match = cnae_code

    if best_match and best_score >= 0.55:
        return {"code": best_match, "confidence": round(best_score, 2)}

    return None


def _build_sector_result(code: str, status: str, source: str, confidence: float, evidence: str) -> Dict:
    """Build the full sector result dict."""
    title = CNAE_TAXONOMY.get(code, "")

    # Derive hierarchy
    section = None
    division = None
    group = None
    level = None

    if '.' in code:
        div_code = code.split('.')[0]
        group_code = f"{div_code}.{code.split('.')[1][0]}" if len(code.split('.')[1]) >= 1 else None

        division = div_code
        if group_code:
            group = group_code

        # Find section for this division
        div_num = int(div_code) if div_code.isdigit() else 0
        section = _division_to_section(div_num)

        level = "class" if len(code.split('.')[1]) >= 2 else "group"
    elif len(code) == 2:
        division = code
        section = _division_to_section(int(code))
        level = "division"

    return {
        "cnae_code": code,
        "cnae_title": title,
        "cnae_section": section,
        "cnae_division": division,
        "cnae_group": group,
        "cnae_level": level,
        "sector_status": status,
        "sector_source": source,
        "sector_confidence": confidence,
        "sector_evidence_text": evidence[:500] if evidence else None,
        "sector_extraction_version": "v1"
    }


def _division_to_section(div: int) -> Optional[str]:
    """Map division number to CNAE section letter."""
    mapping = [
        (1, 3, "A"), (5, 9, "B"), (10, 33, "C"), (35, 35, "D"), (36, 39, "E"),
        (41, 43, "F"), (45, 47, "G"), (49, 53, "H"), (55, 56, "I"),
        (58, 60, "J"), (61, 63, "K"), (64, 66, "L"), (68, 68, "M"),
        (69, 75, "N"), (77, 82, "O"), (84, 84, "P"), (85, 85, "Q"),
        (86, 88, "R"), (90, 93, "S"), (94, 96, "T"), (97, 98, "U"), (99, 99, "V"),
    ]
    for low, high, letter in mapping:
        if low <= div <= high:
            return letter
    return None
