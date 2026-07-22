from fastapi import APIRouter, HTTPException, Depends
from models import (
    RegisterRequest, LoginRequest, TokenResponse,
    ApiKeyCreate, ApiKeyResponse, new_id, now_iso
)
from auth_utils import (
    hash_password, verify_password, create_token,
    generate_api_key, get_current_user
)
from database import db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    existing = await db.users.find_one({"email": req.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = new_id()
    user = {
        "id": user_id,
        "email": req.email,
        "password_hash": hash_password(req.password),
        "role": "admin",
        "created_at": now_iso()
    }
    await db.users.insert_one({**user})
    token = create_token(user_id, req.email)
    return TokenResponse(token=token, user_id=user_id, email=req.email)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user["id"], user["email"])
    return TokenResponse(token=token, user_id=user["id"], email=user["email"])


@router.post("/api-keys")
async def create_api_key(req: ApiKeyCreate, user=Depends(get_current_user)):
    raw_key, key_hash, prefix = generate_api_key()
    api_key_doc = {
        "id": new_id(),
        "user_id": user["id"],
        "name": req.name,
        "key_hash": key_hash,
        "key_prefix": prefix,
        "active": True,
        "last_used_at": None,
        "created_at": now_iso()
    }
    await db.api_keys.insert_one({**api_key_doc})
    return {"id": api_key_doc["id"], "key": raw_key, "prefix": prefix, "name": req.name}


@router.get("/api-keys")
async def list_api_keys(user=Depends(get_current_user)):
    keys = await db.api_keys.find(
        {"user_id": user["id"]},
        {"_id": 0, "key_hash": 0}
    ).to_list(100)
    return keys


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, user=Depends(get_current_user)):
    result = await db.api_keys.update_one(
        {"id": key_id, "user_id": user["id"]},
        {"$set": {"active": False}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked"}


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user.get("role", "user")
    }
