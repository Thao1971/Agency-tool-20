"""Iberinform Processing — Admin endpoints for import and recalculation."""

from fastapi import APIRouter, Depends, Query
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.iberinform_processor import generate_synthetic_dataset, process_real_iberinform_file
from services.sector_intelligence_v2 import compute_sector_intelligence_v2
from services.geo_intelligence import compute_geo_intelligence
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/iberinform", tags=["iberinform_admin"])


@router.post("/generate-synthetic")
async def generate_synthetic(
    count: int = Query(5000, ge=100, le=50000),
    user=Depends(get_current_user),
):
    """Generate synthetic Iberinform dataset based on INE DIRCE distribution."""
    t0 = time.time()

    result = await generate_synthetic_dataset(count=count)

    return {
        **result,
        "processing_time_ms": round((time.time() - t0) * 1000, 1),
    }


@router.post("/process-file/{file_id}")
async def process_file(file_id: str, user=Depends(get_current_user)):
    """Process a real Iberinform file from provider uploads."""
    return await process_real_iberinform_file(file_id)


@router.post("/recalculate-intelligence")
async def recalculate_intelligence(user=Depends(get_current_user)):
    """Recalculate Sector Intelligence V2 + Geo Intelligence after data import."""
    t0 = time.time()

    sector_result = await compute_sector_intelligence_v2()
    geo_result = await compute_geo_intelligence()

    return {
        "status": "completed",
        "sector_intelligence": sector_result,
        "geo_intelligence": geo_result,
        "processing_time_ms": round((time.time() - t0) * 1000, 1),
    }


@router.post("/full-pipeline")
async def full_pipeline(
    count: int = Query(5000, ge=100, le=50000),
    user=Depends(get_current_user),
):
    """Full pipeline: Generate/import → Update master → Recalculate intelligence."""
    t0 = time.time()

    # Step 1: Generate synthetic data
    import_result = await generate_synthetic_dataset(count=count)
    logger.info(f"Iberinform import: {import_result['companies_imported']} companies")

    # Step 2: Recalculate intelligence
    sector_result = await compute_sector_intelligence_v2()
    logger.info(f"Sector Intelligence: {sector_result['total']} entries")

    geo_result = await compute_geo_intelligence()
    logger.info(f"Geo Intelligence: {geo_result['total']} entries")

    return {
        "status": "completed",
        "pipeline_steps": {
            "import": {
                "companies": import_result["companies_imported"],
                "fiscal_years": import_result["fiscal_years_imported"],
                "cnae_coverage": import_result["cnae_divisions_covered"],
                "province_coverage": import_result["provinces_covered"],
                "years": import_result["years_covered"],
            },
            "sector_intelligence": {
                "sections": sector_result["sections"],
                "divisions": sector_result["divisions"],
                "groups": sector_result["groups"],
                "total": sector_result["total"],
            },
            "geo_intelligence": {
                "ccaa": geo_result["ccaa"],
                "provinces": geo_result["provinces"],
                "total": geo_result["total"],
            },
        },
        "processing_time_ms": round((time.time() - t0) * 1000, 1),
    }


@router.get("/stats")
async def iberinform_stats(user=Depends(get_current_user)):
    """Summary statistics of imported Iberinform data."""
    t0 = time.time()

    total_companies = await db.iberinform_companies.count_documents({})
    total_financials = await db.iberinform_financials.count_documents({})

    # CNAE coverage
    cnae_pipeline = [
        {"$group": {"_id": "$cnae_division", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_cnae = await db.iberinform_companies.aggregate(cnae_pipeline).to_list(100)

    # Province coverage
    prov_pipeline = [
        {"$group": {"_id": "$province_code", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_province = await db.iberinform_companies.aggregate(prov_pipeline).to_list(60)

    # Year coverage
    year_pipeline = [
        {"$group": {"_id": "$year", "count": {"$sum": 1}}},
        {"$sort": {"_id": -1}},
    ]
    by_year = await db.iberinform_financials.aggregate(year_pipeline).to_list(10)

    # Revenue stats
    rev_pipeline = [
        {"$group": {
            "_id": None,
            "avg_revenue": {"$avg": "$revenue_latest"},
            "max_revenue": {"$max": "$revenue_latest"},
            "min_revenue": {"$min": "$revenue_latest"},
            "avg_employees": {"$avg": "$employees_latest"},
        }},
    ]
    rev_stats = await db.iberinform_companies.aggregate(rev_pipeline).to_list(1)

    # Companies master with CNAE
    master_with_cnae = await db.companies_master.count_documents({"cnae_primary": {"$exists": True, "$ne": None}})
    master_with_province = await db.companies_master.count_documents({"province_code": {"$exists": True, "$ne": None}})
    master_total = await db.companies_master.count_documents({})

    return {
        "generated_at": now_iso(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
        "iberinform": {
            "total_companies": total_companies,
            "total_fiscal_years": total_financials,
            "cnae_divisions_covered": len(by_cnae),
            "provinces_covered": len(by_province),
            "years_covered": [y["_id"] for y in by_year],
            "top_cnae_divisions": [{"code": c["_id"], "count": c["count"]} for c in by_cnae[:10]],
            "top_provinces": [{"code": p["_id"], "count": p["count"]} for p in by_province[:10]],
            "revenue_stats": rev_stats[0] if rev_stats else None,
        },
        "companies_master": {
            "total": master_total,
            "with_cnae": master_with_cnae,
            "with_province": master_with_province,
            "cnae_coverage_pct": round(master_with_cnae / master_total * 100, 1) if master_total > 0 else 0,
            "province_coverage_pct": round(master_with_province / master_total * 100, 1) if master_total > 0 else 0,
        },
    }
