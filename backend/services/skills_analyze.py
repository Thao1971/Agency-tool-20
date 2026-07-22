"""Skill: Analyze / Enrich Company (REQ-001 evolution).

Public Analyze contract. Internal-only evolution — reuses the canonical master record,
Value's comparables engine and Recommend's size proximity. No new engines, no new sources.
Narrative via Claude (Emergent LLM Key). Boundary First: Agency Tool enriches, arroba renders.
"""

import os
import json
import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple

from emergentintegrations.llm.chat import LlmChat, UserMessage
from database import db
from services.data_layer.accessors import (
    name_of, sector_of, category_of, cnae_section_of, financials_latest, financials_history,
)
from services.skills_valuation import _comparables
from services.skills_recommend import _size_proximity
from services.analyze_cache import (
    ensure_indexes, data_version, cache_key, get_cached, set_cached,
    record_metric, estimate_tokens,
)

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
NARRATIVE_MODEL = "claude-sonnet-4-6"


def _safe_div(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return round(a / b, 4)
    except (TypeError, ZeroDivisionError):
        return None


def _financial_summary(fin: Optional[Dict]) -> Optional[Dict]:
    if not fin:
        return None
    return {k: fin.get(k) for k in
            ["revenue", "ebitda", "ebitda_margin", "net_income", "equity", "employees", "year"]}


def _growth(history: List[Dict]) -> Dict:
    if len(history) < 2:
        return {"revenue_growth": None, "ebitda_growth": None}
    # history is sorted by year desc
    y0, y1 = history[0], history[1]
    def g(cur, prev):
        if cur is None or prev in (None, 0):
            return None
        return round((cur - prev) / abs(prev), 4)
    return {
        "revenue_growth": g(y0.get("revenue"), y1.get("revenue")),
        "ebitda_growth": g(y0.get("ebitda"), y1.get("ebitda")),
    }


def _ratios(fin: Optional[Dict]) -> Dict:
    if not fin:
        return {"ebitda_margin": None, "revenue_per_employee": None,
                "ebitda_per_employee": None, "debt_ratio": None}
    revenue, ebitda = fin.get("revenue"), fin.get("ebitda")
    employees, equity, assets = fin.get("employees"), fin.get("equity"), fin.get("total_assets")
    return {
        "ebitda_margin": fin.get("ebitda_margin") or _safe_div(ebitda, revenue),
        "revenue_per_employee": _safe_div(revenue, employees),
        "ebitda_per_employee": _safe_div(ebitda, employees),
        "debt_ratio": _safe_div((assets - equity), assets) if (assets and equity is not None) else None,
    }


async def _peers(doc: Dict, category: Optional[str], fin: Optional[Dict]) -> List[Dict]:
    """Reuse Value's comparables engine; rank via Recommend's size proximity."""
    comps = await _comparables(doc, category, limit=8)
    seed_emp = (fin or {}).get("employees")
    seed_rev = (fin or {}).get("revenue")
    peers = []
    for c in comps:
        prox, _label = _size_proximity(seed_emp, seed_rev,
                                       {"employees": None, "revenue": c.get("revenue")})
        peers.append({
            "master_company_id": c["master_company_id"],
            "legal_name": c["name"],
            "sector": c["sector"],
            "score": round(0.6 + 0.4 * prox, 4),
        })
    peers.sort(key=lambda p: -p["score"])
    return peers[:5]


def _confidence(doc: Dict, classification: Dict, fin: Optional[Dict]) -> Dict:
    identity = 0.9 if (doc.get("cif") and name_of(doc)) else 0.4
    if classification.get("cnae_code"):
        classification_c = 0.9
    elif category_of(doc):
        classification_c = 0.6
    else:
        classification_c = 0.2
    if fin and fin.get("ebitda"):
        financials_c = 0.9
    elif fin and fin.get("revenue"):
        financials_c = 0.6
    else:
        financials_c = 0.2
    overall = round(doc.get("confidence_score") or (identity + classification_c + financials_c) / 3, 2)
    return {"identity": identity, "classification": classification_c,
            "financials": financials_c, "overall": overall}


def _extract_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    if text:
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None


async def _narrative(doc: Dict, fin: Optional[Dict], growth: Dict, ratios: Dict,
                     sector: Optional[str]) -> Tuple[Dict, Dict]:
    """Returns (narrative, meta). meta = {tokens, claude_error, retries}."""
    empty = {"summary": "", "key_points": [], "risks": [], "opportunities": []}
    meta = {"tokens": 0, "claude_error": False, "retries": 0}
    if not EMERGENT_KEY:
        return empty, meta
    name = name_of(doc)
    facts = {
        "name": name, "sector": sector, "financials": fin,
        "growth": growth, "ratios": ratios,
    }
    prompt = (
        "Analiza esta compañía española y devuelve SOLO JSON válido con este formato exacto:\n"
        '{"summary": "2-3 frases", "key_points": ["..."], "risks": ["..."], "opportunities": ["..."]}\n\n'
        f"Datos del master record (no inventes nada fuera de estos datos):\n{json.dumps(facts, ensure_ascii=False, default=str)}"
    )
    meta["tokens"] += estimate_tokens(prompt)
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            chat = LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"analyze-{uuid.uuid4()}",
                system_message="Eres un analista financiero conciso. Devuelves solo JSON válido en español. No inventas datos.",
            ).with_model("anthropic", NARRATIVE_MODEL)
            resp = await chat.send_message(UserMessage(text=prompt))
            meta["tokens"] += estimate_tokens(resp)
            parsed = _extract_json(resp) or {}
            return {
                "summary": parsed.get("summary", ""),
                "key_points": parsed.get("key_points", []) or [],
                "risks": parsed.get("risks", []) or [],
                "opportunities": parsed.get("opportunities", []) or [],
            }, meta
        except Exception as e:
            logger.error(f"Analyze narrative failed (attempt {attempt + 1}): {e}")
            if attempt + 1 < max_attempts:
                meta["retries"] += 1
                continue
            meta["claude_error"] = True
            return empty, meta
    return empty, meta


async def enrich_company_analyze(master_company_id: str, context: Dict) -> Optional[Dict]:
    t0 = time.time()
    doc = await db.companies_master.find_one({"master_company_id": master_company_id}, {"_id": 0})
    if not doc:
        return None

    include_narrative = context.get("include_narrative", True) if isinstance(context, dict) else True

    await ensure_indexes()
    dv = data_version(doc)
    key = cache_key(master_company_id, include_narrative, dv)
    cached = await get_cached(key)
    if cached is not None:
        await record_metric(master_company_id=master_company_id, include_narrative=include_narrative,
                            cache_hit=True, latency_ms=(time.time() - t0) * 1000)
        return cached

    classification = doc.get("classification") or {}
    sector = sector_of(doc)
    category = category_of(doc)
    fin = financials_latest(doc)
    history = financials_history(doc)

    growth = _growth(history)
    ratios = _ratios(fin)
    peers = await _peers(doc, category, fin)

    from services.knowledge_graph import relationships_for
    relationships = await relationships_for(master_company_id, limit=10)

    if include_narrative:
        narrative, nmeta = await _narrative(doc, fin, growth, ratios, sector)
    else:
        narrative = {"summary": "", "key_points": [], "risks": [], "opportunities": []}
        nmeta = {"tokens": 0, "claude_error": False, "retries": 0}

    base_lineage = doc.get("lineage") or {}
    result = {
        "master_company_id": master_company_id,
        "legal_name": name_of(doc),
        "sector": sector,
        "category": category,
        "cnae_code": classification.get("cnae_code"),
        "cnae_section": cnae_section_of(doc),
        "financial_summary": _financial_summary(fin),
        "growth": growth,
        "ratios": ratios,
        "peers": peers,
        "ownership": {"shareholders": [], "ultimate_parent": None, "group_name": None},
        "relationships": relationships,
        "signals": doc.get("signals") or [],
        "narrative": narrative,
        "confidence": _confidence(doc, classification, fin),
        "lineage": {
            "identity": base_lineage.get("identity", "unknown"),
            "classification": base_lineage.get("classification", "none"),
            "financials": base_lineage.get("financials", "none"),
            "narrative": "ai_generated" if narrative.get("summary") else "none",
        },
    }
    await set_cached(key, result)
    await record_metric(master_company_id=master_company_id, include_narrative=include_narrative,
                        cache_hit=False, latency_ms=(time.time() - t0) * 1000,
                        tokens=nmeta["tokens"], claude_error=nmeta["claude_error"],
                        retries=nmeta["retries"])
    return result
