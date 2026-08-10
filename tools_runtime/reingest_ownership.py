"""Re-ingesta idempotente de ownership (ACCIONISTAS + PARTICIPADAS) desde el directorio
de muestra + rebuild de la propiedad en master para las empresas afectadas. AISLADO
(fuera de /app/backend, no dispara --reload). Confirma que el pipeline de ownership
está verde y reporta cobertura (subirá cuando se suba una entrega con más accionistas).
"""
import asyncio
import sys
import uuid

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from database import db
from services.data_layer.ingestion.iberinform_tab_ingest import (
    ingest_accionistas_file, ingest_participadas_file)
from services.data_layer.master.master_builder import rebuild_master

DIR = "/app/data/muestra_25000"


async def main():
    job = str(uuid.uuid4())
    sv = "iberinform_tab_96664fb7"
    acc = await ingest_accionistas_file(f"{DIR}/Datos_ACCIONISTAS.tab", sv, job)
    print("ACCIONISTAS:", acc, flush=True)
    par = await ingest_participadas_file(f"{DIR}/Datos_PARTICIPADAS.tab", sv, job)
    print("PARTICIPADAS:", par, flush=True)

    src = await db.norm_ownership.distinct("src_cif")
    print(f"norm_ownership src companies: {len(src)}", flush=True)
    r = await rebuild_master(scope="full", cif_list=src, force=True)
    print("rebuild master (ownership cifs):", r, flush=True)

    with_sh = await db.master_companies.count_documents({"ownership.shareholders.0": {"$exists": True}})
    with_inv = await db.master_companies.count_documents({"ownership.investees.0": {"$exists": True}})
    total_edges = await db.norm_ownership.count_documents({})
    print(f"COBERTURA ownership: master con accionistas={with_sh} · con participadas={with_inv} · "
          f"aristas norm_ownership={total_edges}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
