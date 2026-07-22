"""Classification Agent — hybrid rules + LLM for editorial section assignment."""

import re
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Keyword rules (primary layer) ──
SECTION_RULES = {
    "cifras_resultados": [
        r"factur[aó]", r"ingres(?:os|a)", r"beneficio", r"pérdidas?", r"EBITDA", r"margen",
        r"crec(?:e|ió|imiento)", r"resultado(?:s)?", r"previsi(?:ón|ones)", r"revenue",
        r"Q[1-4]\s*20\d{2}", r"semestre", r"trimestre", r"cifra(?:s)?", r"baj[aó]", r"sub[eió]",
        r"millones", r"rentabilidad", r"reduce pérdidas",
    ],
    "ma_vc_pe_alianzas": [
        r"compr[aó]", r"adquir", r"adquisici[oó]n", r"vend[eió]", r"fusi[oó]n", r"absorci[oó]n",
        r"inversi[oó]n", r"ronda(?:\s+de)?", r"alianza", r"partnership", r"joint\s*venture",
        r"capital\s*riesgo", r"private\s*equity", r"venture\s*capital", r"M&A", r"OPA",
        r"desinversi[oó]n", r"escisi[oó]n", r"participa", r"accionari",
    ],
    "nombramientos_reconocimientos": [
        r"nombr[aó]", r"incorpor[aó]", r"(?:nuevo|nueva)\s+(?:CEO|director|presidente|CMO|CTO|COO)",
        r"presidente", r"consejero", r"nombramiento", r"reconocimiento",
        r"premi(?:o|ada)", r"galardon", r"ranking", r"mejor\s+agencia", r"award",
        r"top\s+\d+", r"El\s+Sol", r"Cannes", r"Eficacia", r"Laus",
    ],
    "podcasts_entrevistas": [
        r"podcast", r"episodio", r"entrevista", r"conversaci[oó]n", r"escuch",
        r"audio", r"spotify", r"apple\s*podcast", r"ivoox",
    ],
    "eventos": [
        r"summit", r"festival", r"congreso", r"jornada", r"foro", r"evento",
        r"award\s*ceremony", r"gala", r"conferencia", r"hackathon", r"bootcamp",
        r"AEVEA", r"MWC", r"Inspirational", r"FOA",
    ],
    "indies": [
        r"lanz[aó]", r"nac[eió]", r"nueva\s+boutique", r"nuevo\s+estudio", r"rebranding",
        r"independiente", r"indie", r"emprendedor", r"startup\s+(?:de\s+)?(?:publicidad|marketing|comunicaci)",
        r"abre\s+oficina", r"nueva\s+marca",
    ],
}

# Action detection
ACTION_PATTERNS = [
    (r"compr[aó]|adquir", "compra"),
    (r"adquisici[oó]n", "adquiere"),
    (r"lanz[aó]|presenta", "lanza"),
    (r"nombr[aó]|incorpor[aó]", "nombra"),
    (r"gan[aó]|premi(?:o|ada)|galardon", "gana"),
    (r"abre|inaugur", "abre"),
    (r"factur[aó]|ingres", "factura"),
    (r"crec(?:e|ió)|subi[oó]", "crece"),
    (r"reduce\s+p[eé]rdidas", "reduce pérdidas"),
    (r"alianza|acuerdo|partnership", "firma alianza"),
    (r"inversi[oó]n|ronda|capta", "capta inversión"),
    (r"vend[eió]|desinv", "vende"),
    (r"fusi[oó]n|absorci", "fusiona"),
    (r"cierra|clausura", "cierra"),
    (r"expan|internacion", "se expande"),
]

SIGNAL_TYPE_MAP = {
    "cifras_resultados": "result",
    "ma_vc_pe_alianzas": "acquisition",
    "nombramientos_reconocimientos": "appointment",
    "podcasts_entrevistas": "other",
    "eventos": "event",
    "indies": "launch",
    "noticias_semana": "other",
}


def classify_item(title: str, text: str = "") -> Dict:
    """Classify an editorial item using keyword rules. Returns section, action, signal type."""
    combined = f"{title} {text}".strip()

    # Score each section
    scores = {}
    evidence = {}
    for section, patterns in SECTION_RULES.items():
        score = 0
        matched = []
        for pat in patterns:
            if re.search(pat, combined, re.IGNORECASE):
                score += 1
                matched.append(pat)
        if score > 0:
            scores[section] = score
            evidence[section] = matched[:3]

    # Primary section = highest score
    if scores:
        primary = max(scores, key=scores.get)
        secondaries = [s for s, sc in sorted(scores.items(), key=lambda x: -x[1]) if s != primary and sc > 0][:2]
    else:
        primary = "noticias_semana"
        secondaries = []

    # Detect action
    action = _detect_action(combined)
    signal = SIGNAL_TYPE_MAP.get(primary, "other")

    return {
        "section_primary": primary,
        "section_secondary": secondaries,
        "signal_type": signal,
        "action_detected": action,
        "classification_method": "rules",
        "classification_evidence": evidence.get(primary, []),
        "confidence_score": min(scores.get(primary, 0) / 3.0, 1.0) if scores else 0.2,
    }


def _detect_action(text: str) -> Optional[str]:
    for pattern, action in ACTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return action
    return None


async def classify_with_llm(title: str, text: str, locale: str = "es") -> Dict:
    """LLM-enhanced classification when rules are uncertain."""
    import os, json, uuid
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
    sections_list = ", ".join([
        "cifras_resultados", "indies", "noticias_semana",
        "ma_vc_pe_alianzas", "podcasts_entrevistas",
        "nombramientos_reconocimientos", "eventos"
    ])

    prompt = f"""Classify this editorial item from a marketing/advertising industry newsletter.

Title: {title}
Text: {text[:500]}

Available sections: {sections_list}

Return ONLY valid JSON:
{{
  "section_primary": "one of the sections above",
  "signal_type": "result|acquisition|appointment|launch|award|partnership|fundraise|event|other",
  "action_detected": "main verb/action in Spanish (compra, lanza, nombra, etc.) or null",
  "confidence_score": 0.0 to 1.0
}}"""

    try:
        chat = LlmChat(api_key=EMERGENT_KEY, session_id=f"editorial-{uuid.uuid4()}", system_message="Editorial classifier. JSON only.")
        chat.with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=prompt))
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(response[start:end])
            result["classification_method"] = "llm"
            return result
    except Exception as e:
        logger.warning(f"LLM classification failed: {e}")

    return {"section_primary": "noticias_semana", "classification_method": "llm_failed", "confidence_score": 0.1}
