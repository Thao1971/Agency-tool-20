"""Precalienta descripciones IA fuera de /ficha, con límites y parada por errores.

Vista previa: python -m scripts.prewarm_company_descriptions --limit 100
Ejecución: NVIDIA_DESC_MODEL=<modelo_verificado> python -m scripts.prewarm_company_descriptions \
    --execute --limit 100 --delay 2
"""
import argparse
import asyncio
import hashlib
import os
import random
from pathlib import Path

from database import db
from services.company_summary import resolve_description
from services.cnae_es import cnae_label_es
from docstudio.model_provider import (COMPANY_DESCRIPTION_PROMPT_VERSION,
                                      NVIDIA_FALLBACK_MODEL)


def _objeto_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def _candidates(seed, priority_cifs):
    cached = {(row["master_id"], row["objeto_hash"], row["prompt_version"])
              async for row in db.company_descriptions.find(
                  {"description": {"$nin": [None, ""]}},
                  {"_id": 0, "master_id": 1, "objeto_hash": 1, "prompt_version": 1})
              if row.get("master_id") and row.get("objeto_hash")
              and row.get("prompt_version") is not None}
    pending = []
    async for row in db.master_companies.find(
            {"objeto_social": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "master_id": 1, "cif_normalized": 1,
             "objeto_social": 1, "web_description": 1, "identity.legal_name": 1,
             "classification.cnae_code": 1}):
        objeto = (row.get("objeto_social") or "").strip()
        if objeto and (row["master_id"], _objeto_hash(objeto),
                       COMPANY_DESCRIPTION_PROMPT_VERSION) not in cached:
            pending.append(row)
    rng = random.Random(seed)
    rng.shuffle(pending)
    priority = set(priority_cifs)
    pending.sort(key=lambda row: row.get("cif_normalized") not in priority)
    return pending


async def main(args):
    priority = []
    if args.priority_cifs:
        priority = [line.strip().upper() for line in Path(args.priority_cifs).read_text().splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    pending = await _candidates(args.seed, priority)
    selected = pending[:args.limit]
    print("pending=%d selected=%d priority=%d execute=%s" %
          (len(pending), len(selected), len(priority), args.execute), flush=True)
    if not args.execute:
        print("Vista previa: ninguna llamada al proveedor ni escritura en caché.", flush=True)
        return
    if not os.environ.get("NVIDIA_API_KEY"):
        raise SystemExit("NVIDIA_API_KEY no configurada")
    model = os.environ.get("NVIDIA_DESC_MODEL")
    if not model or model == NVIDIA_FALLBACK_MODEL:
        raise SystemExit("Configurar NVIDIA_DESC_MODEL con un modelo probado antes de ejecutar")

    successes = failures = consecutive_failures = 0
    for index, row in enumerate(selected, 1):
        objeto = row["objeto_social"].strip()
        identity = {"objeto_social": objeto,
                    "description": row.get("web_description"),
                    "legal_name": (row.get("identity") or {}).get("legal_name")}
        cnae = cnae_label_es((row.get("classification") or {}).get("cnae_code"))
        result = await resolve_description(row["master_id"], identity, cnae,
                                           generate_if_missing=True)
        if result["description_source"] == "ai":
            successes += 1
            consecutive_failures = 0
        else:
            failures += 1
            consecutive_failures += 1
        print("%d/%d cif=%s source=%s ok=%d failures=%d" %
              (index, len(selected), row.get("cif_normalized"),
               result["description_source"], successes, failures), flush=True)
        if consecutive_failures >= args.max_consecutive_failures:
            print("Parado por fallos consecutivos del proveedor.", flush=True)
            break
        if index < len(selected):
            await asyncio.sleep(args.delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Autoriza llamadas al proveedor")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--delay", type=float, default=2.0, help="Segundos entre llamadas")
    parser.add_argument("--seed", type=int, default=150926)
    parser.add_argument("--priority-cifs", help="Archivo con CIFs prioritarios, uno por línea")
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    args = parser.parse_args()
    if args.limit < 1 or args.delay < 0 or args.max_consecutive_failures < 1:
        parser.error("limit y max-consecutive-failures deben ser >0; delay debe ser >=0")
    asyncio.run(main(args))
