"""VectorSearchBackend (D-S3) — pluggable. v1 = controlled local top-k cosine with
blocking (D-S5). Atlas Vector Search (HNSW) is a FUTURE backend; swapping it does NOT
change the /similar or /search contract.
"""

from typing import Dict, List, Optional

from services.engines.semantic import embeddings as E
from services.engines.semantic import persistence as P

BACKEND = "local-topk-v1"


async def top_k(vector: List[float], section: Optional[str], exclude: str,
                k: int = 10, pool: int = 500) -> List[Dict]:
    """Cosine top-k over stored profile embeddings, blocked by CNAE section."""
    cands = await P.candidates_with_embeddings(section, exclude, pool)
    scored = []
    for c in cands:
        vec = (c.get("embedding") or {}).get("vector")
        if not vec:
            continue
        scored.append({"master_id": c["master_id"],
                       "name": c.get("identity_name"),
                       "cnae_section": c.get("cnae_section"),
                       "score": E.cosine(vector, vec)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]
