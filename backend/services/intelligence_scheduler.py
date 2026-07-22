"""Intelligence Scheduler — Automatic nightly sync for all intelligence modules.

Schedule (Europe/Madrid timezone, UTC+1/+2):
  - BORME ingestion: Daily 03:00 Madrid (existing scheduler)
  - Sector Intelligence: Daily 04:00 Madrid (~02:00-03:00 UTC)
  - Geo Intelligence: Daily 04:05 Madrid
  - Cross Intelligence: Daily 04:10 Madrid

These modules are derived layers from BORME, INE and other sources.
They must recalculate every night after data updates.
"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_scheduler_running = False

# Schedule: Daily at 02:00 UTC ~ 04:00 Madrid (CET/CEST)
SYNC_HOUR_UTC = 2
CHECK_INTERVAL_SECONDS = 600  # Check every 10 minutes


async def start_intelligence_scheduler():
    """Start the daily intelligence sync scheduler."""
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    logger.info("Intelligence scheduler started (daily ~04:00 Madrid)")
    asyncio.create_task(_scheduler_loop())


async def _scheduler_loop():
    """Main loop — checks every 10 min if it's time to sync."""
    global _scheduler_running
    last_sync_date = None

    while _scheduler_running:
        try:
            now = datetime.now(timezone.utc)
            today_str = now.strftime("%Y%m%d")
            is_sync_hour = now.hour == SYNC_HOUR_UTC

            if is_sync_hour and last_sync_date != today_str:
                logger.info(f"Intelligence scheduler: starting nightly sync ({today_str})")
                await _run_full_sync()
                last_sync_date = today_str
                logger.info(f"Intelligence scheduler: nightly sync completed ({today_str})")

            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

        except Exception as e:
            logger.error(f"Intelligence scheduler error: {e}")
            await asyncio.sleep(300)


async def _run_full_sync():
    """Execute full intelligence recalculation pipeline."""
    from database import db

    try:
        # Step 1: Sector Intelligence
        from services.sector_intelligence_v2 import compute_sector_intelligence_v2
        si = await compute_sector_intelligence_v2()
        await _log_sync("sector_intelligence", "completed", si.get("total", 0))
        logger.info(f"  Sector Intelligence: {si['total']} entries")

        # Step 2: Geo Intelligence
        from services.geo_intelligence import compute_geo_intelligence
        gi = await compute_geo_intelligence()
        await _log_sync("geo_intelligence", "completed", gi.get("total", 0))
        logger.info(f"  Geo Intelligence: {gi['total']} entries")

        # Step 3: Cross Intelligence
        from services.sector_geo_cross import compute_sector_geo_cross
        cx = await compute_sector_geo_cross()
        await _log_sync("cross_intelligence", "completed", cx.get("combinations", 0))
        logger.info(f"  Cross Intelligence: {cx['combinations']} combinations")

        # Step 4: Economic Intelligence Layer
        from services.economic_intelligence import rebuild_economic_metrics, rebuild_economic_signals
        econ = await rebuild_economic_metrics()
        await _log_sync("economic_intelligence", "completed", econ.get("total_metrics", 0))
        logger.info(f"  Economic Intelligence: {econ['total_metrics']} metrics")

        esig = await rebuild_economic_signals()
        logger.info(f"  Economic Signals: {esig['signals_generated']} signals")

        # Step 5: BME Enrichment (daily, only stale/new companies)
        try:
            from services.bme_enrichment import run_full_enrichment
            bme = await run_full_enrichment(max_companies=50)
            logger.info(f"  BME Enrichment: {bme.get('enriched', 0)} companies enriched")
        except Exception as bme_err:
            logger.warning(f"  BME Enrichment skipped: {bme_err}")

    except Exception as e:
        logger.error(f"Intelligence sync failed: {e}")
        await _log_sync("intelligence_pipeline", "failed", 0, str(e))


async def _log_sync(module: str, status: str, entries: int, error: str = None):
    """Log sync event to database."""
    from database import db
    from models import now_iso

    doc = {
        "module": module,
        "status": status,
        "entries": entries,
        "synced_at": now_iso(),
        "trigger": "scheduler",
    }
    if error:
        doc["error"] = error

    await db.intelligence_sync_log.update_one(
        {"module": module},
        {"$set": doc},
        upsert=True,
    )


async def log_manual_sync(module: str, entries: int):
    """Log a manual sync trigger."""
    from database import db
    from models import now_iso

    await db.intelligence_sync_log.update_one(
        {"module": module},
        {"$set": {
            "module": module,
            "status": "completed",
            "entries": entries,
            "synced_at": now_iso(),
            "trigger": "manual",
        }},
        upsert=True,
    )


async def stop_intelligence_scheduler():
    global _scheduler_running
    _scheduler_running = False
    logger.info("Intelligence scheduler stopped")
