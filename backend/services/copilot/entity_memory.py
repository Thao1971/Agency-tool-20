"""ARROBA Copilot — memoria de entidad (copilot-entity-memory-v1).

Historia clínica por compañía, POR USUARIO (`tenant_id + user_id + company_id`). Cada vez que el comité
decide sobre una empresa, se archiva un snapshot ligero (banda, score, fecha, decision_id) y se compara
con el anterior para contar la EVOLUCIÓN ("mejoró desde el último análisis").

No fabrica nada: solo archiva lo que el comité ya calculó y lo pone al lado de lo anterior. Este
histórico NO caduca (información de negocio, decisión de Daniel 2026-07-31). Best-effort sobre BBDD.
Ver memory/ARROBA_COPILOT_MEMORY_SESSIONS_PERSONALIZATION.md (§1.3).
"""

from typing import Dict, List, Optional

ENTITY_MEMORY_VERSION = "copilot-entity-memory-v1"
_MAX_SNAPSHOTS = 50

# Orden de mejor (bandas del comité) para saber si sube o baja.
_BAND_RANK = {"REJECT": 0, "PASS": 1, "EXPLORE": 2, "PROCEED_WITH_CONDITIONS": 3, "PROCEED": 4}
_DIR_ES = {"improved": "ha mejorado", "worsened": "ha empeorado", "stable": "se mantiene"}


def _now() -> str:
    try:
        from models import now_iso
        return now_iso()
    except Exception:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


def _key(tenant_id, user_id, company_id) -> Dict:
    return {"tenant_id": tenant_id, "user_id": user_id, "company_id": company_id}


def _snapshot(decision: Dict) -> Dict:
    try:
        score = int(round(float(decision.get("investment_score"))))
    except Exception:
        score = None
    return {"at": _now(), "decision_id": decision.get("decision_id"),
            "recommendation": decision.get("recommendation"), "score": score,
            "confidence": decision.get("confidence")}


def _delta(prev: Optional[Dict], cur: Dict) -> Dict:
    if not prev:
        return {"first": True}
    sf, st = prev.get("score"), cur.get("score")
    bf, bt = prev.get("recommendation"), cur.get("recommendation")
    rf, rt = _BAND_RANK.get(bf, -1), _BAND_RANK.get(bt, -1)
    score_delta = (st - sf) if (isinstance(sf, int) and isinstance(st, int)) else None
    if rt > rf or (rt == rf and (score_delta or 0) > 0):
        direction = "improved"
    elif rt < rf or (score_delta or 0) < 0:
        direction = "worsened"
    else:
        direction = "stable"
    return {"first": False, "band_changed": bf != bt, "band_from": bf, "band_to": bt,
            "score_from": sf, "score_to": st, "score_delta": score_delta, "direction": direction}


def _narrative(prev: Optional[Dict], cur: Dict, d: Dict) -> str:
    if d.get("first"):
        return "Primer análisis registrado para esta compañía."
    when = (prev.get("at") or "")[:10]
    verb = _DIR_ES.get(d["direction"], "ha cambiado")
    return (f"Desde el último análisis ({when}) {verb}: "
            f"de {d['band_from']} ({d['score_from']}) a {d['band_to']} ({d['score_to']}).")


def latest_narrative(prev: Dict) -> str:
    when = (prev.get("at") or "")[:10]
    return (f"Último análisis registrado: {prev.get('recommendation')} "
            f"({prev.get('score')}) el {when}.")


async def latest(tenant_id, user_id, company_id) -> Optional[Dict]:
    if not (tenant_id and user_id and company_id):
        return None
    try:
        from database import db
        doc = await db.copilot_entity_memory.find_one(_key(tenant_id, user_id, company_id), {"_id": 0})
        if doc:
            snaps = doc.get("snapshots") or []
            return doc.get("last") or (snaps[-1] if snaps else None)
    except Exception:
        pass
    return None


async def history(tenant_id, user_id, company_id, limit: int = 20) -> List[Dict]:
    if not (tenant_id and user_id and company_id):
        return []
    try:
        from database import db
        doc = await db.copilot_entity_memory.find_one(_key(tenant_id, user_id, company_id), {"_id": 0})
        snaps = (doc or {}).get("snapshots") or []
        return list(reversed(snaps))[:limit]      # más reciente primero
    except Exception:
        return []


async def record_decision(tenant_id, user_id, company_id, decision: Dict) -> Dict:
    """Archiva la decisión y devuelve la evolución vs. el análisis anterior. Nunca lanza."""
    prev = await latest(tenant_id, user_id, company_id)
    snap = _snapshot(decision)
    if tenant_id and user_id and company_id:
        try:
            from database import db
            key = _key(tenant_id, user_id, company_id)
            doc = await db.copilot_entity_memory.find_one(key)
            snaps = ((doc or {}).get("snapshots") or []) + [snap]
            snaps = snaps[-_MAX_SNAPSHOTS:]
            now = _now()
            await db.copilot_entity_memory.update_one(
                key,
                {"$set": {**key, "snapshots": snaps, "last": snap, "updated_at": now,
                          "entity_memory_version": ENTITY_MEMORY_VERSION},
                 "$setOnInsert": {"created_at": now}},
                upsert=True)
        except Exception:
            pass
    d = _delta(prev, snap)
    return {"previous": prev, "current": snap, "delta": d, "narrative": _narrative(prev, snap, d)}
