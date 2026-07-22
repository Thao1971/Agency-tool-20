"""Sector × Geo Cross-Intelligence — Public endpoints.

Answers: What sectors grow in Madrid? Where does tech concentrate?
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.sector_geo_cross import (
    compute_sector_geo_cross,
    get_sectors_in_territory,
    get_territories_for_sector,
    get_heatmap_data,
)
import time

router = APIRouter(prefix="/api/v1/public/cross-intelligence", tags=["cross_intelligence"])

CONTRACT_VERSION = "1.0"


def _meta(t0):
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now_iso(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
        "source_attribution": "BORME, Iberinform, INE DIRCE",
    }


@router.get("/sectors-in/{geo_level}/{geo_code}")
async def sectors_in_territory(
    geo_level: str,
    geo_code: str,
    limit: int = Query(21, ge=1, le=21),
):
    """What sectors are most active in a territory?
    Example: /sectors-in/ccaa/13 → sectors in Madrid
    Example: /sectors-in/province/08 → sectors in Barcelona
    """
    t0 = time.time()
    if geo_level not in ("ccaa", "province"):
        raise HTTPException(400, "geo_level must be 'ccaa' or 'province'")

    sectors = await get_sectors_in_territory(geo_level, geo_code, limit)
    geo_name = None
    if geo_level == "ccaa":
        from services.geo_catalog import get_ccaa_label
        geo_name = get_ccaa_label(geo_code)
    else:
        from services.geo_catalog import get_province_label
        geo_name = get_province_label(geo_code)

    return {
        **_meta(t0),
        "geo_level": geo_level,
        "geo_code": geo_code,
        "geo_name": geo_name,
        "sectors": sectors,
        "count": len(sectors),
    }


@router.get("/territory-for/{cnae_section}")
async def territories_for_sector(
    cnae_section: str,
    geo_level: str = Query("province", regex="^(ccaa|province)$"),
    limit: int = Query(20, ge=1, le=52),
):
    """Where does a sector concentrate?
    Example: /territory-for/J → where is ICT strongest?
    Example: /territory-for/F?geo_level=ccaa → construction by CCAA
    """
    t0 = time.time()
    cnae_section = cnae_section.upper()

    territories = await get_territories_for_sector(cnae_section, geo_level, limit)

    from services.cnae_catalog import CNAE_SECTIONS
    section_label = None
    for s in CNAE_SECTIONS:
        if s["code"] == cnae_section:
            section_label = s["label"]
            break

    return {
        **_meta(t0),
        "cnae_section": cnae_section,
        "cnae_label": section_label,
        "geo_level": geo_level,
        "territories": territories,
        "count": len(territories),
    }


@router.get("/heatmap")
async def heatmap(cnae_section: str = Query(None)):
    """Sector × CCAA heatmap data. Optional filter by CNAE section."""
    t0 = time.time()
    if cnae_section:
        cnae_section = cnae_section.upper()
    data = await get_heatmap_data(cnae_section)
    return {
        **_meta(t0),
        "cnae_section_filter": cnae_section,
        "cells": data,
        "count": len(data),
    }


@router.post("/sync")
async def sync(user=Depends(get_current_user)):
    """Recompute sector × geo cross-intelligence."""
    result = await compute_sector_geo_cross()
    from services.intelligence_scheduler import log_manual_sync
    await log_manual_sync("cross_intelligence", result.get("combinations", 0))
    return result
