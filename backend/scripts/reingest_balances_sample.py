"""Validación de muestra (B5): re-ingesta del EAV COMPLETO de balance+cash-flow para N
empresas, rebuild del master de esas empresas, y verificación del contrato arroba.v2.

La ingesta del 2026-07-22 corrió con una versión antigua del normalizador que solo
guardaba los ~6 códigos canónicos por empresa-año. El código actual de
`ingest_balances_file` ya guarda el EAV completo (~168 códigos) pero nunca se re-ejecutó.
Este script replica EXACTAMENTE esa lógica (mismos normalize_cif/parse_amount/derive_metrics)
pero filtrada a una muestra, para validar antes del full run sobre las 25k.
"""

import asyncio
import sys
from collections import defaultdict

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from database import db
from models import now_iso
from services.data_layer.normalize import normalize_cif
from services.data_layer.ingestion.csv_stream import detect_encoding
from services.data_layer.ingestion.account_map import parse_amount, derive_metrics
from services.data_layer.ingestion.bulk import BulkUpserter
from services.data_layer.master.master_builder import rebuild_master
from services.engines.financial import engine as E, metrics as M

RAW = "/app/data/muestra_25000/Datos_BALANCES.tab"
SAMPLE_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 500
BASIS = "individual"


def _s(row, key):
    v = row.get(key)
    return str(v).strip() if v is not None else ""


def _int(v):
    f = parse_amount(v)
    return int(f) if f is not None else None


async def pick_sample():
    """First SAMPLE_SIZE normalized CIFs present in master_companies (so rebuild+analyze work)."""
    master_cifs = set(await db.master_companies.distinct("cif_normalized"))
    import csv
    enc = detect_encoding(RAW)
    chosen = []
    seen = set()
    with open(RAW, encoding=enc, errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for r in reader:
            cifn = normalize_cif(_s(r, "REG_NUMBER"))
            if not cifn or cifn in seen or cifn not in master_cifs:
                continue
            seen.add(cifn)
            chosen.append(cifn)
            if len(chosen) >= SAMPLE_SIZE:
                break
    return set(chosen)


async def reingest(sample):
    """Replica ingest_balances_file pero filtrado al set `sample`."""
    import csv
    enc = detect_encoding(RAW)
    up = BulkUpserter(db.norm_financials)
    acc = defaultdict(dict)
    cif_by_norm = {}
    rows = kept = 0
    with open(RAW, encoding=enc, errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for r in reader:
            rows += 1
            cif = _s(r, "REG_NUMBER")
            code = _s(r, "BALANCE_SHEET_ITEM")
            if not cif or not code:
                continue
            cifn = normalize_cif(cif)
            if not cifn or cifn not in sample:
                continue
            year = _int(r.get("BALANCE_SHEET_YEAR"))
            val = parse_amount(r.get("BALANCE_SHEET_ITEM_VALUE"))
            if year is None or val is None:
                continue
            cif_by_norm[cifn] = cif
            acc[(cifn, year)][code] = val
            kept += 1
    now = now_iso()
    for (cifn, year), accounts in acc.items():
        metrics = derive_metrics(accounts)
        doc = {
            "cif_normalized": cifn, "cif": cif_by_norm.get(cifn), "year": year, "basis": BASIS,
            "accounts": accounts, **metrics,
            "source": "iberinform", "source_version": "iberinform_tab_96664fb7",
            "pipeline_version": "ingest-tab-v1-reingest", "updated_at": now,
        }
        up.upsert({"cif_normalized": cifn, "year": year, "basis": BASIS}, doc)
        await up.maybe_flush()
    await up.flush()
    return {"rows_scanned": rows, "rows_kept": kept, "company_years": len(acc), **up.stats()}


async def verify(sample):
    sample = list(sample)
    # coverage in norm_financials
    n_ca = await db.norm_financials.count_documents(
        {"cif_normalized": {"$in": sample}, "accounts.12000": {"$exists": True}})
    n_cl = await db.norm_financials.count_documents(
        {"cif_normalized": {"$in": sample}, "accounts.32000": {"$exists": True}})
    n_cf = await db.norm_financials.count_documents(
        {"cif_normalized": {"$in": sample}, "accounts.61500": {"$exists": True}})
    n_efe = await db.norm_financials.count_documents(
        {"cif_normalized": {"$in": sample}, "accounts.91000": {"$exists": True}})
    print(f"\n=== COBERTURA norm_financials (muestra {len(sample)} empresas) ===")
    print(f"  con current_assets(12000): {n_ca}")
    print(f"  con current_liabilities(32000): {n_cl}")
    print(f"  con cash-flow OCF(61500): {n_cf}")
    print(f"  con EFE(91000): {n_efe}")

    # master latest coverage (liquidity ratios)
    liq = await db.master_companies.count_documents(
        {"cif_normalized": {"$in": sample}, "financials.latest.ratios.current_ratio": {"$ne": None}})
    wc = await db.master_companies.count_documents(
        {"cif_normalized": {"$in": sample}, "financials.latest.ratios.working_capital": {"$ne": None}})
    print(f"\n=== COBERTURA master_companies.financials.latest.ratios ===")
    print(f"  con current_ratio: {liq}")
    print(f"  con working_capital: {wc}")

    # deep verify one company with cash-flow, one with balance
    async def show(cifn, tag):
        prof = await E.analyze(cifn)
        if not prof:
            print(f"  [{tag}] {cifn}: SIN PERFIL")
            return
        st = prof.get("statements") or {}
        bs = st.get("balance_sheet") or {}
        cf = st.get("cash_flow")
        ratios = prof.get("ratios") or {}
        val = prof.get("valuation") or {}
        print(f"\n--- [{tag}] {cifn} — {prof.get('identity',{}).get('name')} ---")
        print(f"  balance_sheet: current_assets={bs.get('current_assets')} current_liabilities={bs.get('current_liabilities')} "
              f"st_debt={bs.get('st_debt')} lt_debt={bs.get('lt_debt')} financial_debt={bs.get('financial_debt')}")
        print(f"  cash_flow: {'PRESENTE ('+str([r['key'] for r in cf['rows']])+')' if cf else st.get('cash_flow_note','None')}")
        print(f"  ratios liquidez: current_ratio={ratios.get('current_ratio',{}).get('value')} "
              f"(pctile={ratios.get('current_ratio',{}).get('percentile')}) "
              f"working_capital={ratios.get('working_capital',{}).get('value')} "
              f"ccc={ratios.get('cash_conversion_cycle',{}).get('value')}")
        print(f"  valuation: method={val.get('method')} net_debt_used(EV={val.get('enterprise_value')}, equity={val.get('equity_value')})")

    cf_doc = await db.norm_financials.find_one(
        {"cif_normalized": {"$in": sample}, "accounts.61500": {"$exists": True}})
    if cf_doc:
        await show(cf_doc["cif_normalized"], "CASH-FLOW")
    ca_doc = await db.norm_financials.find_one(
        {"cif_normalized": {"$in": sample}, "accounts.12000": {"$exists": True}})
    if ca_doc:
        await show(ca_doc["cif_normalized"], "BALANCE")


async def main():
    print(f"Seleccionando muestra de {SAMPLE_SIZE} empresas...")
    sample = await pick_sample()
    print(f"Muestra: {len(sample)} CIFs")
    print("Re-ingiriendo EAV completo de balances...")
    stats = await reingest(sample)
    print(f"  {stats}")
    print("Reconstruyendo master (force) para la muestra...")
    r = await rebuild_master(scope="full", cif_list=list(sample), force=True)
    print(f"  {r}")
    await verify(sample)

if __name__ == "__main__":
    asyncio.run(main())
