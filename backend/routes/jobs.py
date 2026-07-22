from fastapi import APIRouter, HTTPException, Depends, Query
from auth_utils import get_current_user
from database import db
from services.orchestrator import run_analysis
import asyncio

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(job_id: str, user=Depends(get_current_user)):
    job = await db.analysis_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/retry")
async def retry_job(job_id: str, user=Depends(get_current_user)):
    job = await db.analysis_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] not in ("error", "pending"):
        raise HTTPException(status_code=400, detail="Only failed or pending jobs can be retried")

    retries = job.get("retries", 0) + 1
    await db.analysis_jobs.update_one(
        {"id": job_id},
        {"$set": {"status": "pending", "retries": retries, "error_message": None, "phase": None}}
    )

    asyncio.create_task(run_analysis(job_id, job["url"]))

    return {"status": "retrying", "retries": retries}


@router.get("/bulk/{bulk_id}")
async def get_bulk_job(bulk_id: str, user=Depends(get_current_user)):
    bulk = await db.bulk_jobs.find_one({"id": bulk_id}, {"_id": 0})
    if not bulk:
        raise HTTPException(status_code=404, detail="Bulk job not found")
    return bulk


@router.get("/bulk/{bulk_id}/items")
async def get_bulk_job_items(
    bulk_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user)
):
    skip = (page - 1) * limit
    total = await db.bulk_job_items.count_documents({"bulk_job_id": bulk_id})
    items = await db.bulk_job_items.find(
        {"bulk_job_id": bulk_id}, {"_id": 0}
    ).sort("order", 1).skip(skip).limit(limit).to_list(limit)
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 0
    }
