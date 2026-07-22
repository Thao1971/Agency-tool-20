"""CNMV + BME daily scheduler — automatic sync, no longer "bajo demanda" only.

Both sources previously depended entirely on someone clicking "Sincronizar" in the
UI (frequency: "Bajo demanda" in services/intelligence_engine/sources/cnmv.py and
bme.py, with ingest_runner=None). That meant data could go stale indefinitely with
no automatic refresh and no visible warning. This mirrors the retry-with-cutoff
pattern already used for BORME (borme/scheduler.py), simplified since neither
source publishes on a fixed daily schedule the way BORME does.

Runs once a day off-peak (04:00 UTC), with up to 3 retries spaced 90 minutes apart
if a run comes back with status "error" (e.g. Chromium not available yet at
container boot). Every attempt is recorded in `scheduler_runs` regardless of
outcome — success, partial, or fatal failure — so staleness is always visible,
never silent.
"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_scheduler_running = False

RUN_HOUR_UTC = 4
RETRY_INTERVAL_MINUTES = 90
MAX_ATTEMPTS_PER_DAY = 3


async def start_cnmv_bme_scheduler():
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    logger.info("CNMV/BME scheduler started (daily ~04:00 UTC, up to 3 reintentos si falla)")
    asyncio.create_task(_scheduler_loop())


async def _scheduler_loop():
    global _scheduler_running
    last_success_date = None
    attempts_today = 0
    attempts_date = None

    while _scheduler_running:
        try:
            now_utc = datetime.now(timezone.utc)
            today_str = now_utc.strftime("%Y%m%d")

            if attempts_date != today_str:
                attempts_today = 0
                attempts_date = today_str

            should_attempt = (
                now_utc.hour >= RUN_HOUR_UTC
                and last_success_date != today_str
                and attempts_today < MAX_ATTEMPTS_PER_DAY
            )

            if should_attempt:
                attempts_today += 1
                logger.info(f"CNMV/BME scheduler: intento {attempts_today}/{MAX_ATTEMPTS_PER_DAY} para {today_str}")

                cnmv_ok = await _run_cnmv()
                bme_ok = await _run_bme()

                if cnmv_ok and bme_ok:
                    last_success_date = today_str
                    logger.info(f"CNMV/BME scheduler: {today_str} completado con exito")
                else:
                    logger.warning(
                        f"CNMV/BME scheduler: {today_str} intento {attempts_today} con fallos "
                        f"(cnmv_ok={cnmv_ok}, bme_ok={bme_ok}). "
                        f"{'Reintentara' if attempts_today < MAX_ATTEMPTS_PER_DAY else 'Sin mas reintentos hoy'}."
                    )

            await asyncio.sleep(RETRY_INTERVAL_MINUTES * 60 if should_attempt else 1800)

        except Exception as e:
            logger.error(f"CNMV/BME scheduler error: {e}")
            await asyncio.sleep(600)


async def _run_cnmv() -> bool:
    from database import db
    from services.cnmv_connector import sync_cnmv_entities

    now = datetime.now(timezone.utc).isoformat()
    try:
        result = await sync_cnmv_entities()
        status = result.get("status")
        await db.scheduler_runs.insert_one({
            "source": "cnmv", "ran_at": now, "status": status,
            "detail": result.get("message") or result.get("errors") or None,
        })
        return status in ("completed", "partial")
    except Exception as e:
        logger.error(f"CNMV scheduler run failed: {e}")
        await db.scheduler_runs.insert_one({
            "source": "cnmv", "ran_at": now, "status": "error", "detail": str(e)[:300],
        })
        return False


async def _run_bme() -> bool:
    from database import db
    from services.bme_connector import sync_bme

    now = datetime.now(timezone.utc).isoformat()
    try:
        result = await sync_bme()
        status = result.get("status")
        await db.scheduler_runs.insert_one({
            "source": "bme", "ran_at": now, "status": status,
            "detail": result.get("message") or result.get("errors") or None,
        })
        return status in ("completed", "partial")
    except Exception as e:
        logger.error(f"BME scheduler run failed: {e}")
        await db.scheduler_runs.insert_one({
            "source": "bme", "ran_at": now, "status": "error", "detail": str(e)[:300],
        })
        return False


async def stop_cnmv_bme_scheduler():
    global _scheduler_running
    _scheduler_running = False
    logger.info("CNMV/BME scheduler stopped")
