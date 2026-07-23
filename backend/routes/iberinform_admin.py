"""Iberinform Processing — Admin endpoints for import and recalculation."""

import asyncio
import os
import shutil
import time
import uuid
import zipfile
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.iberinform_processor import (
    generate_synthetic_dataset, process_real_iberinform_file,
    process_real_iberinform_tab_directory, purge_synthetic_dataset,
)
from services.sector_intelligence_v2 import compute_sector_intelligence_v2
from services.geo_intelligence import compute_geo_intelligence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/iberinform", tags=["iberinform_admin"])

# Where uploaded monthly deliveries get extracted. One subdirectory per run_id, kept
# around after processing for audit/debugging (not auto-cleaned — a monthly ~10MB zip
# is cheap to retain; revisit if this ever needs pruning).
DELIVERIES_DIR = Path(__file__).resolve().parent.parent / "data" / "iberinform_deliveries"


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


@router.post("/process-tab-directory")
async def process_tab_directory(
    directory: str = Query(..., description="Server-side path to the extracted Datos_*.tab delivery"),
    source_version: str = Query("real-2026-07"),
    user=Depends(get_current_user),
):
    """Process a real Iberinform delivery (Datos_GENERALES.tab + Datos_BALANCES.tab)
    into the legacy companies_master schema. See process_real_iberinform_tab_directory
    docstring — this is one half of the real-data load; the other half (modern
    master_companies schema) is services/data_layer/ingestion/iberinform_tab_ingest.py,
    triggered separately via the data-layer ingestion pipeline."""
    return await process_real_iberinform_tab_directory(directory, source_version=source_version)


def _find_data_dir(root: str) -> Optional[str]:
    """Walk the extracted zip looking for the folder that actually contains
    Datos_GENERALES.tab — some deliveries nest the files inside a subfolder
    (e.g. the zip's own name) instead of putting them at the top level."""
    for dirpath, _dirnames, filenames in os.walk(root):
        if "Datos_GENERALES.tab" in filenames:
            return dirpath
    return None


async def _run_delivery(run_id: str, data_dir: str, source_version: str) -> None:
    """Background task: load one monthly delivery into BOTH schemas.

    Legacy (companies_master, used by Sector/Geo Intelligence + Valuo) and modern
    (master_companies, used by Control&Synergy/Roll-up/Fragmentacion/Watchlist/grafo)
    are both fed from the same 10 .tab files — see process_real_iberinform_tab_directory
    and services/data_layer/bootstrap.run_bootstrap_tab. Both are upsert-based, so
    re-running (or running a later delivery) never duplicates a company. Recalculates
    Sector/Geo Intelligence at the end so the legacy-schema screens reflect the new data.

    Known limitation, not fixed here: neither pipeline removes a company/relationship
    that existed in a previous delivery but is absent from this one (e.g. a company
    Iberinform stops covering, or a shareholder relationship that ended) — upserts only
    add/update, they never delete. Fine for the common case (most companies persist
    delivery to delivery) but worth knowing before treating record counts as exact.
    """
    t0 = time.time()
    steps = []

    async def _set(patch):
        await db.iberinform_delivery_runs.update_one({"run_id": run_id}, {"$set": patch}, upsert=True)

    try:
        legacy = await process_real_iberinform_tab_directory(data_dir, source_version=source_version)
        steps.append({"step": "legacy_ingest", "status": "ok" if legacy.get("status") != "error" else "error", "result": legacy})
        await _set({"steps": steps})
        if legacy.get("status") == "error":
            raise RuntimeError(f"legacy ingest failed: {legacy.get('message')}")

        sector_result = await compute_sector_intelligence_v2()
        geo_result = await compute_geo_intelligence()
        steps.append({"step": "legacy_intelligence", "status": "ok",
                      "result": {"sector_total": sector_result.get("total"), "geo_total": geo_result.get("total")}})
        await _set({"steps": steps})

        from services.data_layer import bootstrap as bootstrap_svc
        modern = await bootstrap_svc.run_bootstrap_tab(
            directory=data_dir, run_id=f"{run_id}_modern", source_version=source_version)
        steps.append({"step": "modern_ingest", "status": "ok" if modern.get("status") != "failed" else "error", "result": modern})

        status = "completed" if all(s["status"] == "ok" for s in steps) else "completed_with_errors"
        await _set({"status": status, "finished_at": now_iso(),
                    "duration_s": round(time.time() - t0, 1), "steps": steps})
        logger.info(f"[iberinform delivery {run_id}] {status} in {round(time.time()-t0,1)}s")
    except Exception as e:  # noqa: BLE001 — persisted, never crashes the background task
        steps.append({"step": "error", "status": "error", "error": str(e)})
        await _set({"status": "failed", "finished_at": now_iso(),
                    "duration_s": round(time.time() - t0, 1), "error": str(e), "steps": steps})
        logger.error(f"[iberinform delivery {run_id}] failed: {e}")


@router.post("/upload-delivery")
async def upload_delivery(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload a monthly Iberinform delivery (zip of Datos_*.tab files) and load it into
    BOTH schemas (legacy companies_master + modern master_companies) in the background.
    This is the recurring-load path: every time Iberinform sends a new export, upload
    the zip here instead of asking an engineer to run scripts by hand.

    Runs in the background (can take a while at 25k companies + ownership graph rebuild).
    Poll GET /admin/iberinform/upload-delivery/{run_id} for progress."""
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "El fichero debe ser un .zip (la entrega de Iberinform tal cual la reciben)")

    content = await file.read()
    if not content:
        raise HTTPException(400, "El fichero esta vacio")

    run_id = f"delivery_{uuid.uuid4().hex[:12]}"
    extract_dir = DELIVERIES_DIR / run_id
    extract_dir.mkdir(parents=True, exist_ok=True)

    zip_path = extract_dir / "_original.zip"
    zip_path.write_bytes(content)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise HTTPException(400, "El fichero no es un zip valido")

    data_dir = _find_data_dir(str(extract_dir))
    if not data_dir:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise HTTPException(
            400,
            "No se encontro Datos_GENERALES.tab dentro del zip — no parece una entrega "
            "de Iberinform reconocible. Comprueba que el zip contiene los ficheros .tab "
            "tal como los envia Iberinform (no una carpeta reorganizada a mano)."
        )

    await db.iberinform_delivery_runs.insert_one({
        "run_id": run_id, "status": "running", "filename": file.filename,
        "size_bytes": len(content), "started_at": now_iso(), "steps": [],
    })

    asyncio.create_task(_run_delivery(run_id, data_dir, source_version=run_id))

    return {"run_id": run_id, "status": "started",
            "poll": f"/api/v1/admin/iberinform/upload-delivery/{run_id}"}


@router.get("/upload-delivery/{run_id}")
async def get_delivery(run_id: str, user=Depends(get_current_user)):
    doc = await db.iberinform_delivery_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Carga no encontrada")
    return doc


@router.get("/upload-delivery")
async def list_deliveries(limit: int = Query(10, ge=1, le=50), user=Depends(get_current_user)):
    runs = await db.iberinform_delivery_runs.find({}, {"_id": 0}).sort("started_at", -1).to_list(limit)
    return {"runs": runs}


@router.post("/purge-synthetic")
async def purge_synthetic(user=Depends(get_current_user)):
    """Remove the synthetic Iberinform dataset once real data has been loaded and
    verified. Only deletes docs still tagged source="iberinform_synthetic" — never
    touches anything a real delivery has since overwritten."""
    return await purge_synthetic_dataset()


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
    # Explicit real/synthetic split (same "source" marker purge_synthetic_dataset() uses),
    # so the frontend never has to infer this by subtracting unrelated counts (that inference
    # broke once real Iberinform data became the majority of companies_master — see
    # DataQualityPage.js history).
    synthetic_companies = await db.iberinform_companies.count_documents({"source": "iberinform_synthetic"})
    real_companies = total_companies - synthetic_companies

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
            "real_companies": real_companies,
            "synthetic_companies": synthetic_companies,
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
