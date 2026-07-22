"""Analyze Skill endpoint (REQ-001) — enriched company contract for arroba.com.

POST /api/v1/enrich_company — reuses the canonical master record + Value/Recommend engines.
Protected by a service API key (X-API-Key) + per-key rate limiting. Narrative via Claude,
cached to avoid repeated LLM calls. Contract unchanged.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict

from services.skills_analyze import enrich_company_analyze
from services.service_auth import require_service_key

router = APIRouter(prefix="/api/v1", tags=["analyze"])


class EnrichCompanyRequest(BaseModel):
    master_company_id: str
    context: Dict = Field(default_factory=dict)


@router.post("/enrich_company")
async def enrich_company(req: EnrichCompanyRequest, _key=Depends(require_service_key)):
    """Analyze skill: enriched company with financials, growth, ratios, peers, narrative."""
    result = await enrich_company_analyze(req.master_company_id, req.context)
    if result is None:
        raise HTTPException(404, "master_company_id not found")
    return result
