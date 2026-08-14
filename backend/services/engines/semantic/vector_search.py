"""VectorSearchBackend — in-memory cosine over the FULL semantic universe (v2).

v1 was a controlled local top-k over an arbitrary 500-doc slice (blocking by CNAE
section). v2 loads ALL stored embeddings of the ACTIVE provider model into a cached
numpy matrix and scans the full universe on every query (true global search). Only
vectors whose `embedding.model` matches the active provider are considered, so a
provider/dimension switch degrades safely to empty until re-embed completes.

Atlas Vector Search (HNSW) remains a FUTURE backend; swapping it does NOT change the
/similar or /search contract.
"""

import asyncio
import time
from typing import Dict, List, Optional

import numpy as np

from services.engines.semantic import embeddings as E
from services.engines.semantic import persistence as P

BACKEND = "inmemory-cosine-v2"
_CACHE_TTL = 300  # seconds

_matrix: Optional[np.ndarray] = None       # float32 [N, D], L2-normalized rows
_meta: List[Dict] = []                     # aligned metadata per row
_sections: Optional[np.ndarray] = None     # object array of cnae_section per row
_ids: Optional[np.ndarray] = None          # object array of master_id per row
_loaded_at = 0.0
_loaded_model: Optional[str] = None
_lock = asyncio.Lock()


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
        # Memory-safe build: preallocate ONE float32 [N, D] matrix and fill row-by-row
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
                break  # count drifted upward; ignore extras
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
    """Force-refresh the in-memory index (used after a re-embed job). Returns row count."""
    await _ensure_index(force=True)
    return int(_matrix.shape[0]) if _matrix is not None else 0


async def top_k(vector: List[float], section: Optional[str], exclude: str,
                k: int = 10, pool: int = 500) -> List[Dict]:
    """Cosine top-k over the full stored universe (blocked by CNAE section, self-excluded)."""
    await _ensure_index()
    if _matrix is None or _matrix.shape[0] == 0:
        return []
    q = np.asarray(vector, dtype=np.float32)
    if q.shape[0] != _matrix.shape[1]:
        return []  # provider/dimension mismatch → safe empty (index stale vs query)
    qn = np.linalg.norm(q) or 1.0
    q = q / qn

    scores = _matrix @ q  # cosine (rows + query normalized)
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
        m = _meta[gi]
        out.append({"master_id": m["master_id"], "cif": m["cif"], "name": m["name"],
                    "cnae_section": m["cnae_section"], "score": round(float(sub[i]), 6)})
    return out
