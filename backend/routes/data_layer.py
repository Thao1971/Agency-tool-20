"""Data Layer endpoint — canonical master record rebuild (P2.1)."""

import asyncio
import time
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from auth_utils import get_current_user
from database import db
from models import now_iso
from services.data_layer.master_builder import rebuild_master_records
from services.taxonomy_embeddings import build_index
from services.engines.signal.master_signals import rebuild_signals
from services.knowledge_graph import rebuild_graph
from services.jobs import queue as job_queue
from services.data_layer import bootstrap as bootstrap_svc
from services.data_layer.master import ownership_graph as OG
from services.data_layer.master.competitor_graph import rebuild_competitor_edges
from services.data_layer.master import graph_traversal as GT
from services.data_layer.master import control_synergy as CS

router = APIRouter(prefix="/api/v1/data-layer", tags=["data_layer"])


class BootstrapRequest(BaseModel):
    source: Optional[str] = None
    rebuild_intelligence: bool = True
    canonical_n: int = 50


class BootstrapTabRequest(BaseModel):
    directory: str
    rebuild_intelligence: bool = True
    canonical_n: int = 50
    source_version: Optional[str] = None


@router.post("/bootstrap-tab")
async def start_bootstrap_tab(req: BootstrapTabRequest, user=Depends(get_current_user)):
    """Same as /bootstrap, but for Daniel's real 2026-07 Iberinform delivery format
    (Datos_GENERALES.tab, Datos_BALANCES.tab, Datos_ACCIONISTAS.tab, Datos_PARTICIPADAS.tab,
    Datos_ORG_SOCIALES.tab, Datos_RESTO_ORG_SOCIALES.tab, Datos_APODERADOS.tab — extracted
    from Muestra_25000_base.zip into `directory` server-side). Populates the MODERN schema
    (master_companies / master_relationships) used by Control&Synergy, Roll-up, Fragmentación,
    Watchlist, and all the newer engines.

    This is one half of the real-data load. Run POST /admin/iberinform/process-tab-directory
    (routes/iberinform_admin.py) separately for the LEGACY schema (companies_master) used by
    Sector/Geo Intelligence and Valuo. Run both, verify counts, THEN
    POST /admin/iberinform/purge-synthetic to remove the 5,000 synthetic companies.

    Runs in background. Poll GET /bootstrap/{run_id} for progress (same collection/shape
    as the regular /bootstrap endpoint)."""
    run_id = f"bootstrap_tab_{now_iso()}"
    run_id = "bootstrap_tab_" + run_id.replace(":", "").replace("-", "")[:18]

    async def _run():
        try:
            await bootstrap_svc.run_bootstrap_tab(
                directory=req.directory, rebuild_intelligence=req.rebuild_intelligence,
                canonical_n=req.canonical_n, run_id=run_id, source_version=req.source_version)
        except Exception:  # noqa: BLE001 — status persisted inside run_bootstrap_tab
            pass

    asyncio.create_task(_run())
    return {"run_id": run_id, "status": "started",
            "poll": f"/api/v1/data-layer/bootstrap/{run_id}"}


@router.post("/bootstrap")
async def start_bootstrap(req: BootstrapRequest, user=Depends(get_current_user)):
    """Reproducibly rebuild the ENTIRE canonical Data Layer from the official sources.

    Runs the full chain (ingestion → master → ownership → signals → semantic index → verify →
    canonical set) in the background. Poll GET /bootstrap/{run_id} for progress. No manual steps.
    """
    run_id = f"bootstrap_{now_iso()}"
    run_id = "bootstrap_" + run_id.replace(":", "").replace("-", "")[:18]

    async def _run():
        try:
            await bootstrap_svc.run_bootstrap(
                source=req.source, rebuild_intelligence=req.rebuild_intelligence,
                canonical_n=req.canonical_n, run_id=run_id)
        except Exception:  # noqa: BLE001 — status persisted inside run_bootstrap
            pass

    asyncio.create_task(_run())
    return {"run_id": run_id, "status": "started",
            "poll": f"/api/v1/data-layer/bootstrap/{run_id}"}


@router.get("/bootstrap/{run_id}")
async def get_bootstrap(run_id: str, user=Depends(get_current_user)):
    doc = await db.bootstrap_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "bootstrap run not found")
    return doc


@router.get("/bootstrap")
async def list_bootstrap(limit: int = 10, user=Depends(get_current_user)):
    runs = await db.bootstrap_runs.find({}, {"_id": 0, "steps": 0}).sort("started_at", -1).to_list(limit)
    return {"runs": runs}


@router.get("/canonical-set")
async def get_canonical_set(user=Depends(get_current_user)):
    """The curated ~50-company canonical validation set (real data, real fiscal years only)."""
    docs = await db.canonical_validation_set.find({}, {"_id": 0}).to_list(200)
    return {"count": len(docs), "companies": docs}


class JobRequest(BaseModel):
    job_type: str
    params: Dict = Field(default_factory=dict)
    pipeline_version: Optional[str] = None
    priority: int = 0


@router.post("/rebuild-master")
async def rebuild_master(user=Depends(get_current_user)):
    """Idempotently rebuild companies_master into the unified canonical schema."""
    t0 = time.time()
    stats = await rebuild_master_records()
    return {
        "status": "ok",
        "generated_at": now_iso(),
        "duration_ms": round((time.time() - t0) * 1000, 1),
        **stats,
    }


@router.post("/rebuild-embeddings")
async def rebuild_embeddings(user=Depends(get_current_user)):
    """Build the LSA embedding index + clusters (Fase C). Powers hybrid Search/Recommend."""
    t0 = time.time()
    stats = await build_index()
    return {"generated_at": now_iso(), "duration_ms": round((time.time() - t0) * 1000, 1), **stats}


@router.post("/rebuild-signals")
async def rebuild_signals_endpoint(user=Depends(get_current_user)):
    """Compute + persist signals[] and signal_score for every master record (Signal Engine)."""
    t0 = time.time()
    stats = await rebuild_signals()
    return {"status": "ok", "generated_at": now_iso(),
            "duration_ms": round((time.time() - t0) * 1000, 1), **stats}


@router.post("/rebuild-graph")
async def rebuild_graph_endpoint(user=Depends(get_current_user)):
    """DEPRECATED legacy path: materializes company_relationships on the OLD
    companies_master/master_company_id scheme (similar_to/same_cluster only). Not part
    of the official /bootstrap chain. Prefer /relationships/{master_id} (real ownership
    graph, modern master_id scheme) for anything new."""
    t0 = time.time()
    stats = await rebuild_graph()
    return {"generated_at": now_iso(),
            "duration_ms": round((time.time() - t0) * 1000, 1), **stats}


@router.get("/relationships/{master_id}")
async def get_relationships(master_id: str, limit: int = 50, user=Depends(get_current_user)):
    """Q2 — real control graph, read side. Ownership edges (shareholder_of/parent_of/
    ultimate_parent_of/investee_of, from Iberinform via ownership_graph.py) plus
    competitor_of (sector+size heuristic, competitor_graph.py) if computed. This was a
    write-only graph before Q2 — nothing ever queried `master_relationships`."""
    rows = await OG.relationships_for(master_id, limit=limit)
    if not rows:
        exists = await db.master_companies.find_one({"master_id": master_id}, {"_id": 0, "master_id": 1})
        if not exists:
            raise HTTPException(404, "company not found in Master Layer")
    return {"master_id": master_id, "count": len(rows), "relationships": rows}


@router.get("/relationships/{master_id}/group")
async def get_group_members(master_id: str, user=Depends(get_current_user)):
    """Every company in the same ownership group (union-find result of the real graph)."""
    result = await OG.group_members(master_id)
    if result["group_id"] is None:
        exists = await db.master_companies.find_one({"master_id": master_id}, {"_id": 0, "master_id": 1})
        if not exists:
            raise HTTPException(404, "company not found in Master Layer")
    return result


@router.get("/graph/{master_id}/traverse")
async def traverse_graph(master_id: str, max_hops: int = 2, max_nodes: int = 150,
                          relationship_types: Optional[str] = None,
                          user=Depends(get_current_user)):
    """T3 — Navigable Control Graph. Multi-hop BFS over the real control graph (Q2's
    ownership edges + competitor_of), both directions, bounded by max_hops/max_nodes.
    `relationship_types` is an optional comma-separated filter (e.g.
    'parent_of,ultimate_parent_of' to see only the ownership tree, no competitors)."""
    exists = await db.master_companies.find_one({"master_id": master_id}, {"_id": 0, "master_id": 1})
    if not exists:
        raise HTTPException(404, "company not found in Master Layer")
    types = [t.strip() for t in relationship_types.split(",")] if relationship_types else None
    return await GT.traverse(master_id, max_hops=max_hops, max_nodes=max_nodes, relationship_types=types)


@router.get("/graph/sector-map")
async def sector_consolidation_map(cnae_field: str = "cnae_code", cnae_value: str = "",
                                    limit_companies: int = 200,
                                    user=Depends(get_current_user)):
    """T3 — sector consolidation map: the real ownership/competitor graph restricted to
    companies already identified as being in this CNAE sector (same fields Q5's
    drill-down uses). This is the concrete input a roll-up thesis (E6) needs — who
    already owns whom, and who competes with whom, inside one real sector."""
    if not cnae_value:
        raise HTTPException(400, "cnae_value is required")
    try:
        return await GT.sector_consolidation_map(cnae_field, cnae_value, limit_companies=limit_companies)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/search-companies")
async def search_companies(q: str = "", limit: int = 20, user=Depends(get_current_user)):
    """Company autocomplete against the MODERN master_companies/master_id schema (the
    one Q5/T3/E6/Control&Synergy all use) — deliberately separate from
    `GET /api/v1/master` (routes/master.py), which searches the LEGACY
    companies_master/master_company_id schema and would return IDs incompatible with
    these engines. Frontend-only convenience, JWT-gated."""
    if not q or len(q) < 2:
        return {"count": 0, "companies": []}
    rows = await db.master_companies.find(
        {"status": "active", "identity.legal_name": {"$regex": q, "$options": "i"}},
        {"_id": 0, "master_id": 1, "identity.legal_name": 1, "classification.cnae_code": 1,
         "location.provincia": 1},
    ).limit(limit).to_list(limit)
    return {"count": len(rows), "companies": [
        {"master_id": r["master_id"], "legal_name": (r.get("identity") or {}).get("legal_name"),
         "cnae_code": (r.get("classification") or {}).get("cnae_code"),
         "provincia": (r.get("location") or {}).get("provincia")}
        for r in rows
    ]}


@router.get("/control-synergy/{master_id_a}/{master_id_b}")
async def control_synergy(master_id_a: str, master_id_b: str, user=Depends(get_current_user)):
    """Control & Synergy Score (roadmap: parte de T3, dueño Ownership & Control /
    Buyer Intelligence). Control real (pct directo o cadena de pct multi-salto vía T3,
    nunca inventado) + synergy real (competitor_of de Q2, solapamiento CNAE, misma
    provincia) entre dos empresas concretas. supplier_candidate no se mide — sin datos
    reales en ninguna fuente conectada."""
    try:
        return await CS.compute_control_synergy(master_id_a, master_id_b)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/rebuild-competitor-graph")
async def rebuild_competitor_graph_endpoint(limit_codes: int = 300, user=Depends(get_current_user)):
    """Q2 — materialize competitor_of (same CNAE code + same revenue size_band, not in the
    same ownership group). Real, structural data only; no new source. Run after
    /bootstrap (needs master_companies + ownership.group_id populated)."""
    t0 = time.time()
    stats = await rebuild_competitor_edges(limit_codes=limit_codes)
    return {"generated_at": now_iso(),
            "duration_ms": round((time.time() - t0) * 1000, 1), **stats}


# ── Jobs (P0.2) — API only enqueues/queries/cancels; heavy work runs in a separate worker ──
@router.post("/jobs")
async def create_job(req: JobRequest, user=Depends(get_current_user)):
    job_id = await job_queue.enqueue(req.job_type, req.params, req.pipeline_version, req.priority)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs")
async def list_jobs(limit: int = 20, user=Depends(get_current_user)):
    return {"jobs": await job_queue.list_recent(limit)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user=Depends(get_current_user)):
    doc = await job_queue.get(job_id)
    if not doc:
        raise HTTPException(404, "job not found")
    return doc


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user=Depends(get_current_user)):
    ok = await job_queue.request_cancel(job_id)
    if not ok:
        raise HTTPException(409, "job not cancellable (missing or already terminal)")
    return {"job_id": job_id, "cancel_requested": True}
