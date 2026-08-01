"""ARROBA Copilot — gobernanza de la memoria (copilot-governance-v1).

Transparencia y control del usuario sobre lo que el Copilot sabe de él (§6 del canon):
  - `whats_known`: panel "lo que sé de ti" (resumen legible).
  - `export_user`: volcado completo (portabilidad).
  - `forget_user`: borrado por ámbito (derecho al olvido).
  - `audit` / `read_audit`: registro de escrituras de memoria de aprendizaje y acciones de gobernanza.
Todo POR USUARIO y por tenant. Best-effort sobre BBDD. NUNCA cruza datos entre usuarios/tenants.
Ver memory/ARROBA_COPILOT_MEMORY_SESSIONS_PERSONALIZATION.md.
"""

import time
from typing import Dict, List, Optional

GOVERNANCE_VERSION = "copilot-governance-v1"

# Ámbitos de borrado → colecciones afectadas.
_SCOPES = {
    "memory": ["copilot_user_memory"],
    "sessions": ["copilot_sessions"],
    "entities": ["copilot_entity_memory"],
    "feedback": ["copilot_feedback"],
}
_ALL = ["copilot_user_memory", "copilot_sessions", "copilot_entity_memory", "copilot_feedback"]


def _now() -> str:
    try:
        from models import now_iso
        return now_iso()
    except Exception:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


async def audit(action: str, tenant_id, user_id, meta: Optional[Dict] = None) -> None:
    """Registra una escritura/acción (append-only). Nunca lanza."""
    if not (tenant_id and user_id):
        return
    try:
        from database import db
        await db.copilot_audit.insert_one(
            {"action": action, "tenant_id": tenant_id, "user_id": user_id,
             "meta": meta or {}, "at": _now(), "ts": time.time()})
    except Exception:
        pass


async def _dump(coll: str, tenant_id, user_id) -> List[Dict]:
    try:
        from database import db
        out = []
        async for d in db[coll].find({"tenant_id": tenant_id, "user_id": user_id}, {"_id": 0}).limit(2000):
            out.append(d)
        return out
    except Exception:
        return []


async def whats_known(tenant_id, user_id) -> Dict:
    """Resumen legible de lo que el Copilot sabe de este usuario (para el panel)."""
    from services.copilot import memory as MEMORY
    from services.copilot import feedback as FB
    mem = await MEMORY.get_user_memory(tenant_id, user_id)
    bias = await FB.compute_bias(tenant_id, user_id)
    sessions = await _dump("copilot_sessions", tenant_id, user_id)
    entities = await _dump("copilot_entity_memory", tenant_id, user_id)
    feedback = await _dump("copilot_feedback", tenant_id, user_id)
    return {
        "governance_version": GOVERNANCE_VERSION,
        "user_memory": mem,
        "ranking_bias": FB.summarize(bias),
        "sessions": [{"session_id": s.get("session_id"), "status": s.get("status"),
                      "created_at": s.get("created_at"), "turns": len(s.get("turns") or [])}
                     for s in sessions],
        "entities": [{"company_id": e.get("company_id"), "last": e.get("last"),
                      "analyses": len(e.get("snapshots") or [])} for e in entities],
        "feedback_events": len(feedback),
    }


async def export_user(tenant_id, user_id) -> Dict:
    """Volcado completo (portabilidad de datos)."""
    data = {c: await _dump(c, tenant_id, user_id) for c in _ALL}
    data["audit"] = await _dump("copilot_audit", tenant_id, user_id)
    await audit("export", tenant_id, user_id, {"collections": _ALL})
    return {"governance_version": GOVERNANCE_VERSION, "tenant_id": tenant_id,
            "user_id": user_id, "exported_at": _now(), "data": data}


async def forget_user(tenant_id, user_id, scope: str = "all") -> Dict:
    """Borra la memoria del usuario por ámbito (derecho al olvido). scope: all|memory|sessions|entities|feedback."""
    if not (tenant_id and user_id):
        return {"forgotten": False, "reason": "missing_identity"}
    targets = _ALL if scope == "all" else _SCOPES.get(scope)
    if not targets:
        return {"forgotten": False, "reason": "unknown_scope", "valid": ["all", *_SCOPES]}
    deleted: Dict[str, int] = {}
    try:
        from database import db
        for c in targets:
            res = await db[c].delete_many({"tenant_id": tenant_id, "user_id": user_id})
            deleted[c] = getattr(res, "deleted_count", None)
    except Exception:
        pass
    await audit("forget", tenant_id, user_id, {"scope": scope, "deleted": deleted})
    return {"forgotten": True, "scope": scope, "deleted": deleted}


async def read_audit(tenant_id, user_id, limit: int = 100) -> List[Dict]:
    rows = await _dump("copilot_audit", tenant_id, user_id)
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return rows[:limit]
