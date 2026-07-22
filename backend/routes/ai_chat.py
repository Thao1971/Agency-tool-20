"""Generic AI Chat test utility (OpenAI gpt-5.5, user's own API key). Additive, not part of arroba.v1."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db
from auth_utils import get_current_user
from emergentintegrations.llm.chat import LlmChat, UserMessage

router = APIRouter(prefix="/api/v1/ai-chat", tags=["ai-chat"])

MODEL = "gpt-5.5"
PROVIDER = "openai"
SYSTEM_MESSAGE = "You are a helpful AI assistant used for testing inside the Agency Tool platform."


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _save(session_id: str, role: str, content: str):
    await db.ai_chat_messages.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": _now(),
    })


@router.post("/message")
async def chat_message(req: ChatRequest, user=Depends(get_current_user)):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured on the server")
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    session_id = req.session_id or str(uuid.uuid4())
    await _save(session_id, "user", req.message)

    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=SYSTEM_MESSAGE,
    ).with_model(PROVIDER, MODEL)

    try:
        reply = await chat.send_message(UserMessage(text=req.message))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {str(e)}")

    await _save(session_id, "assistant", reply)
    return {"session_id": session_id, "reply": reply, "model": MODEL}


@router.get("/history/{session_id}")
async def history(session_id: str, user=Depends(get_current_user)):
    docs = await db.ai_chat_messages.find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(1000)
    return {"session_id": session_id, "messages": docs}


@router.get("/sessions")
async def sessions(user=Depends(get_current_user)):
    pipeline = [
        {"$sort": {"created_at": 1}},
        {"$group": {
            "_id": "$session_id",
            "last_at": {"$last": "$created_at"},
            "count": {"$sum": 1},
            "first_message": {"$first": "$content"},
        }},
        {"$sort": {"last_at": -1}},
        {"$limit": 100},
    ]
    rows = await db.ai_chat_messages.aggregate(pipeline).to_list(100)
    return {"sessions": [
        {"session_id": r["_id"], "last_at": r["last_at"], "count": r["count"],
         "preview": (r.get("first_message") or "")[:60]}
        for r in rows
    ]}


@router.delete("/session/{session_id}")
async def clear_session(session_id: str, user=Depends(get_current_user)):
    res = await db.ai_chat_messages.delete_many({"session_id": session_id})
    return {"deleted": res.deleted_count}
