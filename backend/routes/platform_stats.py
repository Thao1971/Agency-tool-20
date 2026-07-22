"""Platform Stats endpoint (REQ-002) — public, cacheable, X-Source: real."""

from fastapi import APIRouter, Response
from services.platform_stats import get_platform_stats, CACHE_TTL_SECONDS

# NOTE: ingress routes only /api/* to the backend, so the public URL is
# {BACKEND_URL}/api/v1/platform_stats (arroba's adapter base must include /api).
router = APIRouter(prefix="/api/v1", tags=["platform_stats"])


@router.get("/platform_stats")
async def platform_stats(response: Response):
    """Aggregated platform metrics for arroba.com Home. No auth, no PII, cacheable."""
    data = await get_platform_stats()
    response.headers["X-Source"] = "real"
    response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL_SECONDS}"
    return data
