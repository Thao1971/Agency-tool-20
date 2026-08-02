"""INE Business Demography Monthly Scheduler — sincroniza DIRCE + Sociedades Mercantiles sola.

Horario: día 18, 04:00 UTC (~06:00 Madrid). El INE publica las Sociedades Mercantiles mensuales
con ~1,5 meses de retraso (típicamente hacia mediados de mes), así que el día 18 asegura que el
dato del mes anterior ya está disponible. Idempotente: `sync_business_demography` hace upsert por
(indicator_key, date), no duplica.
"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_scheduler_running = False
SYNC_DAY = 18
SYNC_HOUR_UTC = 4  # ~06:00 Madrid
CHECK_INTERVAL = 3600  # revisa cada hora


async def start_ine_demography_scheduler():
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    logger.info("INE demography scheduler started (monthly, day 18 ~06:00 Madrid)")
    asyncio.create_task(_loop())


async def _loop():
    global _scheduler_running
    last_sync_month = None

    while _scheduler_running:
        try:
            now = datetime.now(timezone.utc)
            month_key = now.strftime("%Y-%m")

            if now.day == SYNC_DAY and now.hour == SYNC_HOUR_UTC and last_sync_month != month_key:
                logger.info(f"INE demography scheduler: starting monthly sync ({month_key})")
                from services.business_demography import sync_business_demography
                result = await sync_business_demography(nult=36)
                if result.get("status") == "completed":
                    logger.info(f"INE demography sync OK: {result.get('total')} points "
                                f"(created={result.get('created_points')}, "
                                f"dissolved={result.get('dissolved_points')}, "
                                f"active={result.get('active_points')})")
                else:
                    logger.error(f"INE demography sync failed: {result.get('error', 'unknown')}")
                last_sync_month = month_key

            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"INE demography scheduler error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)


async def stop_ine_demography_scheduler():
    global _scheduler_running
    _scheduler_running = False
    logger.info("INE demography scheduler stopped")
