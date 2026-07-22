"""EmbeddingProvider (D-S2) — pluggable, provider-agnostic.

v1 ships a LOCAL deterministic provider (feature hashing + tf weighting + L2 norm):
the most stable option in the current environment, with NO external dependency, fully
reproducible. The interface lets us swap to a managed model later WITHOUT changing the
profile contract or any consumer. Every embedding records provider/model/version.
"""

import math
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


_provider: EmbeddingProvider = LocalEmbeddingProvider()


def get_provider() -> EmbeddingProvider:
    return _provider


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return round(sum(x * y for x, y in zip(a, b)), 6)  # vectors are L2-normalized
