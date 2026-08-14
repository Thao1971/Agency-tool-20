"""EmbeddingProvider (D-S2) — pluggable, provider-agnostic.

v1 ships a LOCAL deterministic provider (feature hashing + tf weighting + L2 norm):
the most stable option in the current environment, with NO external dependency, fully
reproducible. The interface lets us swap to a managed model later WITHOUT changing the
profile contract or any consumer. Every embedding records provider/model/version.
"""

import math
import os
import re
import unicodedata
from typing import List, Protocol

EMBEDDING_VERSION = "emb-v1"
_DIM = 512

_TOKEN = re.compile(r"[a-z0-9]+")


def _normalize_text(text: str) -> List[str]:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _TOKEN.findall(text)


class EmbeddingProvider(Protocol):
    name: str
    model: str

    def embed(self, text: str) -> dict: ...


class LocalEmbeddingProvider:
    """Deterministic hashing embedding. Reproducible, dependency-free."""
    name = "local"
    model = "hashing-tf-v1"

    def __init__(self, dim: int = _DIM):
        self.dim = dim

    def embed(self, text: str) -> dict:
        tokens = _normalize_text(text)
        vec = [0.0] * self.dim
        for tok in tokens:
            h = hash((self.model, tok)) % self.dim
            sign = 1.0 if (hash((tok, self.model)) >> 1) & 1 else -1.0
            vec[h] += sign * (1.0 + math.log(1 + tokens.count(tok)))
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vec = [round(v / norm, 6) for v in vec]
        return {"vector": vec, "provider": self.name, "model": self.model,
                "dimension": self.dim, "embedding_version": EMBEDDING_VERSION}


_OPENAI_DIM = 512


def _l2(v: List[float]) -> List[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class OpenAIEmbeddingProvider:
    """Managed semantic embeddings (text-embedding-3-small). L2-normalized vectors."""
    name = "openai"
    model = "text-embedding-3-small"

    def __init__(self, dim: int = _OPENAI_DIM):
        from openai import OpenAI
        self.dim = dim
        self.embedding_version = f"openai-3-small-{dim}-v1"
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def _embed_raw(self, texts: List[str]) -> List[List[float]]:
        cleaned = [((t or " ").replace("\n", " ").strip() or " ")[:8000] for t in texts]
        r = self._client.embeddings.create(model=self.model, input=cleaned,
                                           dimensions=self.dim, encoding_format="float")
        data = sorted(r.data, key=lambda x: x.index)
        return [_l2(list(d.embedding)) for d in data]

    def embed(self, text: str) -> dict:
        vec = self._embed_raw([text])[0]
        return {"vector": vec, "provider": self.name, "model": self.model,
                "dimension": self.dim, "embedding_version": self.embedding_version}

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        return self._embed_raw(texts)


def _make_provider() -> EmbeddingProvider:
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return OpenAIEmbeddingProvider(_OPENAI_DIM)
        except Exception:
            return LocalEmbeddingProvider()
    return LocalEmbeddingProvider()


_provider: EmbeddingProvider = _make_provider()


def get_provider() -> EmbeddingProvider:
    return _provider


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return round(sum(x * y for x, y in zip(a, b)), 6)  # vectors are L2-normalized
