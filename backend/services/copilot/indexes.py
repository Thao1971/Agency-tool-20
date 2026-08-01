"""Índices de las colecciones del Copilot (best-effort, idempotente).

Se llama en el startup del server. Único en `copilot_user_memory` por (tenant,user) para evitar
duplicados; compuestos por tenant+user en el resto para consultas rápidas y aisladas; índice por `ts`
en feedback/audit para la ventana temporal y la purga. Nunca bloquea el arranque.
"""

_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    from database import db
    try:
        await db.copilot_sessions.create_index("session_id", unique=True)
        await db.copilot_sessions.create_index([("tenant_id", 1), ("user_id", 1), ("status", 1)])

        await db.copilot_user_memory.create_index(
            [("tenant_id", 1), ("user_id", 1)], unique=True)

        await db.copilot_entity_memory.create_index(
            [("tenant_id", 1), ("user_id", 1), ("company_id", 1)], unique=True)

        await db.copilot_feedback.create_index([("tenant_id", 1), ("user_id", 1), ("ts", -1)])

        await db.copilot_audit.create_index([("tenant_id", 1), ("user_id", 1), ("ts", -1)])

        await db.copilot_metrics.create_index([("tenant_id", 1), ("ts", -1)])
        _INDEXED = True
    except Exception:
        # best-effort: si falla (p. ej. sin BBDD en tests), no rompe nada
        pass
