"""DataComex Monthly Scheduler — Automatic sync on day 15 of each month.

Schedule: Day 15, 03:00 UTC (~05:00 Madrid)
DataComex publishes monthly data with ~2 month lag.
Day 15 ensures the previous month's data is available.
"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_scheduler_running = False
SYNC_DAY = 15
SYNC_HOUR_UTC = 3  # ~05:00 Madrid
CHECK_INTERVAL = 3600  # Check every hour


async def start_datacomex_scheduler():
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    logger.info("DataComex scheduler started (monthly, day 15 ~05:00 Madrid)")
    asyncio.create_task(_loop())


async def _loop():
    global _scheduler_running
    last_sync_month = None

    while _scheduler_running:
        try:
            now = datetime.now(timezone.utc)
            month_key = now.strftime("%Y-%m")

            if now.day == SYNC_DAY and now.hour == SYNC_HOUR_UTC and last_sync_month != month_key:
                logger.info(f"DataComex scheduler: starting monthly sync ({month_key})")

                from services.datacomex_playwright import sync_via_playwright, post_sync_rebuild
                result = await sync_via_playwright()

                if result["status"] == "completed":
                    rebuild = await post_sync_rebuild()
                    logger.info(f"DataComex sync OK: {result['records']} records → {rebuild['economic_metrics']} econ metrics")
                elif result["status"] == "unchanged":
                    logger.info("DataComex: data unchanged since last sync")
                else:
                    logger.error(f"DataComex sync failed: {result.get('error', 'unknown')}")

                last_sync_month = month_key

            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"DataComex scheduler error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)


async def stop_datacomex_scheduler():
    global _scheduler_running
    _scheduler_running = False
    logger.info("DataComex scheduler stopped")
