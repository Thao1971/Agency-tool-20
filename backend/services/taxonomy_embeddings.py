"""Taxonomy/Company embeddings — Fase C (local LSA, no vector DB, no external API).

Builds a dense semantic space for companies from their unified master text
(name + sector + category + description + tags) using TF-IDF (word + char n-grams)
reduced via Truncated SVD (LSA). Powers semantic similarity + clustering + auto-tags.

Consumed INTERNALLY by Search/Recommend (hybrid ranking) — public contracts unchanged.
Swappable for neural embeddings later without touching the loop. Degrades gracefully:
if the index is missing, callers fall back to pure lexical/structural ranking.
"""

import os
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer
from sklearn.cluster import KMeans

from database import db
from models import now_iso
from services.data_layer.accessors import name_of, sector_of, category_of

logger = logging.getLogger(__name__)

MODEL_PATH = "/app/backend/models/company_lsa.joblib"
EMBED_DIM = 128
N_CLUSTERS = 24
EMBED_VERSION = "lsa-v1"

# In-memory caches (rebuilt on demand / lazy-loaded)
_PIPELINE = None
_VECTORS: Optional[Dict[str, np.ndarray]] = None  # master_company_id -> unit vector


def _doc_text(doc: Dict) -> str:
    web = (doc.get("sources") or {}).get("web") or {}
    parts = [
        name_of(doc) or "", sector_of(doc) or "", category_of(doc) or "",
        " ".join(doc.get("aliases") or []),
        web.get("description") or "",
        " ".join(web.get("tags") or []) if isinstance(web.get("tags"), list) else "",
        (doc.get("classification") or {}).get("cnae_label") or "",
    ]
    return " ".join(p for p in parts if p).strip()


def _build_pipeline(n_docs: int):
    dim = min(EMBED_DIM, max(2, n_docs - 1))
    vectorizer = TfidfVectorizer(
        lowercase=True, strip_accents="unicode", analyzer="word",
        ngram_range=(1, 2), min_df=1, max_df=0.9, sublinear_tf=True,
    )
    svd = TruncatedSVD(n_components=dim, random_state=42)
    return make_pipeline(vectorizer, svd, Normalizer(copy=False)), dim


async def build_index() -> Dict:
    """Fit LSA on all master docs, persist model, store unit vectors + clusters."""
    docs = await db.companies_master.find(
        {"merge_status": {"$ne": "merged"}}, {"_id": 0}
    ).to_list(100000)
    corpus, ids = [], []
    for d in docs:
        text = _doc_text(d)
        if text:
            corpus.append(text)
            ids.append(d["master_company_id"])

    if len(corpus) < 3:
        return {"status": "skipped", "reason": "not enough documents", "count": len(corpus)}

    pipeline, dim = _build_pipeline(len(corpus))
    matrix = pipeline.fit_transform(corpus)  # (n, dim), unit-normalized

    k = min(N_CLUSTERS, max(2, len(corpus) // 20))
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(matrix)

    # Auto-tags per cluster: top TF-IDF terms near each centroid (via inverse transform proxy)
    cluster_tags = _cluster_tags(pipeline, km, k)

    # Persist model + clustering
    joblib.dump({"pipeline": pipeline, "kmeans": km, "dim": dim, "cluster_tags": cluster_tags,
                 "version": EMBED_VERSION}, MODEL_PATH)

    # Store vectors + cluster assignment
    await db.company_embeddings.delete_many({})
    bulk = []
    now = now_iso()
    for i, mc_id in enumerate(ids):
        cl = int(labels[i])
        bulk.append({
            "master_company_id": mc_id,
            "vector": matrix[i].astype(float).tolist(),
            "cluster_id": cl,
            "version": EMBED_VERSION,
            "updated_at": now,
        })
        # write cluster + tags back into master (KG/taxonomy base)
        await db.companies_master.update_one(
            {"master_company_id": mc_id},
            {"$set": {"classification.cluster_id": cl,
                      "classification.cluster_tags": cluster_tags.get(cl, [])}},
        )
    if bulk:
        await db.company_embeddings.insert_many(bulk)

    # refresh in-memory caches
    global _PIPELINE, _VECTORS
    _PIPELINE = pipeline
    _VECTORS = {mc_id: matrix[i] for i, mc_id in enumerate(ids)}

    return {"status": "ok", "count": len(corpus), "dim": dim, "clusters": k, "version": EMBED_VERSION}


def _cluster_tags(pipeline, km, k: int, top_n: int = 5) -> Dict[int, List[str]]:
    """Top terms per cluster by projecting centroids back to TF-IDF space."""
    try:
        vec = pipeline.named_steps["tfidfvectorizer"]
        svd = pipeline.named_steps["truncatedsvd"]
        terms = np.array(vec.get_feature_names_out())
        # centroid (dim) -> term space via SVD components
        term_scores = km.cluster_centers_ @ svd.components_  # (k, n_terms)
        tags = {}
        for c in range(k):
            top_idx = np.argsort(term_scores[c])[::-1][:top_n]
            tags[c] = [t for t in terms[top_idx].tolist() if len(t) > 2]
        return tags
    except Exception as e:
        logger.warning(f"cluster tag extraction failed: {e}")
        return {}


def _load_model():
    global _PIPELINE
    if _PIPELINE is not None:
        return _PIPELINE
    if os.path.exists(MODEL_PATH):
        try:
            _PIPELINE = joblib.load(MODEL_PATH)["pipeline"]
        except Exception as e:
            logger.error(f"failed loading embedding model: {e}")
    return _PIPELINE


async def _load_vectors() -> Dict[str, np.ndarray]:
    global _VECTORS
    if _VECTORS is not None:
        return _VECTORS
    rows = await db.company_embeddings.find({}, {"_id": 0, "master_company_id": 1, "vector": 1}).to_list(100000)
    _VECTORS = {r["master_company_id"]: np.array(r["vector"], dtype=float) for r in rows}
    return _VECTORS


def is_ready() -> bool:
    return _load_model() is not None


def embed_text(text: str) -> Optional[np.ndarray]:
    pipeline = _load_model()
    if pipeline is None or not text:
        return None
    try:
        return pipeline.transform([text])[0]
    except Exception:
        return None


async def semantic_scores(query: str, candidate_ids: List[str]) -> Dict[str, float]:
    """Cosine similarity (0..1) between the query and each candidate's vector."""
    qv = embed_text(query)
    if qv is None:
        return {}
    vectors = await _load_vectors()
    out = {}
    for mc_id in candidate_ids:
        v = vectors.get(mc_id)
        if v is not None:
            out[mc_id] = float(max(0.0, np.dot(qv, v)))  # both unit-normalized
    return out


async def similar_by_vector(master_company_id: str, candidate_ids: List[str]) -> Dict[str, float]:
    vectors = await _load_vectors()
    seed = vectors.get(master_company_id)
    if seed is None:
        return {}
    out = {}
    for mc_id in candidate_ids:
        if mc_id == master_company_id:
            continue
        v = vectors.get(mc_id)
        if v is not None:
            out[mc_id] = float(max(0.0, np.dot(seed, v)))
    return out


async def semantic_top(query: str, k: int = 80) -> List[Tuple[str, float]]:
    """Top-k companies by semantic cosine to the query across the whole index."""
    qv = embed_text(query)
    if qv is None:
        return []
    vectors = await _load_vectors()
    sims = [(mc_id, float(max(0.0, np.dot(qv, v)))) for mc_id, v in vectors.items()]
    sims.sort(key=lambda x: -x[1])
    return sims[:k]


async def warm_cache() -> bool:
    """Preload model + vectors at startup so the first request doesn't pay cold-load."""
    if _load_model() is None:
        return False
    await _load_vectors()
    return True
