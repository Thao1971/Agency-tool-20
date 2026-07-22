import asyncio
import uuid
import io
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from models import ScrapeRequest, BulkScrapeRequest, new_id, now_iso
from auth_utils import get_current_user
from database import db
from services.orchestrator import run_analysis, run_bulk_analysis

router = APIRouter(prefix="/api/v1/scrape", tags=["scrape"])


@router.post("")
async def scrape_individual(req: ScrapeRequest, user=Depends(get_current_user)):
    """Launch individual URL analysis. Returns job_id immediately, processes async."""
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    job_id = new_id()
    now = now_iso()

    job = {
        "id": job_id,
        "url": url,
        "status": "pending",
        "bulk_job_id": None,
        "bulk_item_id": None,
        "result_id": None,
        "retries": 0,
        "max_retries": 3,
        "error_message": None,
        "phase": None,
        "user_id": user["id"],
        "created_at": now,
        "started_at": None,
        "completed_at": None
    }
    await db.analysis_jobs.insert_one({**job})

    # Job created as "pending" — persistent worker picks it up automatically

    return {
        "job_id": job_id,
        "status": "pending",
        "url": url,
        "created_at": now
    }


async def _run_and_handle(job_id: str, url: str):
    try:
        await run_analysis(job_id, url)
    except Exception as e:
        pass  # Error already handled in orchestrator


@router.post("/bulk")
async def scrape_bulk(req: BulkScrapeRequest, user=Depends(get_current_user)):
    """Launch bulk analysis from a list of URLs."""
    if not req.urls or len(req.urls) == 0:
        raise HTTPException(status_code=400, detail="No URLs provided")

    bulk_job_id = new_id()
    now = now_iso()

    bulk_job = {
        "id": bulk_job_id,
        "user_id": user["id"],
        "filename": None,
        "total_urls": len(req.urls),
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "status": "pending",
        "callback_url": req.callback_url,
        "created_at": now,
        "completed_at": None
    }
    await db.bulk_jobs.insert_one({**bulk_job})

    items = []
    for i, url in enumerate(req.urls):
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        job_id = new_id()
        item_id = new_id()

        analysis_job = {
            "id": job_id,
            "url": clean_url,
            "status": "pending",
            "bulk_job_id": bulk_job_id,
            "bulk_item_id": item_id,
            "result_id": None,
            "retries": 0,
            "max_retries": 3,
            "error_message": None,
            "phase": None,
            "user_id": user["id"],
            "created_at": now,
            "started_at": None,
            "completed_at": None
        }
        await db.analysis_jobs.insert_one({**analysis_job})

        item = {
            "id": item_id,
            "bulk_job_id": bulk_job_id,
            "url": clean_url,
            "order": i,
            "status": "pending",
            "job_id": job_id,
            "result_id": None,
            "error_message": None,
            "created_at": now,
            "completed_at": None
        }
        items.append(item)

    if items:
        await db.bulk_job_items.insert_many([{**i} for i in items])

    # Run bulk analysis in background
    asyncio.create_task(run_bulk_analysis(bulk_job_id))

    return {
        "bulk_job_id": bulk_job_id,
        "total_urls": len(req.urls),
        "status": "pending",
        "items": [{"id": i["id"], "url": i["url"], "status": "pending"} for i in items]
    }


@router.post("/bulk/upload")
async def scrape_bulk_upload(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    """Upload CSV/Excel for bulk analysis."""
    import pandas as pd

    content = await file.read()
    filename = file.filename or "upload"

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use CSV or Excel.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    # Find URL column
    url_col = None
    for col in df.columns:
        if col.lower().strip() in ("url", "urls", "website", "web", "link", "domain"):
            url_col = col
            break
    if url_col is None:
        url_col = df.columns[0]

    urls = df[url_col].dropna().astype(str).tolist()
    urls = [u.strip() for u in urls if u.strip() and u.strip().lower() != "nan"]

    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs found in file")

    # Reuse bulk logic
    req = BulkScrapeRequest(urls=urls)
    return await scrape_bulk(req, user)
