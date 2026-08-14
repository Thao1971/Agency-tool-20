"""Semantic Intelligence Engine API — own public contract (semantic-intelligence-v1).

Product = Company Semantic Profile. Embeddings/similar/search are derived tools.
Decoupled, UI-agnostic. Service-key auth (X-API-Key). v1 scope (D-S6): profile,
embedding, similar, search (basic), profile/schema, catalog. No full Universal Search yet.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.engines.semantic import engine as sem_engine
from services.engines.semantic import profile as PB
from services.engines.semantic import embeddings as E
from services.engines.semantic import vector_search as VS
from services.service_auth import require_service_key
from routes import engine_schemas as S

router = APIRouter(prefix="/api/v1/semantic-intelligence", tags=["semantic_intelligence"])


def _ok(model):
    return {200: {"model": model, "description": "Successful Response"}}


class ProfileRequest(BaseModel):
    identifier: str
    enrich: bool = False              # opt-in AI enrichment (D-S1)
    with_relationships: bool = False


class SimilarRequest(BaseModel):
    identifier: str
    limit: int = 10
    same_section: bool = True


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    cnae_section: Optional[str] = None


@router.post("/profile", responses=_ok(S.SemanticProfileResponse))
async def profile(req: ProfileRequest, _key=Depends(require_service_key)):
    result = await sem_engine.build_profile(req.identifier, enrich=req.enrich,
                                            with_relationships=req.with_relationships)
    if result is None:
        raise HTTPException(404, "company not found in Master Layer")
    return result


@router.post("/embedding", responses=_ok(S.SemanticEmbeddingResponse))
async def embedding(req: ProfileRequest, _key=Depends(require_service_key)):
    result = await sem_engine.get_embedding(req.identifier)
    if result is None:
        raise HTTPException(404, "company not found in Master Layer")
    return result


@router.post("/similar", responses=_ok(S.SemanticSimilarResponse))
async def similar(req: SimilarRequest, _key=Depends(require_service_key)):
    result = await sem_engine.similar(req.identifier, limit=req.limit, same_section=req.same_section)
    if result is None:
        raise HTTPException(404, "company not found in Master Layer")
    return result


@router.post("/search", responses=_ok(S.SemanticSearchResponse))
async def search(req: SearchRequest, _key=Depends(require_service_key)):
    if not req.query.strip():
        raise HTTPException(400, "query required")
    res = await sem_engine.search(req.query, limit=req.limit, section=req.cnae_section)
    rows = res.get("results") or []
    if rows:
        from services.company_card import build_summaries
        summaries = await build_summaries([r["master_id"] for r in rows])
        for r in rows:
            r["summary"] = summaries.get(r["master_id"])
    return res


@router.get("/profile/schema", responses=_ok(S.SemanticProfileSchemaResponse))
async def profile_schema(_key=Depends(require_service_key)):
    return {"profile_version": PB.PROFILE_VERSION, "dimensions": PB.DIMENSIONS,
            "dimension_count": len(PB.DIMENSIONS),
            "status_values": ["available", "partial", "unavailable"],
            "methods": ["rules", "ai"],
            "embedding_sources": PB.EMBEDDING_SOURCES}


@router.get("/catalog", responses=_ok(S.SemanticCatalogResponse))
async def catalog(_key=Depends(require_service_key)):
    return {"engine_version": sem_engine.ENGINE_VERSION,
            "profile_version": PB.PROFILE_VERSION,
            "embedding_version": E.EMBEDDING_VERSION,
            "embedding_provider": E.get_provider().name,
            "embedding_model": E.get_provider().model,
            "vector_search_backend": VS.current_backend(),
            "dimensions": PB.DIMENSIONS,
            "scope_v1": ["profile", "embedding", "similar", "search", "profile/schema", "catalog"],
            "deferred": ["full Universal Search", "Atlas Vector Search backend",
                         "materialized semantic relationships"]}
