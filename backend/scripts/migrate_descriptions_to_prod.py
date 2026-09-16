"""Migración idempotente de descripciones válidas Preview(local) -> Producción(Atlas).

NO ejecuta nada por defecto (dry-run). NO borra ni sobrescribe documentos existentes
en destino (usa $setOnInsert): solo inserta los que faltan, por lo que es re-ejecutable
sin duplicar ni regenerar.

Comprobación previa (por documento) contra PRODUCCIÓN:
  1) el master_id existe en master_companies de destino;
  2) objeto_hash coincide con el hash del objeto social VIGENTE en destino.
Si no se cumple, el documento se OMITE y se reporta (no se migra una descripción a una
empresa inexistente o cuyo objeto social ha cambiado).

Uso (las credenciales del destino se pasan por entorno en el momento, NUNCA se guardan):
    TARGET_MONGO_URL="mongodb+srv://...atlas..." TARGET_DB_NAME="arroba_agency_tool" \
        python -m scripts.migrate_descriptions_to_prod            # dry-run (informe)
    TARGET_MONGO_URL="..." TARGET_DB_NAME="arroba_agency_tool" \
        python -m scripts.migrate_descriptions_to_prod --execute  # inserta faltantes

Documento "válido" = prompt_version == 3, description_source == "ai", description no vacía.
Campos preservados: master_id, objeto_hash, prompt_version, description,
description_source, model, fallback_used, generated_at.
"""
import argparse
import asyncio
import hashlib
import os

from motor.motor_asyncio import AsyncIOMotorClient

_COLL = "company_descriptions"
_MASTER = "master_companies"
_PRESERVE = ["master_id", "objeto_hash", "prompt_version", "description",
             "description_source", "model", "fallback_used", "generated_at"]
_VALID = {"prompt_version": 3, "description_source": "ai",
          "description": {"$nin": [None, ""]}}


def _objeto_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


async def main(execute: bool):
    src_url = os.environ["MONGO_URL"]
    src_db_name = os.environ["DB_NAME"]
    tgt_url = os.environ.get("TARGET_MONGO_URL")
    tgt_db_name = os.environ.get("TARGET_DB_NAME", src_db_name)
    if not tgt_url:
        raise SystemExit("Falta TARGET_MONGO_URL (URI del Atlas de producción)")

    src_db = AsyncIOMotorClient(src_url)[src_db_name]
    tgt_db = AsyncIOMotorClient(tgt_url)[tgt_db_name]
    src, tgt = src_db[_COLL], tgt_db[_COLL]

    valid = await src.count_documents(_VALID)
    print(f"origen={src_db_name}(local)  destino={tgt_db_name}(atlas)  coleccion={_COLL}")
    print(f"documentos VÁLIDOS en origen (pv=3, source=ai, desc no vacía): {valid}")

    to_insert = existing = inserted = 0
    skip_bad_key = skip_no_master = skip_hash_mismatch = 0
    reports = []

    async for d in src.find(_VALID, {"_id": 0}):
        mid = d.get("master_id")
        oh = d.get("objeto_hash")
        if not mid or not oh:
            skip_bad_key += 1
            continue
        # --- comprobación previa contra producción ---
        prod_master = await tgt_db[_MASTER].find_one({"master_id": mid}, {"_id": 0, "objeto_social": 1})
        if not prod_master:
            skip_no_master += 1
            reports.append((mid, "master_id ausente en producción"))
            continue
        current_hash = _objeto_hash((prod_master.get("objeto_social") or "").strip())
        if current_hash != oh:
            skip_hash_mismatch += 1
            reports.append((mid, f"objeto_hash no coincide (origen={oh} vigente={current_hash})"))
            continue
        # --- idempotencia ---
        key = {"master_id": mid, "objeto_hash": oh, "prompt_version": d.get("prompt_version")}
        if await tgt.find_one(key, {"_id": 1}):
            existing += 1
            continue
        to_insert += 1
        if execute:
            doc = {k: d.get(k) for k in _PRESERVE}
            await tgt.update_one(key, {"$setOnInsert": doc}, upsert=True)
            inserted += 1

    print(f"ya presentes en destino (se omiten): {existing}")
    print(f"omitidos sin clave válida (master_id/objeto_hash): {skip_bad_key}")
    print(f"omitidos por master_id ausente en producción: {skip_no_master}")
    print(f"omitidos por objeto_hash desactualizado: {skip_hash_mismatch}")
    if execute:
        print(f"INSERTADOS en destino: {inserted}")
        print(f"total destino ahora: {await tgt.count_documents({})}")
    else:
        print(f"[DRY-RUN] se INSERTARÍAN: {to_insert}  (usa --execute para escribir)")
    if reports:
        print("\n--- documentos omitidos por comprobación previa (primeros 20) ---")
        for mid, why in reports[:20]:
            print(f"  master_id={mid} :: {why}")
        if len(reports) > 20:
            print(f"  ... y {len(reports) - 20} más")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true", help="Autoriza la escritura en destino")
    args = p.parse_args()
    asyncio.run(main(args.execute))
