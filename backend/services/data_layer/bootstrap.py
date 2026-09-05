"""Reproducible Data Layer bootstrap (Track A).

Reconstructs the ENTIRE canonical Data Layer from the official Iberinform Valu8 source files,
with NO manual steps and NO simulated data. A completely empty environment can be rebuilt with a
single call to `run_bootstrap()` (or `python -m services.data_layer.bootstrap`).

Chain (in order):
  1. ingestion        raw CSV → norm_company / norm_financials / norm_ownership / norm_officers
  2. master builder    norm_* → master_companies  (includes Entity Resolution + financial projection)
  3. ownership graph   master_companies → group_id (union-find)
  4. signal builder    master_companies → signals[] + signal_score
  5. semantic index    LSA embeddings + clusters (powers Search / Recommend / Semantic)
  6. verification      counts + coverage + public-contract smoke + canonical validation set

The financial projection is part of step 2 (`_fin_summary` in master_builder): raw financial rows
present in `norm_financials` are projected into `master_companies.financials.{latest,history}`.
Only REAL, ingested fiscal years are shown — never interpolated or estimated.
"""
import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from database import db
from models import now_iso

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = str(ROOT_DIR / "tests" / "fixtures" / "iberinform_sample")
BOOTSTRAP_VERSION = "bootstrap-v1"

# A well-known real company present in the official source, used for the smoke check.
SMOKE_CIF = "B59022921"  # TRANSPORTS LA MUNTANYESA


def source_dir() -> str:
    return os.environ.get("DATA_LAYER_SOURCE_DIR") or DEFAULT_SOURCE_DIR


async def _set(run_id: str, patch: Dict, unset: Optional[List[str]] = None) -> None:
    update: Dict = {"$set": patch}
    if unset:
        update["$unset"] = {k: "" for k in unset}
    await db.bootstrap_runs.update_one({"run_id": run_id}, update, upsert=True)


# Terminal-state fields from a previous run that must never leak into a fresh run sharing
# the same run_id — otherwise a successful re-run can still show a stale "error" from an
# earlier failed attempt (found by Neo's testing agent after the entity-resolver fix).
_STALE_TERMINAL_FIELDS = ["error", "finished_at", "verification", "canonical_set", "duration_s"]


async def _step(run_id: str, steps: List[Dict], name: str, coro):
    t0 = time.time()
    entry = {"step": name, "status": "running", "started_at": now_iso()}
    steps.append(entry)
    await _set(run_id, {"steps": steps, "current_step": name})
    try:
        result = await coro
        entry.update({"status": "ok", "duration_s": round(time.time() - t0, 1), "result": result})
    except Exception as e:  # noqa: BLE001 — record and re-raise to abort the bootstrap
        entry.update({"status": "error", "duration_s": round(time.time() - t0, 1), "error": str(e)})
        await _set(run_id, {"steps": steps})
        raise
    await _set(run_id, {"steps": steps})
    return result


async def verify(smoke_cif: str = SMOKE_CIF) -> Dict:
    """Counts, coverage and a public-contract smoke check. No writes to canonical data."""
    counts = {c: await db[c].count_documents({}) for c in
              ("norm_company", "norm_financials", "norm_ownership", "norm_officers",
               "master_companies", "entity_xref", "signals", "semantic_profiles")}
    with_name = await db.master_companies.count_documents({"identity.legal_name": {"$ne": None}})
    with_fin = await db.master_companies.count_documents({"financials.latest": {"$ne": None}})
    with_rev = await db.master_companies.count_documents({"financials.latest.revenue": {"$ne": None}})
    with_hist2 = await db.master_companies.count_documents({"financials.history.1": {"$exists": True}})

    smoke = {"cif": smoke_cif, "identity_ok": False, "financials_ok": False, "years": []}
    doc = await db.master_companies.find_one({"cif_normalized": smoke_cif}, {"_id": 0})
    if doc:
        ident = doc.get("identity") or {}
        fin = doc.get("financials") or {}
        latest = fin.get("latest") or {}
        smoke["identity_ok"] = bool(ident.get("legal_name") and (doc.get("classification") or {}).get("cnae_code"))
        smoke["financials_ok"] = latest.get("revenue") is not None
        smoke["years"] = [h.get("year") for h in (fin.get("history") or [])]
        smoke["master_id"] = doc.get("master_id")
        # canonical intelligence smoke (proves search/comparables index is populated)
        try:
            from services.engines.signal import engine as sig_engine
            from services.engines.semantic import engine as sem_engine
            from services.engines.recommendation import engine as rec_engine
            from services.engines.strategy import engine as strat_engine
            mid = doc.get("master_id")
            sig = await sig_engine.analyze(mid, persist=False)
            sim = await sem_engine.similar(mid, limit=5)
            comp = await rec_engine.comparables(mid, limit=5)
            th = await strat_engine.thesis(mid)
            smoke["engines"] = {
                "signals": len((sig or {}).get("signals") or []),
                "similar": (sim or {}).get("count"),
                "comparables": (comp or {}).get("count"),
                "thesis": bool((th or {}).get("thesis_id")),
            }
        except Exception as e:  # noqa: BLE001
            smoke["engines"] = {"error": str(e)[:160]}

    ok = (counts["master_companies"] > 0 and with_name > 0 and with_fin > 0
          and smoke["identity_ok"] and smoke["financials_ok"])
    return {
        "ok": ok,
        "counts": counts,
        "coverage": {"with_legal_name": with_name, "with_financials": with_fin,
                     "with_revenue": with_rev, "with_history_2plus": with_hist2},
        "smoke": smoke,
    }


async def select_canonical_set(n: int = 50, persist: bool = True) -> Dict:
    """Curated validation set: real companies with the richest REAL multi-year financials.

    Selection is data-driven and never fabricates data: only companies whose `financials.history`
    contains ≥2 real fiscal years qualify, ranked by (years available, latest revenue) desc.
    """
    cursor = db.master_companies.find(
        {"financials.history.1": {"$exists": True}, "identity.legal_name": {"$ne": None}},
        {"_id": 0, "master_id": 1, "cif_normalized": 1, "identity.legal_name": 1,
         "classification.cnae_section": 1, "financials.latest": 1, "financials.history": 1},
    )
    rows = []
    async for d in cursor:
        hist = (d.get("financials") or {}).get("history") or []
        years = sorted({h.get("year") for h in hist if h.get("year") is not None})
        latest = (d.get("financials") or {}).get("latest") or {}
        rows.append({
            "master_id": d.get("master_id"),
            "cif": d.get("cif_normalized"),
            "legal_name": (d.get("identity") or {}).get("legal_name"),
            "cnae_section": (d.get("classification") or {}).get("cnae_section"),
            "years": years,
            "years_count": len(years),
            "latest_revenue": latest.get("revenue"),
        })
    rows.sort(key=lambda r: (r["years_count"], r["latest_revenue"] or 0), reverse=True)
    selected = rows[:n]
    if persist:
        now = now_iso()
        await db.canonical_validation_set.delete_many({})
        if selected:
            await db.canonical_validation_set.insert_many(
                [{**r, "selected_at": now, "bootstrap_version": BOOTSTRAP_VERSION} for r in selected])
    return {"requested": n, "available": len(rows), "selected": len(selected), "companies": selected}


async def build_signals_canonical(heartbeat=None) -> Dict:
    """Compute + persist signals for every canonical master record (db.signals by master_id)."""
    from services.engines.signal import engine as sig_engine
    ids = await db.master_companies.distinct("master_id", {"status": "active"})
    total = with_signals = errors = 0
    for mid in ids:
        total += 1
        try:
            r = await sig_engine.analyze(mid, persist=True)
            if r and (r.get("signals")):
                with_signals += 1
        except Exception:  # noqa: BLE001 — never abort the batch for one company
            errors += 1
        if heartbeat and total % 200 == 0:
            await heartbeat({"processed": total, "message": "signals"})
    return {"total": total, "with_signals": with_signals, "errors": errors}


async def build_semantic_canonical(heartbeat=None) -> Dict:
    """Build + persist the semantic profile & embedding for every canonical master record.

    Populates the vector store that powers Semantic search/similar and Recommendation comparables.
    """
    from services.engines.semantic import engine as sem_engine
    ids = await db.master_companies.distinct("master_id", {"status": "active"})
    total = with_embedding = errors = 0
    for mid in ids:
        total += 1
        try:
            r = await sem_engine.build_profile(mid, persist=True)
            if r and (r.get("embedding") or {}).get("dimension"):
                with_embedding += 1
        except Exception:  # noqa: BLE001
            errors += 1
        if heartbeat and total % 200 == 0:
            await heartbeat({"processed": total, "message": "semantic"})
    return {"total": total, "with_embedding": with_embedding, "errors": errors}


async def run_bootstrap(source: Optional[str] = None, rebuild_intelligence: bool = True,
                        canonical_n: int = 50, run_id: Optional[str] = None) -> Dict:
    """Run the full reproducible Data Layer reconstruction. Idempotent and re-runnable."""
    from services.data_layer.ingestion.iberinform_ingest import ingest_directory
    from services.data_layer.master.master_builder import rebuild_master
    from services.data_layer.master.ownership_graph import rebuild_ownership_graph

    src = source or source_dir()
    run_id = run_id or f"bootstrap_{uuid.uuid4().hex[:12]}"
    steps: List[Dict] = []
    t0 = time.time()
    await _set(run_id, {"run_id": run_id, "status": "running", "source": src,
                        "bootstrap_version": BOOTSTRAP_VERSION, "started_at": now_iso(), "steps": []},
               unset=_STALE_TERMINAL_FIELDS)
    logger.info(f"[bootstrap {run_id}] start · source={src}")
    try:
        await _step(run_id, steps, "ingestion", ingest_directory(src))
        await _step(run_id, steps, "master_builder", rebuild_master(scope="full", force=True))
        await _step(run_id, steps, "ownership_graph", rebuild_ownership_graph())
        if rebuild_intelligence:
            await _step(run_id, steps, "signal_builder", build_signals_canonical())
            await _step(run_id, steps, "semantic_index", build_semantic_canonical())
        report = await _step(run_id, steps, "verification", verify())
        canonical = await _step(run_id, steps, "canonical_set", select_canonical_set(canonical_n))
        status = "completed" if report.get("ok") else "completed_with_warnings"
        await _set(run_id, {"status": status, "finished_at": now_iso(),
                            "duration_s": round(time.time() - t0, 1),
                            "verification": report, "canonical_set": canonical})
        logger.info(f"[bootstrap {run_id}] {status} in {round(time.time()-t0,1)}s")
        return {"run_id": run_id, "status": status, "duration_s": round(time.time() - t0, 1),
                "verification": report, "canonical_set": canonical, "steps": steps}
    except Exception as e:  # noqa: BLE001
        await _set(run_id, {"status": "failed", "finished_at": now_iso(),
                            "duration_s": round(time.time() - t0, 1), "error": str(e)})
        logger.error(f"[bootstrap {run_id}] failed: {e}")
        raise


async def run_bootstrap_tab(directory: str = None, rebuild_intelligence: bool = True,
                             canonical_n: int = 50, run_id: Optional[str] = None,
                             source_version: Optional[str] = None, delivery=None) -> Dict:
    """Same reconstruction chain as `run_bootstrap()`, but for Daniel's real 2026-07
    Iberinform delivery format (10 tab-separated Datos_*.tab files) instead of the
    original Valu8 CSV format. Only step 1 (ingestion) differs — everything downstream
    (master builder, ownership graph, signals, semantic index, verification) is the
    exact same, unmodified code, since both ingestors write to the same norm_* shape.

    Use this instead of run_bootstrap() when `source` points at a directory containing
    Datos_GENERALES.tab / Datos_BALANCES.tab / etc. (see
    services/data_layer/ingestion/iberinform_tab_ingest.py for the full format mapping).

    `delivery` (ZipDelivery de R2): si se pasa, la INGESTA se hace por streaming desde el
    zip en R2 en vez de leer `directory` del disco (todo lo demás, aguas abajo, es idéntico
    — lee de las colecciones norm_*, no del disco). Ver r2_delivery.py.
    """
    from services.data_layer.ingestion.iberinform_tab_ingest import (
        ingest_tab_directory, ingest_tab_delivery)
    from services.data_layer.master.master_builder import rebuild_master
    from services.data_layer.master.ownership_graph import rebuild_ownership_graph

    run_id = run_id or f"bootstrap_tab_{uuid.uuid4().hex[:12]}"
    source_label = directory or (delivery.key if delivery is not None else "?")
    steps: List[Dict] = []
    t0 = time.time()
    await _set(run_id, {"run_id": run_id, "status": "running", "source": source_label,
                        "bootstrap_version": BOOTSTRAP_VERSION, "pipeline": "tab",
                        "started_at": now_iso(), "steps": []},
               unset=_STALE_TERMINAL_FIELDS)
    logger.info(f"[bootstrap-tab {run_id}] start · source={source_label}")
    try:
        ingestion = (ingest_tab_delivery(delivery, source_version=source_version)
                     if delivery is not None
                     else ingest_tab_directory(directory, source_version=source_version))
        await _step(run_id, steps, "ingestion", ingestion)
        await _step(run_id, steps, "master_builder", rebuild_master(scope="full", force=True))
        await _step(run_id, steps, "ownership_graph", rebuild_ownership_graph())
        if rebuild_intelligence:
            await _step(run_id, steps, "signal_builder", build_signals_canonical())
            await _step(run_id, steps, "semantic_index", build_semantic_canonical())
        report = await _step(run_id, steps, "verification", verify())
        canonical = await _step(run_id, steps, "canonical_set", select_canonical_set(canonical_n))
        status = "completed" if report.get("ok") else "completed_with_warnings"
        await _set(run_id, {"status": status, "finished_at": now_iso(),
                            "duration_s": round(time.time() - t0, 1),
                            "verification": report, "canonical_set": canonical})
        logger.info(f"[bootstrap-tab {run_id}] {status} in {round(time.time()-t0,1)}s")
        return {"run_id": run_id, "status": status, "duration_s": round(time.time() - t0, 1),
                "verification": report, "canonical_set": canonical, "steps": steps}
    except Exception as e:  # noqa: BLE001
        await _set(run_id, {"status": "failed", "finished_at": now_iso(),
                            "duration_s": round(time.time() - t0, 1), "error": str(e)})
        logger.error(f"[bootstrap-tab {run_id}] failed: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = asyncio.run(run_bootstrap())
    v = out["verification"]
    print("\n=== BOOTSTRAP RESULT ===")
    print("status:", out["status"], "| duration_s:", out["duration_s"])
    print("counts:", v["counts"])
    print("coverage:", v["coverage"])
    print("smoke:", v["smoke"])
    print("canonical_set:", {k: out["canonical_set"][k] for k in ("requested", "available", "selected")})
