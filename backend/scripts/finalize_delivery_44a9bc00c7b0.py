"""Red de seguridad efímera (Daniel 2026-09-11): espera a que el worker de la
entrega 20260821_base.zip termine y, si el run quedó en 'running' pero el
bootstrap moderno acabó OK, lo marca 'completed'. No toca datos, solo el run doc."""
import asyncio
import os
import time

from database import db

RUN_ID = "delivery_44a9bc00c7b0"
WORKER_PID = 2156


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


async def main():
    # espera (máx ~3h) a que el worker termine
    for _ in range(1080):
        if not _alive(WORKER_PID):
            break
        await asyncio.sleep(10)
    d = await db.iberinform_delivery_runs.find_one({"run_id": RUN_ID}, {"_id": 0})
    br = await db.bootstrap_runs.find_one({"run_id": f"{RUN_ID}_modern"}, {"_id": 0})
    if not d:
        return
    if d.get("status") == "running":
        boot_ok = bool(br) and br.get("status") in ("ok", "completed", "done")
        new_status = "completed" if boot_ok else "completed_with_warnings"
        await db.iberinform_delivery_runs.update_one(
            {"run_id": RUN_ID},
            {"$set": {"status": new_status,
                      "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "finalized_by": "safety_watcher"}})


if __name__ == "__main__":
    asyncio.run(main())
