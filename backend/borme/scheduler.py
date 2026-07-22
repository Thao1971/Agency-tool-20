"""BORME daily scheduler — automatic ingestion with retry logic."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_scheduler_running = False

# Schedule: first attempt at 03:00 Europe/Madrid, retry every 30min until 10:00
# Europe/Madrid = UTC+1 (winter) or UTC+2 (summer)
# We use UTC offsets: 03:00 Madrid ≈ 01:00-02:00 UTC depending on DST
FIRST_ATTEMPT_UTC_HOUR = 1   # ~03:00 Madrid (CET)
RETRY_INTERVAL_MINUTES = 30
MAX_ATTEMPT_UTC_HOUR = 8     # ~10:00 Madrid (CET)


async def start_borme_scheduler():
    """Start the daily BORME ingestion scheduler."""
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    logger.info("BORME scheduler started (daily at ~03:00 Madrid, retries every 30min until 10:00)")
    asyncio.create_task(_scheduler_loop())


async def _scheduler_loop():
    """Main scheduler loop — checks every 10 minutes if it's time to fetch."""
    global _scheduler_running
    last_fetched_date = None

    while _scheduler_running:
        try:
            now_utc = datetime.now(timezone.utc)
            today_str = now_utc.strftime("%Y%m%d")
            hour_utc = now_utc.hour

            # Only attempt within the window (01:00 - 08:00 UTC ≈ 03:00 - 10:00 Madrid)
            within_window = FIRST_ATTEMPT_UTC_HOUR <= hour_utc <= MAX_ATTEMPT_UTC_HOUR

            # Skip weekends (BORME only publishes on business days)
            is_weekday = now_utc.weekday() < 5

            if within_window and is_weekday and last_fetched_date != today_str:
                logger.info(f"BORME scheduler: attempting fetch for {today_str}")

                from database import db
                from borme.fetcher import fetch_summary, extract_items_from_summary

                # Check if today's BORME is available
                summary = fetch_summary(today_str)
                if summary:
                    items = extract_items_from_summary(summary)
                    if items:
                        logger.info(f"BORME scheduler: summary available for {today_str} with {len(items)} items. Processing...")

                        # Import and run the processor
                        from borme.routes import _process_date
                        result = await _process_date(today_str, force=False)

                        events_new = result.get("events_new", 0)
                        pdfs_ok = result.get("pdfs_ok", 0)

                        if events_new > 0 or result.get("skipped"):
                            last_fetched_date = today_str
                            logger.info(f"BORME scheduler: {today_str} completed — {pdfs_ok} PDFs, {events_new} events")

                            # Log to DB
                            await db.borme_scheduler_logs.insert_one({
                                "date": today_str,
                                "status": "completed",
                                "attempt_time": now_utc.isoformat(),
                                "pdfs_processed": pdfs_ok,
                                "events_extracted": events_new,
                                "message": f"Auto-fetch successful: {pdfs_ok} PDFs, {events_new} events"
                            })
                        else:
                            logger.warning(f"BORME scheduler: {today_str} processed but 0 events. Will retry.")
                            await db.borme_scheduler_logs.insert_one({
                                "date": today_str,
                                "status": "retry",
                                "attempt_time": now_utc.isoformat(),
                                "message": "Summary available but 0 events extracted"
                            })
                    else:
                        logger.info(f"BORME scheduler: summary for {today_str} has 0 items. Will retry in {RETRY_INTERVAL_MINUTES}min.")
                        await db.borme_scheduler_logs.insert_one({
                            "date": today_str,
                            "status": "retry",
                            "attempt_time": now_utc.isoformat(),
                            "message": "Summary available but 0 items"
                        })
                else:
                    logger.info(f"BORME scheduler: no summary yet for {today_str}. Will retry in {RETRY_INTERVAL_MINUTES}min.")
                    from database import db
                    await db.borme_scheduler_logs.insert_one({
                        "date": today_str,
                        "status": "not_available",
                        "attempt_time": now_utc.isoformat(),
                        "message": "Summary not yet published"
                    })

            # Sleep: 30 minutes during window, 10 minutes outside
            sleep_seconds = RETRY_INTERVAL_MINUTES * 60 if within_window else 600
            await asyncio.sleep(sleep_seconds)

        except Exception as e:
            logger.error(f"BORME scheduler error: {e}")
            await asyncio.sleep(300)  # 5min on error


async def stop_borme_scheduler():
    global _scheduler_running
    _scheduler_running = False
    logger.info("BORME scheduler stopped")
