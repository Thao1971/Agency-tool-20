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
