"""Iberinform Processing — Admin endpoints for import and recalculation."""

import asyncio
import io
import os
import shutil
import tempfile
import time
import uuid
import zipfile
import logging
from datetime import datetime, timezone
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

# Uploaded deliveries are extracted to EPHEMERAL pod-local scratch (system temp via
# tempfile), used only for the in-request background load into Mongo and never served
# back to clients — so no durable/object storage is needed for this transient workflow.


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


# ── Auto-reconciliación de entregas huérfanas ──────────────────────────────
_last_reconcile_ts = 0.0
STALE_RUN_MINUTES = 45
RECONCILE_MIN_INTERVAL_S = 60


async def _reconcile_stale_delivery_runs() -> None:
    global _last_reconcile_ts
    now = time.time()
    if now - _last_reconcile_ts < RECONCILE_MIN_INTERVAL_S:
        return
    _last_reconcile_ts = now
    try:
        stale_ids = []
        cursor = db.iberinform_delivery_runs.find(
            {"status": "running"}, {"_id": 0, "run_id": 1, "worker_pid": 1, "started_at": 1}
        )
        async for doc in cursor:
            run_id = doc.get("run_id")
            pid = doc.get("worker_pid")
            if pid:
                try:
                    os.kill(pid, 0)
                    continue
                except ProcessLookupError:
                    stale_ids.append(run_id)
                    continue
                except PermissionError:
                    continue
                except Exception:
                    pass
            started_at = doc.get("started_at")
            if not started_at:
                continue
            try:
                started_dt = datetime.fromisoformat(started_at)
            except Exception:
                continue
            age_min = (datetime.now(timezone.utc) - started_dt).total_seconds() / 60
            if age_min >= STALE_RUN_MINUTES:
                stale_ids.append(run_id)
        for run_id in stale_ids:
            await db.iberinform_delivery_runs.update_one(
                {"run_id": run_id, "status": "running"},
                {"$set": {
                    "status": "failed",
                    "finished_at": now_iso(),
                    "error": "orphaned: no live worker process found during reconciliation "
                             "(worker died before writing final status — reload/pod-restart/crash)",
                }},
            )
    except Exception:
        logger.exception("iberinform: fallo en _reconcile_stale_delivery_runs (no bloqueante)")


async def _launch_delivery_worker(run_id: str, mode: str, data_dir: str = None, object_key: str = None) -> None:
    """Lanza scripts/run_delivery_worker.py como SUBPROCESO AISLADO (no en el event loop
    del backend) para que el rebuild pesado (rebuild_master completo + ownership + señales
    + índice semántico) de una entrega de 25k+ no bloquee el resto de peticiones. El
    subproceso reporta progreso a `iberinform_delivery_runs` (mismo shape y mismo polling
    que antes). Mismo enfoque que /reingest-eav (scripts/prod_seed_eav)."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    args = [_sys.executable, "-m", "scripts.run_delivery_worker", "--run-id", run_id, "--mode", mode]
    if mode == "dir":
        args += ["--data-dir", data_dir]
    else:
        args += ["--object-key", object_key]

    log_path = None
    stdout_target = asyncio.subprocess.DEVNULL
    stderr_target = asyncio.subprocess.DEVNULL
    log_file = None
    try:
        log_dir = Path(tempfile.gettempdir()) / "iberinform_worker_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{run_id}.log"
        log_file = open(log_path, "wb")
        stdout_target = stderr_target = log_file
    except Exception:
        logger.exception("iberinform: no se pudo abrir el log del worker, usando DEVNULL")

    try:
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=str(BACKEND_DIR), env=env,
            stdout=stdout_target, stderr=stderr_target,
            start_new_session=True)
    finally:
        if log_file is not None:
            log_file.close()

    await db.iberinform_delivery_runs.update_one(
        {"run_id": run_id},
        {"$set": {"worker_pid": proc.pid, **({"worker_log": str(log_path)} if log_path else {})}}
    )


@router.post("/upload-delivery")
async def upload_delivery(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload a monthly Iberinform delivery (zip of Datos_*.tab files) and load it into
    BOTH schemas (legacy companies_master + modern master_companies) in the background.
    This is the recurring-load path: every time Iberinform sends a new export, upload
    the zip here instead of asking an engineer to run scripts by hand.

    Runs in the background (can take a while at 25k companies + ownership graph rebuild).
    Poll GET /admin/iberinform/upload-delivery/{run_id} for progress."""
    await _reconcile_stale_delivery_runs()
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "El fichero debe ser un .zip (la entrega de Iberinform tal cual la reciben)")

    content = await file.read()
    if not content:
        raise HTTPException(400, "El fichero esta vacio")

    run_id = f"delivery_{uuid.uuid4().hex[:12]}"
    extract_dir = Path(tempfile.mkdtemp(prefix=f"{run_id}_"))

    # Extrae el zip directamente desde memoria — el archivo subido NUNCA se escribe en el
    # pod; solo los .tab derivados aterrizan en el scratch temporal para el load a Mongo.
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
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

    asyncio.create_task(_launch_delivery_worker(run_id, "dir", data_dir=data_dir))

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
    await _reconcile_stale_delivery_runs()
    runs = await db.iberinform_delivery_runs.find({}, {"_id": 0}).sort("started_at", -1).to_list(limit)
    return {"runs": runs}


# ══════════════════════════════════════════
# ENTREGAS DESDE R2 (streaming, sin subir el zip por HTTP)
# ──────────────────────────────────────────
# Para entregas grandes (9,8 GB, futuras decenas de GB) que no caben por un POST de
# navegador ni en el disco de 9,8 GB del pod: Daniel sube el .zip a Cloudflare R2 por su
# cuenta (rclone/aws-cli) y el backend lo INGIERE leyéndolo por STREAMING desde el bucket
# (rangos HTTP, sin materializar el zip ni los .tab en disco). El trabajo pesado corre en
# SUBPROCESO AISLADO (scripts/run_delivery_worker.py), con el mismo modelo de progreso en
# iberinform_delivery_runs y mismo polling GET /upload-delivery/{run_id}.


@router.get("/storage-deliveries")
async def list_storage_deliveries(prefix: str = Query("", description="Filtro de prefijo opcional"),
                                  user=Depends(get_current_user)):
    """Lista los .zip disponibles en el bucket R2 (los que Daniel haya subido con
    rclone/aws-cli), para elegir cuál ingerir con /process-from-storage."""
    from services.data_layer.ingestion.r2_delivery import list_zip_deliveries
    try:
        deliveries = list_zip_deliveries(prefix=prefix)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No se pudo listar el bucket R2: {e}")
    return {"deliveries": deliveries, "count": len(deliveries)}


@router.post("/process-from-storage")
async def process_from_storage(object_key: str = Query(..., description="Key del .zip en el bucket R2"),
                               user=Depends(get_current_user)):
    """Ingiere una entrega de Iberinform leyéndola por STREAMING desde R2 (sin subirla por
    HTTP ni materializarla en disco). Corre en background con el mismo modelo de progreso
    que /upload-delivery; sondea GET /upload-delivery/{run_id}."""
    await _reconcile_stale_delivery_runs()
    if not object_key.lower().endswith(".zip"):
        raise HTTPException(400, "object_key debe apuntar a un .zip")

    run_id = f"delivery_{uuid.uuid4().hex[:12]}"
    await db.iberinform_delivery_runs.insert_one({
        "run_id": run_id, "status": "running", "filename": object_key,
        "source": "r2", "object_key": object_key, "started_at": now_iso(), "steps": [],
    })
    asyncio.create_task(_launch_delivery_worker(run_id, "r2", object_key=object_key))
    return {"run_id": run_id, "status": "started",
            "poll": f"/api/v1/admin/iberinform/upload-delivery/{run_id}"}


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



# ── Re-ingesta EAV completa (balance + cash-flow) + ownership + is_listed(BME) ──────
# Siembra/actualiza la base a la que ESTÉ conectado el backend (preview local o el Atlas
# de producción tras el redeploy) usando los .tab versionados en /app/data/muestra_25000.
# Se ejecuta como SUBPROCESO AISLADO (no bloquea el event loop del backend). Idempotente.
import sys as _sys

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "muestra_25000"
BACKEND_DIR = Path(__file__).resolve().parent.parent


@router.post("/reingest-eav")
async def reingest_eav(
    ownership: bool = Query(True),
    listed: bool = Query(True),
    balances: bool = Query(True),
    user=Depends(get_current_user),
):
    """Re-ingesta EAV completa (balance + cash-flow) desde los .tab versionados, + ownership
    + marcado is_listed(BME) + backfill de ratios en master. Corre en subproceso AISLADO.
    Idempotente. `balances=false` salta el paso pesado de balances (útil si ya están
    ingeridos y solo falta el backfill ligero de ratios — evita picos de memoria en el pod)."""
    if balances and not (SAMPLE_DIR / "Datos_BALANCES.tab").exists():
        raise HTTPException(400, f"No se encuentra Datos_BALANCES.tab en {SAMPLE_DIR}")
    run_id = str(uuid.uuid4())
    await db.eav_reingest_runs.insert_one({
        "run_id": run_id, "status": "queued", "step": "queued",
        "options": {"ownership": ownership, "listed": listed, "balances": balances},
        "started_at": now_iso(), "updated_at": now_iso()})
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    await asyncio.create_subprocess_exec(
        _sys.executable, "-m", "scripts.prod_seed_eav",
        run_id, "1" if ownership else "0", "1" if listed else "0", "1" if balances else "0",
        cwd=str(BACKEND_DIR), env=env,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    return {"run_id": run_id, "status": "queued",
            "poll": f"/api/v1/admin/iberinform/reingest-eav/{run_id}"}


@router.get("/reingest-eav/{run_id}")
async def reingest_eav_status(run_id: str, user=Depends(get_current_user)):
    doc = await db.eav_reingest_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "run_id no encontrado")
    return doc
