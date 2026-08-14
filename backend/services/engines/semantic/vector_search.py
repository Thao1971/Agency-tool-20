"""VectorSearchBackend — Atlas $vectorSearch (HNSW) with in-memory cosine fallback.

Primary path (production Atlas): `$vectorSearch` over the `semantic_vec` HNSW index on
`embedding.vector` — the cosine math runs INSIDE Atlas (no per-request load of the
universe, no Python matmul) → ~120-200ms warm.

Fallback path (e.g. local MongoDB in preview, which has no $vectorSearch): a memory-safe
in-memory numpy index (preallocated float32 [N, D] matrix, streamed build) scanning the
full universe. Same contract for /search and /similar; response shape is unchanged.

The active backend is auto-detected once (probe) and cached in `_ATLAS_OK`.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

import numpy as np

from database import db
from services.engines.semantic import embeddings as E
from services.engines.semantic import persistence as P

logger = logging.getLogger(__name__)

_INDEX_NAME = "semantic_vec"
_ATLAS_OK: Optional[bool] = None  # None=unknown, True=Atlas $vectorSearch, False=in-memory

# ── in-memory fallback state ─────────────────────────────────────────────────
_CACHE_TTL = 300
_matrix: Optional[np.ndarray] = None
_meta: List[Dict] = []
_sections: Optional[np.ndarray] = None
_ids: Optional[np.ndarray] = None
_loaded_at = 0.0
_loaded_model: Optional[str] = None
_lock = asyncio.Lock()


def current_backend() -> str:
    if _ATLAS_OK is True:
        return "atlas-vectorsearch-v1"
    if _ATLAS_OK is False:
        return "inmemory-cosine-v2"
    return "auto"


# ── Atlas $vectorSearch ──────────────────────────────────────────────────────
async def _atlas_top_k(vector: List[float], section: Optional[str], exclude: str,
                       k: int) -> List[Dict]:
    over = k + (5 if exclude and exclude != "__query__" else 0)
    stage = {"index": _INDEX_NAME, "path": "embedding.vector", "queryVector": vector,
             "numCandidates": min(max(k * 20, 150), 10000), "limit": over}
    if section:
        stage["filter"] = {"cnae_section": section}
    pipe = [{"$vectorSearch": stage},
            {"$project": {"_id": 0, "master_id": 1, "cif_normalized": 1,
                          "identity_name": 1, "cnae_section": 1,
                          "score": {"$meta": "vectorSearchScore"}}}]
    rows = await db.semantic_profiles.aggregate(pipe).to_list(None)
    out = []
    for r in rows:
        if exclude and r.get("master_id") == exclude:
            continue
        out.append({"master_id": r["master_id"], "cif": r.get("cif_normalized"),
                    "name": r.get("identity_name"), "cnae_section": r.get("cnae_section"),
                    "score": round(float(r.get("score") or 0.0), 6)})
        if len(out) >= k:
            break
    return out


# ── in-memory fallback ───────────────────────────────────────────────────────
def _fresh(model: str) -> bool:
    return (_matrix is not None and _loaded_model == model
            and (time.time() - _loaded_at) < _CACHE_TTL)


async def _ensure_index(force: bool = False) -> None:
    global _matrix, _meta, _sections, _ids, _loaded_at, _loaded_model
    model = E.get_provider().model
    if not force and _fresh(model):
        return
    async with _lock:
        if not force and _fresh(model):
            return
        # Memory-safe build: preallocate ONE float32 [N, D] matrix, fill row-by-row
        # from a streamed cursor (never materializes the universe as a Python list).
        n = await P.count_embeddings(model)
        meta: List[Dict] = []
        if n <= 0:
            _matrix, _meta = np.zeros((0, 1), dtype=np.float32), []
            _sections = np.array([], dtype=object)
            _ids = np.array([], dtype=object)
            _loaded_at, _loaded_model = time.time(), model
            return
        m = None
        i = 0
        async for r in P.iter_embeddings(model):
            v = (r.get("embedding") or {}).get("vector")
            if not v:
                continue
            if m is None:
                m = np.empty((n, len(v)), dtype=np.float32)
            if i >= n:
                break
            m[i] = v
            meta.append({"master_id": r["master_id"], "cif": r.get("cif_normalized"),
                         "name": r.get("identity_name"), "cnae_section": r.get("cnae_section")})
            i += 1
        if m is None or i == 0:
            m = np.zeros((0, 1), dtype=np.float32)
        else:
            m = m[:i]
            norms = np.linalg.norm(m, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            m /= norms
        _matrix = m
        _meta = meta
        _sections = np.array([x["cnae_section"] for x in meta], dtype=object)
        _ids = np.array([x["master_id"] for x in meta], dtype=object)
        _loaded_at = time.time()
        _loaded_model = model


async def reload() -> int:
    await _ensure_index(force=True)
    return int(_matrix.shape[0]) if _matrix is not None else 0


async def _inmemory_top_k(vector: List[float], section: Optional[str], exclude: str,
                          k: int) -> List[Dict]:
    await _ensure_index()
    if _matrix is None or _matrix.shape[0] == 0:
        return []
    q = np.asarray(vector, dtype=np.float32)
    if q.shape[0] != _matrix.shape[1]:
        return []
    qn = np.linalg.norm(q) or 1.0
    q = q / qn
    scores = _matrix @ q
    n = scores.shape[0]
    keep = np.ones(n, dtype=bool)
    if section:
        keep &= (_sections == section)
    if exclude:
        keep &= (_ids != exclude)
    idxs = np.nonzero(keep)[0]
    if idxs.shape[0] == 0:
        return []
    sub = scores[idxs]
    kk = int(min(k, idxs.shape[0]))
    part = np.argpartition(-sub, kk - 1)[:kk]
    part = part[np.argsort(-sub[part])]
    out = []
    for i in part:
        gi = int(idxs[i])
        mm = _meta[gi]
        out.append({"master_id": mm["master_id"], "cif": mm["cif"], "name": mm["name"],
                    "cnae_section": mm["cnae_section"], "score": round(float(sub[i]), 6)})
    return out


# ── dispatcher + warm ────────────────────────────────────────────────────────
async def top_k(vector: List[float], section: Optional[str], exclude: str,
                k: int = 10, pool: int = 500) -> List[Dict]:
    global _ATLAS_OK
    if _ATLAS_OK is not False:
        try:
            res = await _atlas_top_k(vector, section, exclude, k)
            _ATLAS_OK = True
            return res
        except Exception as e:
            if _ATLAS_OK is None:
                _ATLAS_OK = False
                logger.warning(f"[semantic] $vectorSearch unavailable → in-memory fallback: {e}")
            else:
                logger.warning(f"[semantic] $vectorSearch transient error → in-memory this request: {e}")
    return await _inmemory_top_k(vector, section, exclude, k)


async def warm() -> Dict:
    """Probe Atlas $vectorSearch; if available use it (no in-memory load), else warm in-memory."""
    global _ATLAS_OK
    try:
        probe = [1.0] + [0.0] * 511
        await _atlas_top_k(probe, None, "__warm__", 1)
        _ATLAS_OK = True
        return {"backend": "atlas-vectorsearch-v1", "index": _INDEX_NAME}
    except Exception as e:
        _ATLAS_OK = False
        n = await reload()
        logger.info(f"[semantic] Atlas $vectorSearch not available ({e}); in-memory index warmed: {n}")
        return {"backend": "inmemory-cosine-v2", "vectors": n}
