from fastapi import APIRouter, HTTPException, Depends
from models import ScraperConfig, ConfigUpdateRequest, now_iso
from auth_utils import get_current_user
from database import db
from services.orchestrator import get_scraper_config

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("")
async def get_config(user=Depends(get_current_user)):
    config = await get_scraper_config()
    config.pop("_id", None)
    return config


@router.put("")
async def update_config(req: ConfigUpdateRequest, user=Depends(get_current_user)):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = now_iso()

    config = await get_scraper_config()
    await db.scraper_config.update_one(
        {"id": config["id"]},
        {"$set": update}
    )

    updated = await db.scraper_config.find_one({"id": config["id"]}, {"_id": 0})
    return updated
