"""Watchlist Scheduler (Q7) — periodic in-app alert sweep.

Same in-process asyncio pattern as `intelligence_scheduler.py`/`borme/scheduler.py`/
`services/datacomex_scheduler.py` (no Celery, no system cron, one `while True` loop per
process). Runs far more often than the nightly intelligence sync because checking for
new signals against a small watchlist is cheap — it's an indexed lookup, not a
recomputation (see `services/watchlist.py::sync_alerts_all()`).
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

_scheduler_running = False
CHECK_INTERVAL_SECONDS = 900  # 15 minutes


async def start_watchlist_scheduler():
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    logger.info("Watchlist scheduler started (sweep every 15 min)")
    asyncio.create_task(_scheduler_loop())


async def _scheduler_loop():
    global _scheduler_running
    from services.watchlist import sync_alerts_all

    while _scheduler_running:
        try:
            result = await sync_alerts_all()
            if result["alerts_created"]:
                logger.info(f"Watchlist scheduler: {result['alerts_created']} new alert(s) "
                            f"across {result['users_checked']} watcher(s)")
        except Exception as e:
            logger.error(f"Watchlist scheduler error: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def stop_watchlist_scheduler():
    global _scheduler_running
    _scheduler_running = False
    logger.info("Watchlist scheduler stopped")
