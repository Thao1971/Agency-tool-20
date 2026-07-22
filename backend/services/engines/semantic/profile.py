"""Rules-based Company Semantic Profile builder (D-S1: rules first; D-S4: 14 dimensions
always present with explicit status). AI enrichment is optional and traceable (ai_extractor).

Strict Master sourcing: every dimension is derived ONLY from the Master record
(+ optionally Financial/Signal). No access to raw/normalized sources.
"""

import re
import unicodedata
from typing import Dict, List, Optional

PROFILE_VERSION = "semantic-profile-v1"

DIMENSIONS = [
    "economic_activity", "capabilities", "products_services", "technologies",
    "customers", "suppliers", "sectors", "subsectors", "value_chain",
    "value_proposition", "competitive_advantages", "positioning",
    "economic_context", "semantic_relationships",
]

# CNAE section → value-chain position (rules, explainable)
_SECTION_VALUE_CHAIN = {
    "A": "upstream", "B": "upstream", "C": "midstream", "F": "midstream",
    "G": "downstream", "H": "midstream", "I": "downstream", "J": "midstream",
    "K": "downstream", "M": "downstream", "Q": "downstream", "L": "downstream",
}

# small explainable lexicon for technologies/capabilities extracted from objeto_social
_TECH_LEXICON = [
    "software", "cloud", "saas", "ecommerce", "logistica", "transporte", "fabricacion",
    "consultoria", "ingenieria", "construccion", "distribucion", "marketing", "digital",
    "energia", "renovable", "automatizacion", "datos", "inteligencia artificial",
    "biotecnologia", "farmaceutica", "alimentacion", "hosteleria", "inmobiliaria",
]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _dim(value, status, evidence, method="rules", confidence=0.0, **extra):
    return {"value": value, "status": status, "evidence": evidence,
            "method": method, "confidence": round(confidence, 3), **extra}


def _split_activities(objeto: str) -> List[str]:
    parts = re.split(r"[.;,\n]| y | e ", objeto or "")
    return [p.strip() for p in parts if len(p.strip()) > 4][:8]


def build_rules_profile(master: Dict, financial: Optional[Dict] = None,
                        signal: Optional[Dict] = None) -> Dict:
    cls = master.get("classification") or {}
    objeto = master.get("objeto_social") or ""
    objeto_n = _norm(objeto)
    cnae_desc = cls.get("cnae_description")
    section = cls.get("cnae_section")
    size = master.get("size") or {}
    employees = size.get("employees_total")

    has_obj = bool(objeto.strip())
    has_cnae = bool(cls.get("cnae_code"))

    prof: Dict = {}

    # economic_activity
    if has_cnae or has_obj:
        val = cnae_desc or (objeto[:200] if has_obj else None)
        prof["economic_activity"] = _dim(
            val, "available" if (has_cnae and has_obj) else "partial",
            [e for e, c in (("objeto_social", has_obj), ("cnae_code", has_cnae)) if c],
            confidence=0.8 if (has_cnae and has_obj) else 0.5)
    else:
        prof["economic_activity"] = _dim(None, "unavailable", [], confidence=0.0)

    # capabilities (rules: derived from activity phrases)
    acts = _split_activities(objeto) if has_obj else []
    prof["capabilities"] = ([_dim(a, "available", ["objeto_social"], confidence=0.4) for a in acts]
                            if acts else [_dim(None, "unavailable", [], confidence=0.0)])

    # products_services (rules: from cnae_description + activities)
    ps = []
    if cnae_desc:
        ps.append(_dim(cnae_desc, "available", ["cnae_description"], confidence=0.6))
    for a in acts[:3]:
        ps.append(_dim(a, "partial", ["objeto_social"], confidence=0.35))
    prof["products_services"] = ps or [_dim(None, "unavailable", [], confidence=0.0)]

    # technologies (rules: lexicon match over objeto_social)
    techs = [t for t in _TECH_LEXICON if t in objeto_n]
    prof["technologies"] = ([_dim(t, "available", ["objeto_social"], confidence=0.4) for t in techs]
                            if techs else [_dim(None, "unavailable", [], confidence=0.0)])

    # customers / suppliers — not in Master → explicit unavailable (no invention, D-S1)
    prof["customers"] = [_dim(None, "unavailable", [], confidence=0.0,
                              reason="no customer data in Master Layer")]
    prof["suppliers"] = [_dim(None, "unavailable", [], confidence=0.0,
                              reason="no supplier data in Master Layer")]

    # sectors / subsectors (rules from CNAE)
    if section:
        prof["sectors"] = [_dim(section, "available", ["cnae_section"], confidence=0.9,
                                cnae=cls.get("cnae_code"))]
        prof["subsectors"] = [_dim(cls.get("cnae_division") or cls.get("cnae_description"),
                                   "available" if cls.get("cnae_division") else "partial",
                                   ["cnae_division"], confidence=0.7)]
    else:
        prof["sectors"] = [_dim(None, "unavailable", [], confidence=0.0)]
        prof["subsectors"] = [_dim(None, "unavailable", [], confidence=0.0)]

    # value_chain (rules from section)
    if section and section in _SECTION_VALUE_CHAIN:
        prof["value_chain"] = _dim(None, "available", ["cnae_section"], confidence=0.6,
                                   position=_SECTION_VALUE_CHAIN[section])
    else:
        prof["value_chain"] = _dim(None, "unavailable", [], confidence=0.0, position=None)

    # value_proposition (rules fallback; AI enrich later)
    if cnae_desc or has_obj:
        vp = f"Empresa dedicada a {cnae_desc or acts[0] if acts else 'su actividad'}".strip()
        prof["value_proposition"] = _dim(vp, "partial", ["cnae_description", "objeto_social"],
                                         method="rules", confidence=0.3)
    else:
        prof["value_proposition"] = _dim(None, "unavailable", [], confidence=0.0)

    # competitive_advantages — needs evidence; from financials if strong margins
    ca = []
    if financial and financial.get("has_financials"):
        kpis = financial.get("kpis") or {}
        if (kpis.get("ebitda_margin") or 0) > 0.15:
            ca.append(_dim("Rentabilidad operativa superior (margen EBITDA >15%)", "available",
                           ["financial-intelligence-v1"], confidence=0.5))
    prof["competitive_advantages"] = ca or [_dim(None, "unavailable", [], confidence=0.0,
                                                  reason="no evidence in Master/Financial")]

    # positioning (rules: size band + sector)
    if employees is not None and section:
        band = "grande" if employees >= 250 else ("mediana" if employees >= 50 else "pequeña")
        prof["positioning"] = _dim(f"Empresa {band} del sector {section}", "available",
                                   ["size.employees_total", "cnae_section"], confidence=0.6,
                                   segment=band)
    else:
        prof["positioning"] = _dim(None, "partial" if section else "unavailable",
                                   ["cnae_section"] if section else [], confidence=0.2 if section else 0.0,
                                   segment=None)

    # economic_context (from Financial + Signal, optional)
    ctx_evidence, ctx_parts = [], []
    if financial and financial.get("has_financials"):
        ctx_evidence.append("financial-intelligence-v1")
        ev = (financial.get("evolution") or {}).get("trend")
        if ev:
            ctx_parts.append(f"tendencia financiera: {ev}")
    if signal and signal.get("counts_by_category"):
        ctx_evidence.append("signal-intelligence-v1")
        ctx_parts.append(f"señales activas: {sum(signal['counts_by_category'].values())}")
    prof["economic_context"] = _dim("; ".join(ctx_parts) or None,
                                    "available" if ctx_parts else "unavailable",
                                    ctx_evidence, confidence=0.5 if ctx_parts else 0.0)

    # semantic_relationships — computed on-demand (D-S5); empty here unless injected
    prof["semantic_relationships"] = []

    return prof


def embedding_text(profile: Dict) -> str:
    """Build the text the embedding is derived FROM (subset of the profile)."""
    parts: List[str] = []

    def collect(field):
        v = profile.get(field)
        if isinstance(v, list):
            for it in v:
                if it.get("value"):
                    parts.append(str(it["value"]))
        elif isinstance(v, dict) and v.get("value"):
            parts.append(str(v["value"]))

    for f in ("economic_activity", "capabilities", "products_services",
              "technologies", "sectors", "subsectors", "value_proposition", "positioning"):
        collect(f)
    return " ".join(parts)


EMBEDDING_SOURCES = ["economic_activity", "capabilities", "products_services",
                     "technologies", "sectors", "subsectors", "value_proposition", "positioning"]


def coverage(profile: Dict) -> Dict:
    by_status = {"available": 0, "partial": 0, "unavailable": 0}
    for field in DIMENSIONS:
        v = profile.get(field)
        if field == "semantic_relationships":
            st = "available" if v else "unavailable"
        elif isinstance(v, list):
            sts = [it.get("status") for it in v]
            st = "available" if "available" in sts else ("partial" if "partial" in sts else "unavailable")
        elif isinstance(v, dict):
            st = v.get("status", "unavailable")
        else:
            st = "unavailable"
        by_status[st] = by_status.get(st, 0) + 1
    present = by_status["available"] + by_status["partial"]
    score = round(100 * (by_status["available"] + 0.5 * by_status["partial"]) / len(DIMENSIONS))
    return {"score": score, "fields_present": present, "fields_total": len(DIMENSIONS),
            "by_status": by_status}
