"""(d) Marca is_listed / listed_market en master_companies cruzando con bme_companies
por name_key. Idempotente. AISLADO (fuera de /app/backend, no dispara --reload).

Realidad actual: la muestra Iberinform 25k casi no contiene cotizadas (solo ~1 solape),
pero deja el campo poblado y listo para cuando llegue una entrega que sí las incluya.

Uso: cd /app && PYTHONDONTWRITEBYTECODE=1 python tools_runtime/mark_listed_from_bme.py
"""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from database import db
from models import now_iso
from services.data_layer.normalize import name_key


def _market_label(b: dict):
    if b.get("listed_in_bme_principal"):
        return "BME (Mercado Continuo)"
    if b.get("listed_in_growth"):
        return "BME Growth"
    if b.get("listed_in_scaleup"):
        return "BME Scaleup"
    return b.get("market") or b.get("market_segment") or "BME"


async def main():
    matched = 0
    async for b in db.bme_companies.find({}, {"_id": 0}):
        nm = name_key(b.get("company_name"))
        if not nm:
            continue
        doc = await db.master_companies.find_one({"name_key": nm}, {"_id": 0, "cif_normalized": 1})
        if not doc:
            continue
        await db.master_companies.update_one(
            {"cif_normalized": doc["cif_normalized"]},
            {"$set": {"is_listed": True, "listed_market": _market_label(b),
                      "isin": b.get("isin"), "listed_source": "bme", "updated_at": now_iso()}})
        matched += 1
        print(f"  marcada cotizada: {b.get('company_name')} -> {doc['cif_normalized']} ({_market_label(b)})")
    total_listed = await db.master_companies.count_documents({"is_listed": True})
    print(f"DONE matched={matched} total_is_listed={total_listed}")


if __name__ == "__main__":
    asyncio.run(main())
