"""Admin cache management — purge stale analysis caches (HARDENING-004).

Producción (Intel) mantiene una caché Mongo (TTL) de los payloads de
`financial-analysis`. Los payloads cacheados ANTES de que existiera la narrativa
financiera (assessment/verdict/weaknesses/risks) se seguirían sirviendo aunque el
código nuevo ya esté desplegado, porque un reinicio del servicio solo vacía la LRU
en memoria, NO las entradas persistidas en Mongo (su TTL sobrevive al restart).

Este endpoint purga esas entradas persistidas para que la siguiente llamada a
`financial-analysis` recompute con la narrativa. Protegido con JWT admin. Idempotente:
las cachés se reconstruyen bajo demanda, por lo que es seguro ejecutarlo cuando sea.
"""
import time

from fastapi import APIRouter, Depends, Query

from database import db
from auth_utils import get_current_user

router = APIRouter(prefix="/api/v1/admin/cache", tags=["admin_cache"])

# Colecciones Mongo de caché del path de análisis. `analyze_cache` es la actual;
# `intelligence_cache` es el nombre que usa la Intel de producción desplegada.
_ANALYZE_CACHE_COLLECTIONS = ["analyze_cache", "intelligence_cache"]


@router.get("/inspect")
async def inspect_caches(user=Depends(get_current_user)):
    """Lista toda colección cuyo nombre contenga 'cache' + su recuento de documentos,
    para que ops vea exactamente qué caché tiene la BD en ejecución ANTES de purgar
    (resuelve la ambigüedad del nombre real en prod)."""
    names = await db.list_collection_names()
    caches = sorted(n for n in names if "cache" in n.lower())
    out = {}
    for n in caches:
        out[n] = await db[n].count_documents({})
    return {"cache_collections": out, "known_analyze_caches": _ANALYZE_CACHE_COLLECTIONS}


@router.post("/purge-analyze")
async def purge_analyze_cache(
    extra: str = Query("", description="Nombres extra de colecciones de caché a purgar, separados por comas"),
    user=Depends(get_current_user),
):
    """Purga la caché persistida de `financial-analysis` (HARDENING-004). Vacía tanto la
    `analyze_cache` actual como la `intelligence_cache` legacy (+ las que se pasen en
    `extra`). Usa delete_many (conserva índices/TTL). Devuelve el recuento borrado por
    colección. Idempotente. Nota: la LRU en memoria la limpia el propio redeploy/restart."""
    t0 = time.time()
    targets = list(_ANALYZE_CACHE_COLLECTIONS)
    for e in (extra or "").split(","):
        e = e.strip()
        if e and e not in targets:
            targets.append(e)

    existing = set(await db.list_collection_names())
    deleted = {}
    for name in targets:
        if name in existing:
            res = await db[name].delete_many({})
            deleted[name] = res.deleted_count
        else:
            deleted[name] = None  # colección no presente en esta BD

    return {
        "status": "completed",
        "deleted": deleted,
        "note": "Las cachés se reconstruyen bajo demanda; la siguiente llamada a "
                "financial-analysis recompute con la narrativa (assessment/verdict/"
                "weaknesses/risks). El restart del redeploy limpia la LRU en memoria.",
        "processing_time_ms": round((time.time() - t0) * 1000, 1),
    }
