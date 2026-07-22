"""Public-sources scheduler — automatiza las ingestas reales y registra cada
corrida en er_audit_logs con trazabilidad completa.

Frecuencias:
- Ayudas (BDNS): diaria a las 04:30 Madrid
- Empleo (INE/SEPE): mensual día 5
- Territoriales (INE): anual día 1 de febrero

Cada ejecución persiste un audit log con source_name, source_url, started_at,
finished_at, inserted/updated/error count, status y duration_ms.
"""

import asyncio
import logging
from datetime import datetime, timezone

from database import db
from models import new_id

logger = logging.getLogger(__name__)

_scheduler_running = False


async def _run_and_audit(name: str, runner, performed_by: str = "intelligence_engine_scheduler") -> dict:
    """Ejecuta una ingesta y registra audit log. Idempotente.

    `name` es el nombre de la colección (no el de la fuente del engine), de modo
    que `action` coincida con `META['audit_action']` y la UI lea last_run tanto de
    corridas del scheduler como de disparos manuales.
    """
    started = datetime.now(timezone.utc)
    log = {
        "log_id": new_id(),
        "action": f"public_source_ingest_{name}",
        "source_name": name,
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "performed_by": performed_by,
        "timestamp": started.isoformat().replace("+00:00", "Z"),
    }
    try:
        result = await runner()
        finished = datetime.now(timezone.utc)
        log.update({
            "finished_at": finished.isoformat().replace("+00:00", "Z"),
            "duration_ms": int((finished - started).total_seconds() * 1000),
            "source_url": result.get("source") or result.get("source_url"),
            "inserted_count": result.get("inserted", 0),
            "updated_count": result.get("updated", 0),
            "error_count": result.get("errors", 0),
            "status": result.get("status", "ok"),
            "result": result,
        })
    except Exception as e:
        log.update({
            "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "error",
            "error_count": 1,
            "reason": str(e)[:300],
        })
        logger.exception(f"Ingest {name} failed")
    await db.er_audit_logs.insert_one({**log})
    return log


async def start_public_sources_scheduler():
    """Inicia un loop ligero que dispara las 3 ingestas a su cadencia.

    Cadencias simplificadas (en lugar de cron real, hacemos checks horarios):
      - Ayudas: cada 24h
      - Empleo: cada 30 días
      - Territoriales: cada 365 días
    El primer disparo ocurre al arrancar si la última ingesta correspondiente
    es más antigua que la ventana.
    """
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    logger.info("Public sources scheduler started (ayudas:24h, empleo:30d, territoriales:365d)")

    from services.intelligence_engine.ingestion import (
        ingest_ayudas_subvenciones, ingest_estadisticas_empleo, ingest_estadisticas_territoriales,
    )

    async def loop():
        cadences = {
            "ayudas_subvenciones_publicas": (ingest_ayudas_subvenciones, 24 * 3600),
            "estadisticas_empleo": (ingest_estadisticas_empleo, 30 * 24 * 3600),
            "estadisticas_territoriales": (ingest_estadisticas_territoriales, 365 * 24 * 3600),
        }
        while _scheduler_running:
            try:
                for name, (runner, window_sec) in cadences.items():
                    last = await db.er_audit_logs.find_one(
                        {"action": f"public_source_ingest_{name}", "status": "ok"},
                        sort=[("started_at", -1)],
                    )
                    if last:
                        try:
                            last_dt = datetime.fromisoformat(last["started_at"].replace("Z", "+00:00"))
                            if (datetime.now(timezone.utc) - last_dt).total_seconds() < window_sec:
                                continue
                        except Exception:
                            pass
                    await _run_and_audit(name, runner)
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            # Wake every hour
            await asyncio.sleep(3600)

    asyncio.create_task(loop())


async def stop_public_sources_scheduler():
    global _scheduler_running
    _scheduler_running = False
