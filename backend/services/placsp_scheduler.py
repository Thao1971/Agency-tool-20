"""PLACSP weekly scheduler — automatic re-sync, no longer "bajo demanda" only.

Found during the 2026-07-23 sources audit: PLACSP (public_procurement_contracts,
183K+ contratos) had NO periodic scheduler and NO manual sync button in the
frontend (ProcurementPage.js only displayed `last_sync`, read-only). The only
population path was a ONE-TIME auto-populate at server startup
(`if placsp_count < 1000: sync_placsp(...)` in server.py), which never runs
again once the collection has more than 1000 contracts — meaning PLACSP could
never refresh again for the entire life of the deployment unless someone called
the API directly. A manual "Sincronizar PLACSP" button was added to
ProcurementPage.js in the same pass; this scheduler adds the automatic side.

`sync_placsp()` (services/placsp_connector.py) defaults to current+previous year
and upserts by `expediente` (idempotent, confirmed safe to re-run), and already
writes its own log entry to `procurement_sync_logs` with a real status
(completed/partial/error — fixed in Actualización v5), so this scheduler doesn't
need its own audit collection; it only decides WHEN to call it.

Weekly cadence (not daily): PLACSP publishes bulk ZIP dumps, not a live feed —
daily re-downloads would be wasted bandwidth for data that doesn't change that
often. Mirrors the retry-with-cutoff style of cnmv_bme_scheduler.py, simplified
since PLACSP doesn't need same-day retries (a failed week just tries again next
week; the manual button covers urgent re-syncs)."""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_scheduler_running = False

CHECK_INTERVAL_SECONDS = 6 * 3600  # check every 6h
STALE_AFTER_SECONDS = 7 * 24 * 3600  # re-sync if last run older than 7 days


async def start_placsp_scheduler():
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    logger.info("PLACSP scheduler started (re-sync semanal, si el ultimo run tiene mas de 7 dias)")
    asyncio.create_task(_scheduler_loop())


async def _scheduler_loop():
    global _scheduler_running
    while _scheduler_running:
        try:
            if await _is_stale():
                await _run_sync()
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except Exception as e:
            logger.error(f"PLACSP scheduler error: {e}")
            await asyncio.sleep(1800)


async def _is_stale() -> bool:
    from database import db

    last = await db.procurement_sync_logs.find_one({}, {"_id": 0, "synced_at": 1}, sort=[("synced_at", -1)])
    if not last or not last.get("synced_at"):
        return True
    try:
        last_dt = datetime.fromisoformat(last["synced_at"].replace("Z", "+00:00"))
    except Exception:
        return True
    return (datetime.now(timezone.utc) - last_dt).total_seconds() > STALE_AFTER_SECONDS


async def _run_sync() -> None:
    from services.placsp_connector import sync_placsp

    logger.info("PLACSP scheduler: iniciando re-sync semanal")
    try:
        result = await sync_placsp()
        logger.info(f"PLACSP scheduler: {result.get('status')} — "
                    f"{result.get('total_imported', 0)} importados, {result.get('total_skipped', 0)} omitidos")
    except Exception as e:
        # sync_placsp() already logs its own procurement_sync_logs entry per year/attempt
        # internally; this catches anything that escapes that (e.g. a totally unexpected
        # crash) so the scheduler loop itself never dies from one bad run.
        logger.error(f"PLACSP scheduler: re-sync failed: {e}")


async def stop_placsp_scheduler():
    global _scheduler_running
    _scheduler_running = False
    logger.info("PLACSP scheduler stopped")
