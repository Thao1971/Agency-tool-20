"""ARROBA Company Taxonomy — API interna (JWT) para el panel de auditoría de la Platform Console.

La API externa `/api/v1/company-taxonomy` usa service-key (la consume ARROBA). Esta capa fina expone
lo mismo autenticada con el JWT del usuario del agency tool (`get_current_user`). Reutiliza los
servicios de taxonomía (no recrea nada). Aditivo.
"""

from typing import Optional
from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from services.taxonomy import TAXONOMY_VERSION
from services.taxonomy import audit as AUDIT
from services.taxonomy import batch as BATCH

router = APIRouter(prefix="/api/v1/company-taxonomy-ui", tags=["company-taxonomy-ui"])


@router.get("/audit")
async def audit(sample_n: int = 0, user=Depends(get_current_user)):
    """Distribución por sector + métricas de calidad de la clasificación F3."""
    return await AUDIT.audit_report(sample_n=sample_n)


@router.get("/unclassified")
async def unclassified(limit: int = 300, user=Depends(get_current_user)):
    """Empresas sin sector principal, para revisión manual (con nombre/CNAE/objeto social)."""
    return await AUDIT.list_unclassified(limit=limit)


@router.post("/reclassify")
async def reclassify(limit: Optional[int] = None, user=Depends(get_current_user)):
    """Re-lanza la pasada de clasificación F3 sobre el universo (o los primeros `limit`)."""
    return await BATCH.classify_batch(limit=limit)


@router.get("/health")
async def health(user=Depends(get_current_user)):
    return {"taxonomy_version": TAXONOMY_VERSION, "status": "ok", "auth": "jwt"}
