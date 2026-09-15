"""Worker AISLADO de una entrega Iberinform (subproceso, NO en el event loop del backend).

Lo lanzan los endpoints admin /upload-delivery (modo disco) y /process-from-storage (modo
R2 streaming). Ejecuta las MISMAS 3 fases que hacía `_run_delivery` en proceso — legacy
(companies_master) + intelligence (Sector/Geo) + moderno (run_bootstrap_tab: rebuild
completo + ownership + señales + índice semántico) — pero fuera del backend, para que una
reingesta de 25k (o futuras de millones) no bloquee ni ralentice el resto de peticiones a
intel.arroba.com mientras corre.

Reporta progreso en la MISMA colección `iberinform_delivery_runs` con el mismo shape
(steps/status/duration_s), así el polling GET /upload-delivery/{run_id} del frontend no
cambia. Mismo enfoque que scripts/prod_seed_eav.py (que ya se aísla igual).

Uso:
  python -m scripts.run_delivery_worker --run-id <id> --mode dir --data-dir <ruta>
  python -m scripts.run_delivery_worker --run-id <id> --mode r2  --object-key <key>
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))

from database import db
from models import now_iso
from services.iberinform_processor import process_real_iberinform_tab_directory
from services.sector_intelligence_v2 import compute_sector_intelligence_v2
from services.geo_intelligence import compute_geo_intelligence


async def _run(run_id: str, mode: str, data_dir: str = None, object_key: str = None) -> None:
    t0 = time.time()
    steps = []

    async def _set(patch):
        await db.iberinform_delivery_runs.update_one({"run_id": run_id}, {"$set": patch}, upsert=True)

    delivery = None
    try:
        # ── Fase 1 · legacy (companies_master) ──
        if mode == "r2":
            from services.data_layer.ingestion.r2_delivery import ZipDelivery
            delivery = ZipDelivery(object_key)
            if not delivery.has("Datos_GENERALES.tab"):
                raise RuntimeError(
                    f"El objeto R2 '{object_key}' no contiene Datos_GENERALES.tab — no parece "
                    "una entrega de Iberinform reconocible.")
            legacy = await process_real_iberinform_tab_directory(source_version=run_id, delivery=delivery)
        else:
            legacy = await process_real_iberinform_tab_directory(data_dir, source_version=run_id)
        steps.append({"step": "legacy_ingest", "status": "ok" if legacy.get("status") != "error" else "error", "result": legacy})
        await _set({"steps": steps})
        if legacy.get("status") == "error":
            raise RuntimeError(f"legacy ingest failed: {legacy.get('message')}")

        # ── Fase 2 · intelligence legacy (Sector/Geo) ──
        sector_result = await compute_sector_intelligence_v2()
        geo_result = await compute_geo_intelligence()
        steps.append({"step": "legacy_intelligence", "status": "ok",
                      "result": {"sector_total": sector_result.get("total"), "geo_total": geo_result.get("total")}})
        await _set({"steps": steps})

        # ── Fase 3 · moderno (delta-scoped: master_companies + ratios + ownership + señales + semántico) ──
        from services.data_layer import bootstrap_delta
        if mode == "r2":
            modern = await bootstrap_delta.run_bootstrap_delta(
                run_id=f"{run_id}_modern", source_version=run_id, delivery=delivery,
                steps=steps, set_fn=_set)
        else:
            modern = await bootstrap_delta.run_bootstrap_delta(
                directory=data_dir, run_id=f"{run_id}_modern", source_version=run_id,
                steps=steps, set_fn=_set)
        modern_summary = {k: v for k, v in modern.items() if k != "steps"}
        steps.append({"step": "modern_ingest", "status": "ok" if modern.get("status") != "failed" else "error", "result": modern_summary})

        latest_step_status = {}
        for s in steps:
            latest_step_status[s["step"]] = s["status"]
        status = "completed" if all(v == "ok" for v in latest_step_status.values()) else "completed_with_errors"
        await _set({"status": status, "finished_at": now_iso(),
                    "duration_s": round(time.time() - t0, 1), "steps": steps})
    except Exception as e:  # noqa: BLE001 — persistido, nunca revienta silenciosamente
        steps.append({"step": "error", "status": "error", "error": str(e)})
        await _set({"status": "failed", "finished_at": now_iso(),
                    "duration_s": round(time.time() - t0, 1), "error": str(e), "steps": steps})
        raise
    finally:
        if delivery is not None:
            try:
                delivery.close()
            except Exception:
                pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--mode", required=True, choices=["dir", "r2"])
    ap.add_argument("--data-dir")
    ap.add_argument("--object-key")
    a = ap.parse_args()
    asyncio.run(_run(a.run_id, a.mode, data_dir=a.data_dir, object_key=a.object_key))
