"""ARROBA Copilot — sesiones (copilot-session-v1).

Continuidad de conversación POR USUARIO. Una sesión vive mientras la sesión de login esté activa
(`status: active|closed`), SIN TTL por inactividad (decisión de Daniel, 2026-07-31). Al cerrar sesión
se marca `closed` y no se reanuda: un login nuevo abre una sesión nueva (la memoria de usuario sí
persiste, ver memory.py).

Guarda `working_context` (entidad activa, última decisión, último nivel) para resolver referencias
implícitas ("¿y sus riesgos?" → la última compañía). No calcula, no decide, no habla. Best-effort:
si no hay BBDD degrada a una sesión efímera sin romper.
Ver memory/ARROBA_COPILOT_MEMORY_SESSIONS_PERSONALIZATION.md.
"""

import hashlib
import os
from typing import Dict, Optional

SESSION_VERSION = "copilot-session-v1"
_MAX_TURNS = 20  # el hilo se acota a los últimos N turnos


def _new_id() -> str:
    return "cs_" + hashlib.sha256(os.urandom(16)).hexdigest()[:16]


def _blank(session_id: str, tenant_id, user_id, buyer_profile) -> Dict:
    return {"session_id": session_id, "tenant_id": tenant_id, "user_id": user_id,
            "buyer_profile": buyer_profile, "status": "active", "session_version": SESSION_VERSION,
            "working_context": {"active_entity": None, "last_decision_id": None,
                                "last_level": None, "last_intent": None},
            "turns": []}


async def get_or_create(session_id: Optional[str] = None, tenant_id=None, user_id=None,
                        buyer_profile=None) -> Dict:
    """Reanuda la sesión si existe y está activa; en cualquier otro caso abre una nueva."""
    if session_id:
        try:
            from database import db
            doc = await db.copilot_sessions.find_one({"session_id": session_id}, {"_id": 0})
            if doc and doc.get("status") == "active":
                return doc
        except Exception:
            pass
    sid = _new_id()
    sess = _blank(sid, tenant_id, user_id, buyer_profile)
    try:
        from database import db
        from models import now_iso
        now = now_iso()
        await db.copilot_sessions.update_one(
            {"session_id": sid},
            {"$set": {**sess, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True)
    except Exception:
        pass
    return sess


async def update(session_id: Optional[str], context_patch: Optional[Dict] = None,
                 turn: Optional[Dict] = None) -> None:
    """Actualiza working_context y/o añade un turno (read-modify-write, acotado). Nunca lanza."""
    if not session_id:
        return
    try:
        from database import db
        from models import now_iso
        doc = await db.copilot_sessions.find_one({"session_id": session_id})
        if not doc:
            return
        wc = doc.get("working_context") or {}
        if context_patch:
            wc.update({k: v for k, v in context_patch.items() if v is not None})
        turns = doc.get("turns") or []
        if turn:
            turns = (turns + [{**turn, "ts": now_iso()}])[-_MAX_TURNS:]
        await db.copilot_sessions.update_one(
            {"session_id": session_id},
            {"$set": {"working_context": wc, "turns": turns, "updated_at": now_iso()}})
    except Exception:
        pass


async def close(session_id: Optional[str]) -> Dict:
    """Cierra la sesión (logout). Una sesión cerrada no se reanuda."""
    if not session_id:
        return {"closed": False}
    try:
        from database import db
        from models import now_iso
        await db.copilot_sessions.update_one(
            {"session_id": session_id},
            {"$set": {"status": "closed", "updated_at": now_iso()}})
        return {"closed": True, "session_id": session_id}
    except Exception:
        return {"closed": False, "session_id": session_id}
