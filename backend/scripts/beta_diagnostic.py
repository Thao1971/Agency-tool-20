"""Diagnóstico integral para Beta (B-2 Fase 0):
1) Selecciona 5 CIFs reales de master_companies por tramo (grande/mid/SME ind/SME serv/micro).
2) Por cada uno verifica el contrato completo (analyze + identity + ficha blocks).
3) Confirma por qué los 4 CIFs de Beta dan 404.
4) Inventario real de Atlas (colecciones + nº docs + campos poblados clave).
"""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from database import db
from services.engines.financial import engine as FE
from services.engines.recommendation import engine as REC
from routes.company_intelligence import _build as build_identity

FAIL = ["A08363419", "A28017895", "B65076193", "B95758389"]


async def pick_by_band(lo, hi, section=None, need_officers=False, exclude=None):
    q = {"financials.latest.revenue": {"$ne": None}}
    if lo is not None:
        q["financials.latest.revenue"] = {"$gte": lo}
        if hi is not None:
            q["financials.latest.revenue"]["$lt"] = hi
    if section:
        q["classification.cnae_section"] = section
    if need_officers:
        q["officers_count"] = {"$gt": 0}
    if exclude:
        q["cif_normalized"] = {"$nin": exclude}
    # prefer ones with ownership + officers for a richer demo
    cur = db.master_companies.find(q, {"_id": 0, "cif_normalized": 1}).sort("officers_count", -1).limit(1)
    docs = await cur.to_list(1)
    return docs[0]["cif_normalized"] if docs else None


async def show(cif, tag):
    prof = await FE.analyze(cif)
    if not prof:
        print(f"\n### [{tag}] {cif}: NO RESUELVE")
        return None
    master = await db.master_companies.find_one({"cif_normalized": cif})
    ident = build_identity(master).model_dump() if master else {}
    st = prof.get("statements") or {}
    bs = st.get("balance_sheet") or {}
    cf = st.get("cash_flow")
    val = prof.get("valuation") or {}
    fq = prof.get("financial_quality") or {}
    rk = prof.get("ranking") or {}
    # ficha blocks counts
    own_n = await db.norm_ownership.count_documents({"src_cif": cif, "relationship_type": "shareholder"})
    off_n = await db.norm_officers.count_documents({"cif_normalized": cif})
    sig_n = await db.signals.count_documents({"master_id": master["master_id"], "status": "active"}) if master else 0
    buyers = await REC.buyers(cif, 5)
    bcount = (buyers or {}).get("count", 0)
    print(f"\n### [{tag}] {cif} — {prof['identity'].get('name')}")
    print(f"  revenue={prof.get('kpis',{}).get('revenue')} ebitda={prof.get('kpis',{}).get('ebitda')} section={prof['identity'].get('cnae_section')} prov={prof['identity'].get('provincia')}")
    print(f"  has_financials={prof.get('has_financials')} confidence={prof.get('confidence')}")
    print(f"  identity.corporate_purpose? {bool(ident.get('corporate_purpose'))}  identity.description? {bool(ident.get('description'))}")
    print(f"  balance debt breakdown: st_debt={bs.get('st_debt')} lt_debt={bs.get('lt_debt')} financial_debt={bs.get('financial_debt')} total_liab={bs.get('total_liabilities')}")
    print(f"  cash_flow: {'PRESENTE' if cf else 'None (abreviadas)'}")
    print(f"  ratios.current_ratio={prof.get('ratios',{}).get('current_ratio',{}).get('value')} (pctile={prof.get('ratios',{}).get('current_ratio',{}).get('percentile')})")
    print(f"  valuation.method={val.get('method')} benchmark?={bool(val.get('benchmark'))} methodology?={bool(val.get('methodology'))} scenarios?={bool(val.get('scenarios'))}")
    print(f"  financial_quality: score={fq.get('score')} assessment?={bool(fq.get('assessment'))} verdict?={bool(fq.get('verdict'))} weaknesses={len(fq.get('weaknesses') or [])} risks={len(fq.get('risks') or [])}")
    print(f"  ranking.explain={rk.get('explain')}")
    print(f"  ficha counts: shareholders={own_n} officers={off_n} signals={sig_n} buyers={bcount}")
    return {"cif": cif, "name": prof['identity'].get('name'), "tag": tag, "buyers": bcount}


async def inventory():
    print("\n\n================ INVENTARIO ATLAS ================")
    names = await db.list_collection_names()
    rows = []
    for n in sorted(names):
        try:
            c = await db[n].estimated_document_count()
        except Exception:
            c = -1
        rows.append((n, c))
    rows.sort(key=lambda x: -x[1])
    for n, c in rows:
        if c > 0:
            print(f"  {n:40s} {c:>12,}")

    print("\n--- master_companies: campos poblados ---")
    T = await db.master_companies.count_documents({})
    checks = {
        "financials.latest.revenue": {"financials.latest.revenue": {"$ne": None}},
        "financials.latest.ratios.current_ratio": {"financials.latest.ratios.current_ratio": {"$ne": None}},
        "objeto_social": {"objeto_social": {"$nin": [None, ""]}},
        "web_description": {"web_description": {"$nin": [None, ""]}},
        "ownership.shareholders>=1": {"ownership.shareholders.0": {"$exists": True}},
        "officers_count>0": {"officers_count": {"$gt": 0}},
        "contact.web": {"contact.web": {"$nin": [None, ""]}},
        "size.employees_total": {"size.employees_total": {"$ne": None}},
    }
    for label, q in checks.items():
        n = await db.master_companies.count_documents(q)
        print(f"  {label:45s} {n:>7,} / {T:,}  ({round(n/T*100,1)}%)")

    print("\n--- norm_financials: cobertura EAV ---")
    NT = await db.norm_financials.count_documents({})
    for label, code in [("total assets(10000)","10000"),("current_assets(12000)","12000"),
                        ("current_liab(32000)","32000"),("st_debt(32300)","32300"),
                        ("lt_debt(31200)","31200"),("cashflow_OCF(61500)","61500"),
                        ("ratios(precalc)","__ratios__")]:
        if code == "__ratios__":
            n = await db.norm_financials.count_documents({"ratios": {"$exists": True}})
        else:
            n = await db.norm_financials.count_documents({f"accounts.{code}": {"$exists": True}})
        print(f"  {label:25s} {n:>7,} / {NT:,}")


async def main():
    print("================ 5 CIFs POR TRAMO ================")
    chosen = []
    grande = await pick_by_band(80_000_000, None, exclude=chosen)
    if grande: chosen.append(grande)
    mid = await pick_by_band(30_000_000, 80_000_000, exclude=chosen)
    if mid: chosen.append(mid)
    sme_ind = await pick_by_band(10_000_000, 50_000_000, section="C", need_officers=True, exclude=chosen)
    if sme_ind: chosen.append(sme_ind)
    sme_serv = await pick_by_band(5_000_000, 30_000_000, section="J", need_officers=True, exclude=chosen)
    if not sme_serv:
        sme_serv = await pick_by_band(5_000_000, 30_000_000, section="M", need_officers=True, exclude=chosen)
    if sme_serv: chosen.append(sme_serv)
    micro = await pick_by_band(200_000, 3_000_000, need_officers=True, exclude=chosen)
    if micro: chosen.append(micro)

    tags = ["GRANDE (>80M€)", "MID-CAP (30-80M€)", "SME INDUSTRIAL (C, 10-50M€)",
            "SME SERVICIOS (J/M, 5-30M€)", "MICRO (<3M€)"]
    out = []
    for cif, tag in zip(chosen, tags):
        r = await show(cif, tag)
        if r: out.append(r)

    print("\n================ DIAGNÓSTICO 404 (CIFs de Beta) ================")
    for cif in FAIL:
        m = await db.master_companies.find_one({"cif_normalized": cif}, {"_id": 0, "cif_normalized": 1})
        print(f"  {cif}: {'EN MASTER' if m else 'NO está en el master (→ analyze/ficha 404 esperado)'}")

    await inventory()

    print("\n================ RESUMEN 5 CIFs ================")
    for r in out:
        print(f"  {r['cif']}  {r['tag']:30s} buyers={r['buyers']}  {r['name']}")

asyncio.run(main())
