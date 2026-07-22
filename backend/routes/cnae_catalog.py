"""CNAE Catalog — Public endpoint for CNAE hierarchy and archetypes.

Standalone route: GET /api/v1/public/cnae/catalog
"""

from fastapi import APIRouter
from services.cnae_catalog import build_full_catalog, BUSINESS_ARCHETYPES, TAXONOMY_TYPES
from models import now_iso
import time

router = APIRouter(prefix="/api/v1/public/cnae", tags=["cnae_catalog"])


@router.get("/catalog")
async def cnae_catalog():
    """Full CNAE-2009 hierarchy: Section (A-U) → Division (2-digit) → Group (4-digit)."""
    t0 = time.time()
    catalog = build_full_catalog()
    return {
        "contract_version": "1.0",
        "generated_at": now_iso(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
        "catalog": catalog,
        "total_sections": len(catalog),
        "total_divisions": sum(len(s["divisions"]) for s in catalog),
        "total_groups": sum(len(d["groups"]) for s in catalog for d in s["divisions"]),
    }


@router.get("/archetypes")
async def business_archetypes():
    """List of business archetypes for future classification."""
    return {
        "contract_version": "1.0",
        "generated_at": now_iso(),
        "archetypes": BUSINESS_ARCHETYPES,
        "taxonomy_types": TAXONOMY_TYPES,
    }
