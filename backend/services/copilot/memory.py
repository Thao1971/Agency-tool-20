"""ARROBA Copilot — memoria de usuario (copilot-memory-v1).

Ámbito POR USUARIO (`tenant_id + user_id`): dos analistas del mismo tenant NO comparten memoria.
Guarda SOLO lo que el usuario CONFIGURA explícitamente (perfil de comprador por defecto, rol,
nivel de autonomía, mandato, preferencias de comunicación) — esto NO caduca (hasta que él lo cambie).
Lo que se APRENDE del comportamiento (preferencias/sesgo, 90 días, tope ±10 %) es Fase 4, no aquí.

Best-effort: si no hay BBDD disponible degrada a defaults sin romper. Nunca fabrica hechos ni toca
los scores del comité. Ver memory/ARROBA_COPILOT_MEMORY_SESSIONS_PERSONALIZATION.md.
"""

from typing import Dict, Optional

MEMORY_VERSION = "copilot-memory-v1"

# Nivel de autonomía por defecto: 1 · Informa (decisión de Daniel, 2026-07-31).
DEFAULT_AUTONOMY = 1
AUTONOMY_LEVELS = {
    0: "silent",                 # solo responde si se le pregunta
    1: "inform",                 # avisa de hechos/riesgos; no propone acciones
    2: "propose",                # recomienda decisiones; el usuario ejecuta
    3: "execute_with_permission",# puede pedir autorización y ejecutar tras el sí
    4: "autonomous_bounded",     # ejecuta por su cuenta solo acciones sin efecto externo
}

# Whitelist de campos configurables (nada sensible; sin PII ni secretos).
_CONFIG_FIELDS = {"buyer_profile", "role", "autonomy_level", "mandate", "preferences", "language"}


def _defaults() -> Dict:
    return {"buyer_profile": None, "role": None, "autonomy_level": DEFAULT_AUTONOMY,
            "mandate": {}, "preferences": {}, "language": "es"}


async def get_user_memory(tenant_id: Optional[str], user_id: Optional[str]) -> Dict:
    """Devuelve la memoria configurada del usuario (o defaults). Nunca lanza."""
    base = _defaults()
    if not (tenant_id and user_id):
        return base
    try:
        from database import db
        doc = await db.copilot_user_memory.find_one(
            {"tenant_id": tenant_id, "user_id": user_id}, {"_id": 0})
        if doc:
            for k in _CONFIG_FIELDS:
                if k in doc and doc[k] is not None:
                    base[k] = doc[k]
    except Exception:
        pass
    return base


def _sanitize(patch: Dict) -> Dict:
    clean = {k: v for k, v in (patch or {}).items() if k in _CONFIG_FIELDS}
    if "autonomy_level" in clean:
        try:
            lvl = int(clean["autonomy_level"])
            clean["autonomy_level"] = lvl if lvl in AUTONOMY_LEVELS else DEFAULT_AUTONOMY
        except Exception:
            clean.pop("autonomy_level", None)
    return clean


async def set_user_memory(tenant_id: Optional[str], user_id: Optional[str], patch: Dict) -> Dict:
    """Upsert de campos CONFIGURADOS (whitelist). Devuelve la memoria resultante. Nunca lanza."""
    clean = _sanitize(patch)
    if not (tenant_id and user_id and clean):
        return await get_user_memory(tenant_id, user_id)
    try:
        from database import db
        from models import now_iso
        await db.copilot_user_memory.update_one(
            {"tenant_id": tenant_id, "user_id": user_id},
            {"$set": {"tenant_id": tenant_id, "user_id": user_id, **clean, "updated_at": now_iso()},
             "$setOnInsert": {"memory_version": MEMORY_VERSION}},
            upsert=True)
    except Exception:
        pass
    try:
        from services.copilot import governance as GOV
        await GOV.audit("memory_set", tenant_id, user_id, {"fields": sorted(clean.keys())})
    except Exception:
        pass
    return await get_user_memory(tenant_id, user_id)
