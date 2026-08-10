"""Siembra/actualiza la base a la que apunta el backend (preview local o el Atlas de
producción) con la re-ingesta EAV completa (balance + cash-flow) + ownership +
marcado is_listed(BME) + backfill LIGERO de ratios en master (para percentiles).
Escribe progreso en `eav_reingest_runs`.

Se ejecuta como SUBPROCESO AISLADO (lo lanza el endpoint admin /reingest-eav) para NO
bloquear el event loop del backend. Idempotente.

NOTA: NO usa `rebuild_master` completo (reescribe el doc entero de 25k empresas con 13
índices → inviable en Atlas). En su lugar hace un backfill dirigido de
`financials.latest.ratios` vía bulk_write (campo NO indexado) — rápido y con progreso.

Uso: python -m scripts.prod_seed_eav <run_id> <ownership 0/1> <listed 0/1>
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))

from pymongo import UpdateOne

from database import db
from models import now_iso
from services.data_layer.ingestion.iberinform_tab_ingest import (
    ingest_balances_file, ingest_accionistas_file, ingest_participadas_file)
from services.data_layer.normalize import name_key
from services.engines.financial import metrics as _M, ratios_library as _R

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "muestra_25000"
SV = "iberinform_tab_96664fb7"


async def _set(run_id, **kw):
    await db.eav_reingest_runs.update_one(
        {"run_id": run_id}, {"$set": {**kw, "updated_at": now_iso()}})


async def _mark_listed():
    n = 0
    async for b in db.bme_companies.find({}, {"_id": 0}):
        nm = name_key(b.get("company_name"))
        if not nm:
            continue
        doc = await db.master_companies.find_one({"name_key": nm}, {"_id": 0, "cif_normalized": 1})
        if not doc:
            continue
        market = ("BME (Mercado Continuo)" if b.get("listed_in_bme_principal")
                  else "BME Growth" if b.get("listed_in_growth")
                  else "BME Scaleup" if b.get("listed_in_scaleup")
                  else b.get("market") or b.get("market_segment") or "BME")
        await db.master_companies.update_one(
            {"cif_normalized": doc["cif_normalized"]},
            {"$set": {"is_listed": True, "listed_market": market, "isin": b.get("isin"),
                      "listed_source": "bme", "updated_at": now_iso()}})
        n += 1
    return n


async def _backfill_ratios(run_id):
    """$set financials.latest.ratios (+fcf/cash_conversion) por empresa con balance.
    Un solo cursor + bulk_write en lotes → rápido en Atlas y con progreso."""
    # elegir, por cif, el mejor doc (individual > consolidado, año más reciente)
    best = {}
    async for f in db.norm_financials.find(
            {"accounts.10000": {"$exists": True}},
            {"_id": 0, "cif_normalized": 1, "basis": 1, "year": 1, "accounts": 1}):
        cif = f.get("cif_normalized")
        if not cif:
            continue
        rank = (1 if f.get("basis") == "individual" else 0, f.get("year") or 0)
        cur = best.get(cif)
        if cur is None or rank > cur[0]:
            best[cif] = (rank, f)

    ops, updated = [], 0
    for cif, (_, f) in best.items():
        ym = _M._year_metrics(f.get("accounts") or {})
        ratios = {k: v["value"] for k, v in _R.compute_all(ym, None).items()
                  if v.get("value") is not None}
        if not ratios:
            continue
        setter = {"financials.latest.ratios": ratios, "updated_at": now_iso()}
        for extra in ("free_cash_flow", "cash_conversion"):
            if ym.get(extra) is not None:
                setter[f"financials.latest.{extra}"] = ym[extra]
        ops.append(UpdateOne({"cif_normalized": cif}, {"$set": setter}))
        if len(ops) >= 1000:
            res = await db.master_companies.bulk_write(ops, ordered=False)
            updated += res.modified_count
            ops = []
            await _set(run_id, step=f"backfill_ratios ({updated})")
    if ops:
        res = await db.master_companies.bulk_write(ops, ordered=False)
        updated += res.modified_count
    return {"candidates": len(best), "ratios_backfilled": updated}


async def main(run_id, do_ownership, do_listed):
    t0 = time.time()
    try:
        await _set(run_id, status="running", step="balances")
        bal = await ingest_balances_file(str(SAMPLE_DIR / "Datos_BALANCES.tab"), SV, run_id)

        own = None
        if do_ownership:
            await _set(run_id, step="ownership")
            acc = await ingest_accionistas_file(str(SAMPLE_DIR / "Datos_ACCIONISTAS.tab"), SV, run_id)
            par = await ingest_participadas_file(str(SAMPLE_DIR / "Datos_PARTICIPADAS.tab"), SV, run_id)
            own = {"accionistas": acc, "participadas": par}

        listed = 0
        if do_listed:
            await _set(run_id, step="is_listed")
            listed = await _mark_listed()

        # índices (idempotente; acelera queries del contrato)
        await _set(run_id, step="ensure_indexes")
        for col, field in [("norm_company", "cif_normalized"), ("norm_financials", "cif_normalized"),
                           ("norm_officers", "cif_normalized"), ("norm_ownership", "src_cif"),
                           ("master_companies", "cif_normalized"), ("master_companies", "name_key")]:
            try:
                await db[col].create_index(field)
            except Exception:
                pass

        await _set(run_id, step="backfill_ratios")
        rb = await _backfill_ratios(run_id)

        cov = {
            "norm_current_assets": await db.norm_financials.count_documents({"accounts.12000": {"$exists": True}}),
            "norm_cashflow_ocf": await db.norm_financials.count_documents({"accounts.61500": {"$exists": True}}),
            "master_current_ratio": await db.master_companies.count_documents({"financials.latest.ratios.current_ratio": {"$ne": None}}),
            "master_is_listed": await db.master_companies.count_documents({"is_listed": True}),
        }
        await _set(run_id, status="completed", step="done", balances=bal, ownership=own,
                   is_listed_marked=listed, ratios=rb, coverage=cov,
                   elapsed_s=round(time.time() - t0, 1))
    except Exception as e:
        await _set(run_id, status="failed", error=str(e), elapsed_s=round(time.time() - t0, 1))
        raise


if __name__ == "__main__":
    rid = sys.argv[1]
    ownership = sys.argv[2] == "1" if len(sys.argv) > 2 else True
    listed = sys.argv[3] == "1" if len(sys.argv) > 3 else True
    asyncio.run(main(rid, ownership, listed))
