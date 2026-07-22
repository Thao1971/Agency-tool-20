import os
import jwt
import bcrypt
import uuid
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import Header, HTTPException, Depends
from database import db

JWT_SECRET = os.environ.get('JWT_SECRET', 'default-secret')
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

def generate_api_key() -> tuple:
    """Returns (raw_key, key_hash, key_prefix)"""
    raw = f"as_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:12]
    return raw, key_hash, prefix


async def get_current_user(authorization: str = Header(None)):
    """Dependency: extract user from JWT or API key."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = authorization.replace("Bearer ", "").strip()

    # Try JWT first
    try:
        payload = decode_token(token)
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        pass

    # Try API key
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    api_key = await db.api_keys.find_one({"key_hash": key_hash, "active": True}, {"_id": 0})
    if api_key:
        await db.api_keys.update_one(
            {"id": api_key["id"]},
            {"$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}}
        )
        user = await db.users.find_one({"id": api_key["user_id"]}, {"_id": 0})
        if user:
            return user

    raise HTTPException(status_code=401, detail="Invalid credentials")


async def optional_user(authorization: str = Header(None)):
    """Dependency: optionally extract user, return None if no auth."""
    if not authorization:
        return None
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None
