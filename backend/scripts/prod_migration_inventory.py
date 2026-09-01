"""Inventario READ-ONLY para verificar el estado de la migración legacy→canónica.

NO escribe nada: solo count_documents / find / distinct / aggregate.

Uso:
  # contra la base por defecto (la del .env — en preview es la LOCAL):
  cd /app/backend && python -m scripts.prod_migration_inventory

  # contra PRODUCCIÓN (Arroba-pro): pasa el URI de Atlas y el nombre de la BD:
  cd /app/backend && python -m scripts.prod_migration_inventory "<ATLAS_URI_READONLY>" "<DB_NAME>"
  # (o por entorno)
  MONGO_URL="<ATLAS_URI_READONLY>" DB_NAME="<DB_NAME>" python -m scripts.prod_migration_inventory
"""

import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient


def _conn():
    uri = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MONGO_URL")
    dbname = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DB_NAME")
    if not uri or not dbname:
        raise SystemExit("Falta MONGO_URL y/o DB_NAME (por argv o entorno).")
    host = uri.split("@")[-1].split("/")[0]
    print(f"→ Conectando a DB='{dbname}' host='{host}'  (srv={'mongodb+srv' in uri})\n", flush=True)
    return AsyncIOMotorClient(uri, serverSelectionTimeoutMS=15000)[dbname]


async def main():
    db = _conn()

    # 1-3. Conteos
    cm = await db.companies_master.count_documents({})
    mc = await db.master_companies.count_documents({})
    cc = await db.company_classifications.count_documents({})
    print(f"1) companies_master.countDocuments({{}})       = {cm:,}")
    print(f"2) master_companies.countDocuments({{}})        = {mc:,}")
    print(f"3) company_classifications.countDocuments({{}}) = {cc:,}\n")

    # 4. Solapamiento por cif_normalized (master_companies vs companies_master)
    print("4) Solapamiento por cif_normalized (master_companies → companies_master):", flush=True)
    cm_cifs = set()
    async for d in db.companies_master.find(
            {"cif_normalized": {"$ne": None}}, {"_id": 0, "cif_normalized": 1}):
        c = d.get("cif_normalized")
        if c:
            cm_cifs.add(c)
    print(f"   - cif_normalized distintos en companies_master (no nulos): {len(cm_cifs):,}")

    mc_total = mc
    mc_null = 0
    mc_match = 0
    mc_nomatch = 0
    async for d in db.master_companies.find({}, {"_id": 0, "cif_normalized": 1}):
        c = d.get("cif_normalized")
        if not c:
            mc_null += 1
        elif c in cm_cifs:
            mc_match += 1
        else:
            mc_nomatch += 1
    print(f"   - master_companies TOTAL:                       {mc_total:,}")
    print(f"   - CON match en companies_master:                {mc_match:,}")
    print(f"   - SIN match en companies_master (cif no nulo):  {mc_nomatch:,}")
    print(f"   - master_companies sin cif_normalized (nulo):   {mc_null:,}")
    pct = (100 * mc_match / mc_total) if mc_total else 0
    print(f"   - cobertura de match:                           {pct:.1f}%\n")

    # 5. Documento de ejemplo de company_classifications con axis='sector'
    print("5) Ejemplo company_classifications axis='sector' (para confirmar label_es):", flush=True)
    doc = await db.company_classifications.find_one({"axis": "sector"}, {"_id": 0})
    if not doc:
        # por si el campo se llama distinto, probamos alternativas comunes
        alt = await db.company_classifications.find_one(
            {"$or": [{"dimension": "sector"}, {"axis_id": "sector"}]}, {"_id": 0})
        doc = alt
    if doc:
        print(f"   - keys: {list(doc.keys())}")
        print(f"   - label_es presente: {'label_es' in doc}  -> valor: {doc.get('label_es')!r}")
        import json
        print("   - documento completo:")
        print(json.dumps(doc, ensure_ascii=False, indent=2, default=str))
    else:
        print("   - No se encontró ningún documento con axis='sector'.")
        sample = await db.company_classifications.find_one({}, {"_id": 0})
        print(f"   - keys de un doc cualquiera de la colección: {list((sample or {}).keys())}")

    print("\n=== FIN (solo lectura, nada modificado) ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
