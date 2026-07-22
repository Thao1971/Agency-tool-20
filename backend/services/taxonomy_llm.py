"""Taxonomy LLM Assisted Mapping — Semantic Mapping Engine v2, Fase B.

Closes the automatic governance loop WITHOUT making the LLM the source of truth:

    Orphan / Weak mapping
        → GPT-5.2 (proposes up to 3 CNAEs)
        → taxonomy_suggestions (candidates)
        → MetaScore (5 weighted signals, GPT is only 10%)
        → taxonomy_mappings (auto-activated only if MetaScore >= 0.90)

NO embeddings / Knowledge Graph / vector DB. `semantic_similarity` is a lightweight
lexical proxy today, ready to be upgraded to embeddings later without touching the loop.
"""

import os
import re
import json
import uuid
import logging
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage
from database import db
from models import new_id, now_iso
from services.cnae_catalog import CNAE_DIVISIONS, resolve_cnae_to_section
from services.taxonomy_intelligence import (
    accept_llm_mapping, recompute_all_weights, get_orphans, get_inconsistencies,
    WEAK_CONFIDENCE_THRESHOLD,
)

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
MODEL_PROVIDER = "openai"
MODEL_NAME = "gpt-5.2"

# MetaScore weights (must sum to 1.0). GPT is intentionally a minority signal.
W_SEMANTIC = 0.40
W_FREQUENCY = 0.25
W_HISTORICAL = 0.15
W_SECTOR = 0.10
W_GPT = 0.10

AUTO_ACCEPT_METASCORE = 0.90
CANDIDATE_METASCORE = 0.70

_STOPWORDS = {"de", "del", "la", "el", "los", "las", "y", "o", "en", "para", "con",
              "por", "sus", "otros", "otras", "no", "se", "a", "u", "e", "su"}


# ──────────────────────────────────────────────────────────────────────────
# Lexical similarity (placeholder for future embeddings)
# ──────────────────────────────────────────────────────────────────────────

def _tokens(text: str) -> set:
    text = (text or "").lower()
    text = re.sub(r"[^a-záéíóúñü0-9 ]", " ", text)
    return {t for t in text.split() if t and t not in _STOPWORDS and len(t) > 2}


def _stems(tokens: set, n: int = 4) -> set:
    return {t[:n] for t in tokens}


def _semantic_similarity(source_label: str, cnae_label: str) -> float:
    """Lexical proxy (no embeddings): blends token Jaccard, morphological stem Jaccard
    and sequence ratio. Stem matching captures roots (pescados↔pesca) across vocabularies.
    Ready to be swapped for embeddings later without touching the loop."""
    a, b = _tokens(source_label), _tokens(cnae_label)
    if not (a or b):
        return 0.0
    jaccard = len(a & b) / len(a | b) if (a | b) else 0.0
    sa, sb = _stems(a), _stems(b)
    stem_jaccard = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
    ratio = SequenceMatcher(None, (source_label or "").lower(), (cnae_label or "").lower()).ratio()
    return round(0.35 * jaccard + 0.45 * stem_jaccard + 0.20 * ratio, 4)


# ──────────────────────────────────────────────────────────────────────────
# GPT proposal
# ──────────────────────────────────────────────────────────────────────────

def _cnae_catalog_text() -> str:
    return "\n".join(f"{code}: {info['label']}" for code, info in CNAE_DIVISIONS.items())


def _extract_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return None


async def _gpt_suggest(source_taxonomy: str, source_code: str, source_label: str) -> List[Dict]:
    """Ask GPT-5.2 for up to 3 candidate CNAE divisions. Returns [{cnae, confidence_score}]."""
    if not EMERGENT_KEY:
        logger.warning("EMERGENT_LLM_KEY missing — LLM suggestion skipped")
        return []

    prompt = f"""Mapea el siguiente código de taxonomía externa a divisiones CNAE-2009 españolas (2 dígitos).

Taxonomía: {source_taxonomy}
Código: {source_code}
Etiqueta del código: {source_label or "(sin etiqueta)"}

Catálogo de divisiones CNAE disponibles (código: descripción):
{_cnae_catalog_text()}

Devuelve SOLO JSON válido con hasta 3 divisiones CNAE más probables, ordenadas por probabilidad,
cada una con un confidence_score entre 0 y 1. Usa únicamente códigos del catálogo. Formato exacto:
{{"suggestions": [{{"cnae": "27", "confidence_score": 0.83}}, {{"cnae": "28", "confidence_score": 0.74}}]}}"""

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"taxonomy-suggest-{uuid.uuid4()}",
            system_message="Eres un motor de clasificación económica preciso. Devuelves solo JSON válido. Nunca inventas códigos fuera del catálogo.",
        ).with_model(MODEL_PROVIDER, MODEL_NAME)
        response = await chat.send_message(UserMessage(text=prompt))
        parsed = _extract_json(response) or {}
        out = []
        for s in (parsed.get("suggestions") or [])[:3]:
            cnae = str(s.get("cnae", "")).strip()
            if cnae in CNAE_DIVISIONS:
                conf = float(s.get("confidence_score", 0.0) or 0.0)
                out.append({"cnae": cnae, "confidence_score": max(0.0, min(conf, 1.0))})
        return out
    except Exception as e:
        logger.error(f"GPT taxonomy suggestion failed for {source_taxonomy}/{source_code}: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────────
# MetaScore signals
# ──────────────────────────────────────────────────────────────────────────

async def _build_context(source_taxonomy: str) -> Dict:
    """Pre-compute taxonomy-wide signals reused across suggestions of the same run."""
    actives = await db.taxonomy_mappings.find(
        {"source_taxonomy": source_taxonomy, "status": "active"},
        {"_id": 0, "source_code": 1, "cnae_code": 1},
    ).to_list(20000)

    # frequency: distinct source_codes that target each CNAE
    cnae_targets: Dict[str, set] = {}
    code_sections: Dict[str, set] = {}
    pairs = set()
    for m in actives:
        cnae_targets.setdefault(m["cnae_code"], set()).add(m["source_code"])
        sec = resolve_cnae_to_section(m["cnae_code"])
        if sec:
            code_sections.setdefault(m["source_code"], set()).add(sec)
        pairs.add((m["source_code"], m["cnae_code"]))

    max_freq = max((len(v) for v in cnae_targets.values()), default=1)
    return {"cnae_targets": cnae_targets, "max_freq": max_freq,
            "code_sections": code_sections, "pairs": pairs}


def _frequency_score(ctx: Dict, cnae: str) -> float:
    freq = len(ctx["cnae_targets"].get(cnae, set()))
    return round(freq / ctx["max_freq"], 4) if ctx["max_freq"] else 0.0


def _historical_score(ctx: Dict, source_code: str, cnae: str) -> float:
    return 1.0 if (source_code, cnae) in ctx["pairs"] else 0.5


def _sector_consistency_score(ctx: Dict, source_code: str, cnae: str) -> float:
    """Fraction of numeric neighbors (±3) whose mapped CNAE shares the suggested section."""
    target_sec = resolve_cnae_to_section(cnae)
    if not target_sec or not source_code.isdigit():
        return 0.5
    base = int(source_code)
    neighbor_secs = []
    for delta in (-3, -2, -1, 1, 2, 3):
        nb = f"{base + delta:02d}"
        for sec in ctx["code_sections"].get(nb, set()):
            neighbor_secs.append(sec)
    if not neighbor_secs:
        return 0.5
    return round(sum(1 for s in neighbor_secs if s == target_sec) / len(neighbor_secs), 4)


def _metascore(semantic: float, frequency: float, historical: float,
               sector: float, gpt_conf: float) -> float:
    return round(
        W_SEMANTIC * semantic + W_FREQUENCY * frequency + W_HISTORICAL * historical
        + W_SECTOR * sector + W_GPT * gpt_conf, 4
    )


# ──────────────────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────────────────

async def suggest_for_code(source_taxonomy: str, source_code: str, source_label: str,
                           target_type: str, ctx: Dict) -> List[Dict]:
    """Generate, score and persist suggestions for one source code. Returns stored suggestion docs."""
    gpt_suggestions = await _gpt_suggest(source_taxonomy, source_code, source_label)
    now = now_iso()
    stored = []

    for g in gpt_suggestions:
        cnae = g["cnae"]
        cnae_label = CNAE_DIVISIONS.get(cnae, {}).get("label", "")
        semantic = _semantic_similarity(source_label, cnae_label)
        frequency = _frequency_score(ctx, cnae)
        historical = _historical_score(ctx, source_code, cnae)
        sector = _sector_consistency_score(ctx, source_code, cnae)
        gpt_conf = g["confidence_score"]
        meta = _metascore(semantic, frequency, historical, sector, gpt_conf)

        if meta >= AUTO_ACCEPT_METASCORE:
            status = "accepted"
        elif meta >= CANDIDATE_METASCORE:
            status = "candidate"
        else:
            status = "rejected"

        doc = {
            "suggestion_id": new_id(),
            "source_taxonomy": source_taxonomy,
            "source_code": source_code,
            "source_label": source_label or "",
            "suggested_cnae": cnae,
            "suggested_label": cnae_label,
            "confidence_score": round(gpt_conf, 4),
            "origin": "llm",
            "llm_model": MODEL_NAME,
            "target_type": target_type,
            "semantic_similarity": semantic,
            "frequency_score": frequency,
            "historical_score": historical,
            "sector_consistency_score": sector,
            "gpt_confidence_score": round(gpt_conf, 4),
            "metascore": meta,
            "status": status,
            "created_at": now,
        }
        await db.taxonomy_suggestions.update_one(
            {"source_taxonomy": source_taxonomy, "source_code": source_code, "suggested_cnae": cnae},
            {"$set": {k: v for k, v in doc.items() if k not in ("suggestion_id", "created_at")},
             "$setOnInsert": {"suggestion_id": doc["suggestion_id"], "created_at": now}},
            upsert=True,
        )

        if status == "accepted":
            await accept_llm_mapping(source_taxonomy, source_code, source_label, cnae, gpt_conf)

        stored.append(doc)

    return stored


async def run_suggestions(scope: str = "all", limit: int = 20) -> Dict:
    """Generate LLM suggestions for orphans and/or weak mappings.

    scope: "orphans" | "weak" | "all"
    """
    targets = []  # (taxonomy, code, label, target_type)

    if scope in ("orphans", "all"):
        orphan_data = await get_orphans(limit=10000)
        # prioritize codes that actually carry data (real signal loss) first
        for o in orphan_data["orphans"]:
            targets.append((o["taxonomy"], o["code"], o.get("label", ""), "orphan"))

    if scope in ("weak", "all"):
        incons = await get_inconsistencies(limit=10000)
        seen = set()
        for w in incons["weak_mappings"]["items"]:
            key = (w["taxonomy"], w["code"])
            if key not in seen:
                seen.add(key)
                targets.append((w["taxonomy"], w["code"], w.get("label", ""), "weak"))

    targets = targets[:limit]

    ctx_cache: Dict[str, Dict] = {}
    auto_accepted = candidates = rejected = 0
    processed = 0

    for tax, code, label, ttype in targets:
        if tax not in ctx_cache:
            ctx_cache[tax] = await _build_context(tax)
        stored = await suggest_for_code(tax, code, label, ttype, ctx_cache[tax])
        processed += 1
        for s in stored:
            if s["status"] == "accepted":
                auto_accepted += 1
            elif s["status"] == "candidate":
                candidates += 1
            else:
                rejected += 1

    if auto_accepted:
        await recompute_all_weights()

    return {
        "scope": scope,
        "codes_processed": processed,
        "suggestions_generated": auto_accepted + candidates + rejected,
        "auto_accepted": auto_accepted,
        "candidates": candidates,
        "rejected": rejected,
        "generated_at": now_iso(),
    }


# ──────────────────────────────────────────────────────────────────────────
# Reads
# ──────────────────────────────────────────────────────────────────────────

async def list_suggestions(status: Optional[str] = None, target_type: Optional[str] = None,
                           taxonomy: Optional[str] = None, limit: int = 500) -> List[Dict]:
    q = {}
    if status:
        q["status"] = status
    if target_type:
        q["target_type"] = target_type
    if taxonomy:
        q["source_taxonomy"] = taxonomy
    return await db.taxonomy_suggestions.find(q, {"_id": 0}).sort("metascore", -1).limit(limit).to_list(limit)


async def suggestions_stats() -> Dict:
    accepted = await db.taxonomy_suggestions.count_documents({"status": "accepted"})
    candidate = await db.taxonomy_suggestions.count_documents({"status": "candidate"})
    rejected = await db.taxonomy_suggestions.count_documents({"status": "rejected"})
    agg = await db.taxonomy_suggestions.aggregate([
        {"$match": {"status": {"$in": ["accepted", "candidate"]}}},
        {"$group": {"_id": None, "avg": {"$avg": "$metascore"}}},
    ]).to_list(1)
    avg_meta = round(agg[0]["avg"], 4) if agg else 0.0
    return {
        "llm_candidates": accepted + candidate,
        "auto_accepted": accepted,
        "pending_candidates": candidate,
        "rejected": rejected,
        "average_metascore": avg_meta,
    }
