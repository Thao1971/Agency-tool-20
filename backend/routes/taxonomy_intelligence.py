"""Taxonomy Intelligence — Semantic Mapping Engine v2 (Quality Console endpoints).

No human-approval surface. The engine resolves automatically; humans observe quality.
"""

from fastapi import APIRouter, Depends, Query
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.taxonomy_intelligence import (
    resolve, resolve_to_cnae, get_health, get_coverage, get_orphans,
    get_inconsistencies, seed_all_taxonomies, recompute_all_weights, ensure_taxonomy_v2,
)
from services.taxonomy_llm import (
    run_suggestions, list_suggestions, suggestions_stats,
)
import time

router = APIRouter(prefix="/api/v1/taxonomy-intelligence", tags=["taxonomy_intelligence"])

CONTRACT_VERSION = "2.0"


def _meta(t0):
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now_iso(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
    }


@router.get("/health")
async def health(user=Depends(get_current_user)):
    """Top-level health verdict of the mapping engine (incl. LLM auto-learn signals)."""
    t0 = time.time()
    base = await get_health()
    llm = await suggestions_stats()
    return {**_meta(t0), **base, **llm}


# ──────────────────────────────────────────────────────────────────────────
# LLM Assisted Mapping (Fase B)
# ──────────────────────────────────────────────────────────────────────────

@router.post("/suggest")
async def suggest(
    scope: str = Query("all", regex="^(orphans|weak|all)$"),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
):
    """Generate GPT-5.2 suggestions for orphans/weak mappings, score via MetaScore, auto-activate >=0.90."""
    return await run_suggestions(scope=scope, limit=limit)


@router.get("/suggestions")
async def suggestions(
    status: str = Query(None, regex="^(candidate|accepted|rejected)$"),
    taxonomy: str = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    user=Depends(get_current_user),
):
    """All AI-generated suggestions (filter by status/taxonomy)."""
    t0 = time.time()
    items = await list_suggestions(status=status, taxonomy=taxonomy, limit=limit)
    return {**_meta(t0), "suggestions": items, "count": len(items)}


@router.get("/suggestions/weak")
async def suggestions_weak(limit: int = Query(500, ge=1, le=2000), user=Depends(get_current_user)):
    """Suggestions generated for weak mappings."""
    t0 = time.time()
    items = await list_suggestions(target_type="weak", limit=limit)
    return {**_meta(t0), "suggestions": items, "count": len(items)}


@router.get("/suggestions/orphans")
async def suggestions_orphans(limit: int = Query(500, ge=1, le=2000), user=Depends(get_current_user)):
    """Suggestions generated for orphan codes."""
    t0 = time.time()
    items = await list_suggestions(target_type="orphan", limit=limit)
    return {**_meta(t0), "suggestions": items, "count": len(items)}


@router.get("/suggestions/stats")
async def suggestions_statistics(user=Depends(get_current_user)):
    """Aggregate stats over AI suggestions."""
    t0 = time.time()
    return {**_meta(t0), **(await suggestions_stats())}


@router.get("/coverage")
async def coverage(user=Depends(get_current_user)):
    """Per-taxonomy coverage and weight integrity."""
    t0 = time.time()
    return {**_meta(t0), **(await get_coverage())}


@router.get("/orphans")
async def orphans(limit: int = Query(500, ge=1, le=10000), user=Depends(get_current_user)):
    """Source codes with no active mapping (real signal loss flagged first)."""
    t0 = time.time()
    return {**_meta(t0), **(await get_orphans(limit))}


@router.get("/inconsistencies")
async def inconsistencies(limit: int = Query(500, ge=1, le=5000), user=Depends(get_current_user)):
    """Weight integrity breaches, weak mappings and fragmented (conflict) codes."""
    t0 = time.time()
    return {**_meta(t0), **(await get_inconsistencies(limit))}


@router.get("/all")
async def all_mappings(
    taxonomy: str = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    user=Depends(get_current_user),
):
    """All mappings, optionally filtered by taxonomy (active + inactive)."""
    t0 = time.time()
    query = {}
    if taxonomy:
        query["source_taxonomy"] = taxonomy
    items = await db.taxonomy_mappings.find(query, {"_id": 0}).sort([
        ("source_taxonomy", 1), ("source_code", 1), ("weight", -1)
    ]).limit(limit).to_list(limit)
    return {**_meta(t0), "mappings": items, "count": len(items)}


@router.get("/resolve/{taxonomy}/{code}")
async def resolve_endpoint(taxonomy: str, code: str):
    """Resolve an external code to weighted CNAEs. Public for Arroba/Valuo. Never returns None."""
    t0 = time.time()
    result = await resolve(taxonomy, code)
    return {**_meta(t0), **result}


@router.post("/seed")
async def seed(user=Depends(get_current_user)):
    """Re-seed all taxonomy mappings from defaults and re-normalize weights."""
    seeded = await seed_all_taxonomies()
    weights = await recompute_all_weights()
    return {"seeded": seeded, "weights": weights}


@router.post("/recompute-weights")
async def recompute(user=Depends(get_current_user)):
    """Re-normalize weights for all active mapping groups (restores weight integrity)."""
    return await recompute_all_weights()
