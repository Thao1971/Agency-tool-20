"""Skills endpoints — public Agency Tool intelligence skills for arroba.com.

POST /api/v1/skills/search (REQ-003) — public, no auth, stable workspace.blocks contract.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

from services.skills_search import search_companies
from services.skills_valuation import value_company
from services.skills_recommend import recommend

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class SearchFilters(BaseModel):
    cnae: List[str] = Field(default_factory=list)
    category: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    has_domain: bool = True


class SearchPagination(BaseModel):
    page: int = 1
    page_size: int = 20


class SearchRequest(BaseModel):
    query: str = ""
    filters: SearchFilters = Field(default_factory=SearchFilters)
    context: Dict = Field(default_factory=dict)
    pagination: SearchPagination = Field(default_factory=SearchPagination)


@router.post("/search")
async def skill_search(req: SearchRequest):
    """Company search skill. Returns workspace.blocks with a single search_results block."""
    page = max(1, req.pagination.page)
    page_size = min(max(1, req.pagination.page_size), 100)
    return await search_companies(req.query, req.filters.model_dump(), page, page_size, req.context)


class ValueRequest(BaseModel):
    master_company_id: str
    context: Dict = Field(default_factory=dict)


@router.post("/value")
async def skill_value(req: ValueRequest):
    """Valuation skill. Returns {valuation_range, comparables, explanation, confidence, lineage}."""
    result = await value_company(req.master_company_id, req.context)
    if result is None:
        raise HTTPException(404, "master_company_id not found")
    return result


class RecommendRequest(BaseModel):
    master_company_id: Optional[str] = None
    query: str = ""
    filters: SearchFilters = Field(default_factory=SearchFilters)
    context: Dict = Field(default_factory=dict)
    pagination: SearchPagination = Field(default_factory=SearchPagination)


@router.post("/recommend")
async def skill_recommend(req: RecommendRequest):
    """Recommendation skill. Mode 'similar' if master_company_id given, else 'thesis' by query."""
    limit = min(max(1, req.pagination.page_size), 100)
    result = await recommend(req.master_company_id, req.query, req.filters.model_dump(), limit)
    if result is None:
        raise HTTPException(404, "master_company_id not found")
    return result
