"""Object Storage abstraction layer.
Uses Emergent Object Storage in v1, designed for easy swap to S3/R2."""

import os
import uuid
import requests
import logging

logger = logging.getLogger(__name__)

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = os.environ.get("APP_NAME", "agency-scraper")

_storage_key = None


def init_storage():
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(
        f"{STORAGE_URL}/init",
        json={"emergent_key": EMERGENT_KEY},
        timeout=30
    )
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    logger.info("Object storage initialized")
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple:
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key},
        timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def upload_screenshot(screenshot_bytes: bytes, result_id: str) -> str:
    """Upload screenshot and return storage path."""
    file_id = str(uuid.uuid4())
    path = f"{APP_NAME}/screenshots/{result_id}/{file_id}.png"
    put_object(path, screenshot_bytes, "image/png")
    return path


def upload_file(file_bytes: bytes, filename: str, content_type: str, user_id: str = "system") -> str:
    """Upload a generic file and return storage path."""
    ext = filename.split(".")[-1] if "." in filename else "bin"
    file_id = str(uuid.uuid4())
    path = f"{APP_NAME}/uploads/{user_id}/{file_id}.{ext}"
    put_object(path, file_bytes, content_type)
    return path


def download_file(path: str) -> tuple:
    """Download file and return (bytes, content_type)."""
    return get_object(path)
