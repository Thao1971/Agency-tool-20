"""Data Providers — Secure file upload for external data providers."""

import hashlib
import os
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Header, Depends, Query, Request
from fastapi.responses import Response
from typing import Optional
from database import db
from models import new_id, now_iso
from auth_utils import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])

MAX_FILE_SIZE = 250 * 1024 * 1024  # 250 MB
ALLOWED_EXTENSIONS = {".xlsx", ".csv", ".zip"}


# ══════════════════════════════════════════
# UPLOAD (provider-facing, key auth)
# ══════════════════════════════════════════

@router.post("/{provider_id}/upload")
async def upload_file(
    provider_id: str,
    request: Request,
    file: UploadFile = File(...),
    x_provider_key: str = Header(...),
):
    """Upload a file from an external data provider."""
    # Validate key: check env var first, then DB
    env_key = os.environ.get(f"{provider_id.upper()}_UPLOAD_API_KEY")
    provider = await db.data_providers.find_one(
        {"provider_id": provider_id, "active": True}, {"_id": 0}
    )
    if not provider:
        raise HTTPException(404, "Provider not found")

    key_valid = False
    if env_key and x_provider_key == env_key:
        key_valid = True
    elif provider.get("api_key") and x_provider_key == provider["api_key"]:
        key_valid = True

    if not key_valid:
        raise HTTPException(401, "Invalid provider key")

    # Validate file extension
    import os as _os
    ext = _os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Formato no aceptado ({ext}). Formatos validos: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    content = await file.read()
    size_bytes = len(content)

    if size_bytes > MAX_FILE_SIZE:
        raise HTTPException(413, f"Fichero demasiado grande. Maximo {MAX_FILE_SIZE // (1024*1024)} MB")

    now = now_iso()
    file_id = f"pf_{new_id()[:12]}"
    checksum = hashlib.sha256(content).hexdigest()

    # Source IP
    source_ip = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        source_ip = forwarded.split(",")[0].strip()

    record = {
        "file_id": file_id,
        "provider_id": provider_id,
        "provider_name": provider.get("name", provider_id),
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": size_bytes,
        "checksum_sha256": checksum,
        "status": "received",
        "source_ip": source_ip,
        "uploaded_at": now,
        "created_at": now,
        "processed": False,
        "processed_at": None,
        "records_detected": None,
        "notes": None,
    }
    await db.provider_files.insert_one({**record})

    # Store raw content separately
    await db.provider_file_contents.insert_one({
        "file_id": file_id,
        "content": content,
    })

    # Update provider stats
    await db.data_providers.update_one(
        {"provider_id": provider_id},
        {"$set": {
            "last_upload_at": now,
            "last_file_id": file_id,
            "last_filename": file.filename,
            "last_file_size": size_bytes,
            "total_uploads": provider.get("total_uploads", 0) + 1,
        }}
    )

    logger.info(f"Provider {provider_id} uploaded {file.filename} ({size_bytes} bytes, sha256={checksum[:16]})")

    return {
        "status": "received",
        "file_id": file_id,
        "filename": file.filename,
        "size_bytes": size_bytes,
        "checksum_sha256": checksum,
        "uploaded_at": now,
    }


# ══════════════════════════════════════════
# ADMIN (Agency Tool UI, JWT auth)
# ══════════════════════════════════════════

@router.get("")
async def list_providers(user=Depends(get_current_user)):
    """List all data providers with status."""
    providers = await db.data_providers.find({}, {"_id": 0, "api_key": 0}).to_list(50)
    return {"providers": providers}


@router.get("/dashboard")
async def providers_dashboard(user=Depends(get_current_user)):
    """Dashboard summary for all providers."""
    providers = await db.data_providers.find({"active": True}, {"_id": 0, "api_key": 0}).to_list(50)

    result = []
    for p in providers:
        last_file = await db.provider_files.find_one(
            {"provider_id": p["provider_id"]}, {"_id": 0}
        , sort=[("uploaded_at", -1)])

        total = await db.provider_files.count_documents({"provider_id": p["provider_id"]})

        result.append({
            "provider_id": p["provider_id"],
            "name": p.get("name"),
            "description": p.get("description"),
            "frequency": p.get("frequency", "weekly"),
            "active": p.get("active", True),
            "total_uploads": total,
            "last_upload_at": p.get("last_upload_at"),
            "last_filename": p.get("last_filename"),
            "last_file_size": p.get("last_file_size"),
            "last_file": last_file,
        })

    return {"providers": result}


@router.get("/{provider_id}/files")
async def list_provider_files(
    provider_id: str,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user)
):
    """List files received from a provider."""
    files = await db.provider_files.find(
        {"provider_id": provider_id}, {"_id": 0}
    ).sort("uploaded_at", -1).limit(limit).to_list(limit)
    total = await db.provider_files.count_documents({"provider_id": provider_id})
    return {"files": files, "total": total}


@router.get("/{provider_id}/files/{file_id}/download")
async def download_provider_file(provider_id: str, file_id: str, user=Depends(get_current_user)):
    """Download a received file."""
    record = await db.provider_files.find_one(
        {"file_id": file_id, "provider_id": provider_id}, {"_id": 0}
    )
    if not record:
        raise HTTPException(404, "File not found")

    content_doc = await db.provider_file_contents.find_one({"file_id": file_id})
    if not content_doc:
        raise HTTPException(404, "File content not found")

    return Response(
        content=content_doc["content"],
        media_type=record.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename={record['filename']}"}
    )
