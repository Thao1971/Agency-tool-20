"""Semantic Intelligence Engine — orchestrator (semantic-intelligence-v1).

Product = Company Semantic Profile (canonical, technology-agnostic, explainable).
Embeddings/similarity/search are DERIVED tools. Strict Master sourcing. Boundary First.
"""

import asyncio
import hashlib
import json
from typing import Dict, List, Optional

from database import db
from models import now_iso
from services.engines.financial import engine as fin_engine
from services.engines.signal import engine as sig_engine
from services.engines.semantic import profile as PB
from services.engines.semantic import embeddings as E
from services.engines.semantic import ai_extractor as AI
from services.engines.semantic import vector_search as VS
from services.engines.semantic import persistence as P

ENGINE_VERSION = "semantic-intelligence-v1"


def _checksum(profile: Dict) -> str:
    return hashlib.sha256(json.dumps(profile, sort_keys=True, default=str).encode()).hexdigest()


async def _load_master(identifier: str) -> Optional[Dict]:
    return await db.master_companies.find_one(
        {"$or": [{"master_id": identifier}, {"cif_normalized": identifier}]}, {"_id": 0})


async def _apply_ai(sem_profile: Dict, master: Dict) -> Optional[str]:
    """Optional, traceable AI enrichment (D-S1). Returns ai_model or None."""
    cls = master.get("classification") or {}
    data = await AI.extract(master.get("objeto_social") or "",
                            cls.get("cnae_description") or "",
                            (master.get("identity") or {}).get("legal_name") or "")
    if not data:
        return None
    model = data.get("ai_model")
    if data.get("capabilities"):
        sem_profile["capabilities"] = [PB._dim(c, "available", ["objeto_social"],
                                               method="ai", confidence=0.6) for c in data["capabilities"]]
    if data.get("technologies"):
        sem_profile["technologies"] = [PB._dim(t, "available", ["objeto_social"],
                                               method="ai", confidence=0.6) for t in data["technologies"]]
    if data.get("value_proposition"):
        sem_profile["value_proposition"] = PB._dim(data["value_proposition"], "available",
                                                   ["objeto_social"], method="ai", confidence=0.6)
    return model, data.get("summary")


async def build_profile(identifier: str, enrich: bool = False,
                        with_relationships: bool = False, persist: bool = True) -> Optional[Dict]:
    master = await _load_master(identifier)
    if not master:
        return None
    financial = await fin_engine.analyze(identifier)
    signal = None
    try:
        signal = await sig_engine.analyze(identifier, persist=False)
    except Exception:
        signal = None

    sem_profile = PB.build_rules_profile(master, financial, signal)
    ai_used, ai_model, summary_text, summary_method = False, None, None, "rules"

    if enrich:
        res = await _apply_ai(sem_profile, master)
        if res:
            ai_used, (ai_model, summary_text) = True, res
            summary_method = "ai"

    if not summary_text:
        ea = sem_profile["economic_activity"].get("value")
        summary_text = f"{(master.get('identity') or {}).get('legal_name')}: {ea}" if ea else None

    # embedding (derived artifact)
    emb_text = PB.embedding_text(sem_profile)
    emb = None
    if emb_text.strip():
        e = await asyncio.to_thread(E.get_provider().embed, emb_text)
        emb = {"embedding_version": e["embedding_version"], "provider": e["provider"],
               "model": e["model"], "dimension": e["dimension"], "vector": e["vector"],
               "sources": PB.EMBEDDING_SOURCES, "generated_at": now_iso()}

    profile_only = {k: sem_profile[k] for k in PB.DIMENSIONS if k != "semantic_relationships"}
    checksum = _checksum(profile_only)
    if emb is not None:
        emb["profile_checksum"] = checksum

    section = (master.get("classification") or {}).get("cnae_section")
    if persist and emb is not None:
        await P.save(master["master_id"], master["cif_normalized"], section,
                     {"identity_name": (master.get("identity") or {}).get("legal_name"),
                      "embedding": emb, "profile_checksum": checksum,
                      "coverage": PB.coverage(sem_profile)})

    if with_relationships and emb is not None:
        rels = await VS.top_k(emb["vector"], section, master["master_id"], k=5)
        sem_profile["semantic_relationships"] = [
            {"master_id": r["master_id"], "type": "similar", "score": r["score"],
             "basis": "embedding"} for r in rels if r["score"] > 0]

    coverage = PB.coverage(sem_profile)
    confidences = []
    for f in PB.DIMENSIONS:
        v = sem_profile.get(f)
        if isinstance(v, dict):
            confidences.append(v.get("confidence", 0))
        elif isinstance(v, list):
            confidences += [it.get("confidence", 0) for it in v if isinstance(it, dict)]
    overall = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

    return {
        "master_id": master["master_id"], "cif_normalized": master["cif_normalized"],
        "profile_version": PB.PROFILE_VERSION,
        "identity": {"name": (master.get("identity") or {}).get("legal_name"),
                     "cnae_code": (master.get("classification") or {}).get("cnae_code"),
                     "cnae_section": section},
        "semantic_profile": sem_profile,
        "semantic_summary": {"text": summary_text, "method": summary_method,
                             "model": ai_model, "confidence": 0.5 if summary_text else 0.0},
        "coverage": coverage,
        "embedding": {k: v for k, v in (emb or {}).items() if k != "vector"} if emb else None,
        "lineage": {"master_source_version": (master.get("sources") or [{}])[-1].get("source_version"),
                    "engines_used": [e for e, ok in (("financial-intelligence-v1", bool(financial)),
                                                     ("signal-intelligence-v1", bool(signal))) if ok],
                    "ai_used": ai_used, "ai_model": ai_model},
        "engine_version": ENGINE_VERSION, "generated_at": now_iso(), "confidence": overall,
    }


async def get_embedding(identifier: str) -> Optional[Dict]:
    master = await _load_master(identifier)
    if not master:
        return None
    stored = await P.get(master["master_id"])
    if stored and stored.get("embedding"):
        return {"master_id": master["master_id"], "embedding": stored["embedding"],
                "profile_checksum": stored.get("profile_checksum"),
                "engine_version": ENGINE_VERSION}
    prof = await build_profile(identifier)
    if not prof or not prof.get("embedding"):
        return {"master_id": master["master_id"], "embedding": None,
                "engine_version": ENGINE_VERSION}
    stored = await P.get(master["master_id"])
    return {"master_id": master["master_id"], "embedding": stored.get("embedding"),
            "profile_checksum": stored.get("profile_checksum"), "engine_version": ENGINE_VERSION}


async def similar(identifier: str, limit: int = 10, same_section: bool = True) -> Optional[Dict]:
    master = await _load_master(identifier)
    if not master:
        return None
    emb = await get_embedding(identifier)
    vec = (emb.get("embedding") or {}).get("vector") if emb else None
    if not vec:
        return {"master_id": master["master_id"], "count": 0, "similar": [],
                "note": "no embedding (insufficient semantic data)", "engine_version": ENGINE_VERSION}
    section = (master.get("classification") or {}).get("cnae_section") if same_section else None
    rows = await VS.top_k(vec, section, master["master_id"], k=limit)
    return {"master_id": master["master_id"], "count": len(rows), "similar": rows,
            "backend": VS.BACKEND, "blocking": {"cnae_section": section},
            "engine_version": ENGINE_VERSION}


async def search(query: str, limit: int = 10, section: Optional[str] = None) -> Dict:
    e = await asyncio.to_thread(E.get_provider().embed, query)
    rows = await VS.top_k(e["vector"], section, exclude="__query__", k=limit)
    return {"query": query, "count": len(rows), "results": rows,
            "backend": VS.BACKEND, "embedding_model": e["model"], "engine_version": ENGINE_VERSION}
