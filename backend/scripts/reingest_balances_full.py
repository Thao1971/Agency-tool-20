"""FULL run (B5): re-ingesta del EAV COMPLETO de balances sobre las ~25k en Atlas +
rebuild del master. Usa las funciones reales de producción (ingest_balances_file +
rebuild_master) para máxima fidelidad. Idempotente.
"""

import asyncio
import sys
import uuid
import time

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from database import db
from services.data_layer.ingestion.iberinform_tab_ingest import ingest_balances_file
from services.data_layer.master.master_builder import rebuild_master

RAW = "/app/data/muestra_25000/Datos_BALANCES.tab"


async def heartbeat(info):
    print(f"  [master] {info}", flush=True)


async def main():
    t0 = time.time()
    job_id = str(uuid.uuid4())
    sv = "iberinform_tab_96664fb7"  # mantiene continuidad con la entrega real existente
    print(f"[{time.strftime('%H:%M:%S')}] Re-ingiriendo EAV completo de balances (full)...", flush=True)
    stats = await ingest_balances_file(RAW, sv, job_id)
    print(f"[{time.strftime('%H:%M:%S')}] balances: {stats} ({round(time.time()-t0)}s)", flush=True)

    print(f"[{time.strftime('%H:%M:%S')}] Rebuild master (force=True, full)...", flush=True)
    r = await rebuild_master(scope="full", force=True, heartbeat=heartbeat)
    print(f"[{time.strftime('%H:%M:%S')}] master: {r} ({round(time.time()-t0)}s)", flush=True)

    # coverage summary
    ca = await db.norm_financials.count_documents({"accounts.12000": {"$exists": True}})
    cl = await db.norm_financials.count_documents({"accounts.32000": {"$exists": True}})
    cf = await db.norm_financials.count_documents({"accounts.61500": {"$exists": True}})
    mca = await db.master_companies.count_documents({"financials.latest.ratios.current_ratio": {"$ne": None}})
    print(f"[{time.strftime('%H:%M:%S')}] COBERTURA FINAL: norm current_assets={ca} current_liab={cl} cashflow_OCF={cf} | master current_ratio={mca}", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] DONE en {round(time.time()-t0)}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
