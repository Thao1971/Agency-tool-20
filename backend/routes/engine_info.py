"""Engine identity & capabilities — public 'About' endpoints.

GET /api/v1/engine/version       — full identity card + live health verdict
GET /api/v1/engine/capabilities  — declarative profiles / sources / modules
"""

from fastapi import APIRouter

from services.intelligence_engine.engine_info import (
    get_engine_identity,
    get_capabilities,
    get_profile_names,
    get_all_sources,
)

router = APIRouter(prefix="/api/v1/engine", tags=["engine_info"])


@router.get("/version")
async def engine_version():
    """Identity card of the Intelligence Engine instance answering this request.

    Used by Valuo / arroba for audit trail, smoke tests for post-deploy
    verification, and support to answer 'what version is in production?'.
    """
    identity = get_engine_identity()
    # Live health verdict (best-effort: don't fail the version endpoint if unhealthy)
    health_verdict = "unknown"
    try:
        from database import db
        stuck = await db.valuo_update_requests.count_documents(
            {"enrichment_status": {"$in": ["pending", "processing"]}}
        )
        failed = await db.valuo_update_requests.count_documents(
            {"enrichment_status": "failed"}
        )
        if failed > 0:
            health_verdict = "degraded"
        elif stuck > 5:
            health_verdict = "busy"
        else:
            health_verdict = "healthy"
    except Exception:
        pass

    return {
        **identity,
        "profiles": get_profile_names(),
        "sources": get_all_sources(),
        "health": health_verdict,
    }


@router.get("/capabilities")
async def engine_capabilities():
    """Declarative capabilities — what this engine instance knows how to do.

    Profiles describe enrichment products, sources describe origins of data,
    modules describe transversal capabilities (lineage, cache, queue, …).
    """
    return get_capabilities()
