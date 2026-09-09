"""ARROBA Company Taxonomy Registry — API de lectura + siembra (service-key). Distinta de la taxonomía
maestra del agency tool (routes/taxonomy.py). Ver memory/ARROBA_TAXONOMY_ENGINE_DESIGN.md. La
clasificación de empresas llega en Fase 2."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from services.service_auth import require_service_key
from services.taxonomy import TAXONOMY_VERSION
from services.taxonomy import registry as REG
from services.taxonomy import classify as CLS
from services.taxonomy import batch as BATCH
from services.taxonomy import audit as AUDIT
from services.taxonomy import similarity as SIM
from services.taxonomy import search as SEARCH

router = APIRouter(prefix="/api/v1/company-taxonomy", tags=["company-taxonomy"])


class ClassifyIn(BaseModel):
    company_id: Optional[str] = None
    inputs: Dict[str, Any] = {}


@router.get("/health")
async def health(_key=Depends(require_service_key)):
    return {"taxonomy_version": TAXONOMY_VERSION, "status": "ok", "sectors": len(REG.SEED)}


@router.get("/tree")
async def tree(_key=Depends(require_service_key)):
    return {"taxonomy_version": TAXONOMY_VERSION, "tree": await REG.get_tree()}


@router.get("/dimensions")
async def dimensions(_key=Depends(require_service_key)):
    return {"taxonomy_version": TAXONOMY_VERSION, "dimensions": await REG.get_dimensions()}


@router.get("/node/{node_id}")
async def node(node_id: str, _key=Depends(require_service_key)):
    return await REG.get_node(node_id) or {"error": "not_found", "id": node_id}


@router.post("/seed")
async def seed(_key=Depends(require_service_key)):
    """Siembra idempotente del Registry v1 (por id)."""
    return await REG.build_registry_v1()


@router.post("/classify")
async def classify(req: ClassifyIn, _key=Depends(require_service_key)):
    """Clasifica una empresa (determinista): sector/industria/categoría + dimensiones + fingerprint."""
    return await CLS.classify({"company_id": req.company_id, "inputs": req.inputs})


@router.get("/company/{company_id}")
async def company(company_id: str, _key=Depends(require_service_key)):
    """Clasificación + fingerprint persistidos de una empresa."""
    return await CLS.get_company_classification(company_id)


@router.post("/classify-batch")
async def classify_batch(limit: Optional[int] = None, _key=Depends(require_service_key)):
    """Primera pasada (F3): clasifica el universo `master_companies` (o los primeros `limit`)."""
    return await BATCH.classify_batch(limit=limit)


@router.get("/audit-report")
async def audit_report(sample_n: int = 150, _key=Depends(require_service_key)):
    """Informe de auditoría de la clasificación (distribución, cobertura, muestra)."""
    return await AUDIT.audit_report(sample_n=sample_n)


@router.get("/peers/{company_id}")
async def peers(company_id: str, k: int = 10, same_primary_only: bool = False,
                _key=Depends(require_service_key)):
    """Peer Universe Resolver: comparables reales por taxonomía+dimensiones+tamaño+geo+fingerprint."""
    return await SIM.peers(company_id, k=k, same_primary_only=same_primary_only)


@router.get("/search")
async def search(node_id: Optional[str] = None, dimension_id: Optional[str] = None,
                 q: Optional[str] = None, primary_only: bool = False, limit: int = 50,
                 offset: int = 0, sort_by: Optional[str] = None, sort_dir: str = "desc",
                 _key=Depends(require_service_key)):
    """Búsqueda por taxonomía (doble modo). `q` resuelve una etiqueta de texto a nodo/dimensión.
    Devuelve `results` enriquecidos con `summary` + `count`/`limit`/`offset` (paginación de servidor).
    `sort_by` (name|revenue|ebitda|employees|cif) ordena TODO el conjunto por esa columna."""
    resolved = None
    if q and not (node_id or dimension_id):
        hit = SEARCH.resolve_label(q)
        if not hit:
            return {"count": 0, "results": [], "company_ids": [],
                    "note": f"No reconozco '{q}' en la taxonomía."}
        resolved = hit
        if hit["kind"] in SEARCH._IS_NODE:
            node_id = hit["id"]
        else:
            dimension_id = hit["id"]
    res = await SEARCH.search_by_taxonomy(node_id=node_id, dimension_id=dimension_id,
                                          primary_only=primary_only, limit=limit, offset=offset,
                                          sort_by=sort_by, sort_dir=sort_dir)
    if resolved:
        res["resolved"] = resolved
    return res


class SummaryIn(BaseModel):
    master_ids: List[str] = []


@router.post("/summary")
async def summary_batch(req: SummaryIn, _key=Depends(require_service_key)):
    """Ficha-resumen en LOTE para una lista de master_id (pinta tablas sin N+1)."""
    from services.company_card import build_summaries
    summaries = await build_summaries(req.master_ids)
    return {"count": len(summaries), "summaries": summaries}



@router.get("/sectors")
async def sectors(_key=Depends(require_service_key)):
    """Sectores con nº de empresas (actividad principal) — para chips/atajos."""
    return {"sectors": await SEARCH.sector_counts()}


@router.get("/compare-pair")
async def compare_pair(a: str, b: str, _key=Depends(require_service_key)):
    """Compara dos empresas por taxonomía (compartido/diferencias + similitud de fingerprint)."""
    return await SIM.compare_pair(a, b)