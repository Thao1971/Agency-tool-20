"""Persistencia idempotente de decisiones (best-effort; no rompe si no hay BBDD)."""

import hashlib
from typing import Dict, Optional
from services.engines.investment_decision import ENGINE_VERSION
from services.engines.investment_decision.scoring import SCORE_METHOD


def decision_id(opportunity_id: str, profile_type: str, engines_used, band: str,
                score: int) -> str:
    raw = f"{opportunity_id}|{profile_type}|{','.join(sorted(engines_used))}|{band}|{score}|{SCORE_METHOD}|{ENGINE_VERSION}"
    return "idec_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


async def save(record: Dict) -> None:
    try:
        from database import db
        from models import now_iso
        record = {**record, "updated_at": now_iso()}
        await db.investment_decisions.update_one(
            {"decision_id": record["decision_id"]}, {"$set": record}, upsert=True)
    except Exception:
        pass  # persistencia opcional en Fase 1


async def get(decision_id_: str) -> Optional[Dict]:
    try:
        from database import db
        return await db.investment_decisions.find_one({"decision_id": decision_id_}, {"_id": 0})
    except Exception:
        return None
