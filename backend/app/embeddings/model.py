"""The sentence-embedding model (Heet — FR-07, US-05 groundwork, confirmed in Sprint 0).

``all-MiniLM-L6-v2``: 384 dimensions (``EMBEDDING_DIM``), ~80 MB, fast enough on CPU for
similar-requirement hints under 500 ms (``eval/latency/hints_bench.py``). Vectors are
L2-normalised, so cosine similarity is a dot product and pgvector's ``<=>`` gives ``1 - cosine``.

Everything that embeds goes through :class:`Embedder`, so tests use :class:`HashingEmbedder`
(deterministic, no download) and a model upgrade is one class plus a re-embed of rows whose
``model_version`` differs.
"""

import hashlib
import math
import threading
from collections.abc import Sequence
from functools import lru_cache
from typing import Any, Protocol

from app.models.embedding import EMBEDDING_DIM

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_VERSION = "all-MiniLM-L6-v2"
BATCH_SIZE = 64


class Embedder(Protocol):
    version: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One normalised ``EMBEDDING_DIM`` vector per text, in order."""
        ...


class SentenceTransformerEmbedder:
    """The production embedder. The model loads on first use, once per process."""

    version = MODEL_VERSION

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model_name = model_name
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                # Imported lazily: torch takes seconds to import and the API process never embeds
                # until the first similar-hint request (Sprint 3).
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self._model_name, device="cpu")
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._load().encode(
            list(texts),
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in row] for row in vectors]


class HashingEmbedder:
    """Deterministic stand-in for tests: texts sharing words get similar vectors.

    Each lower-cased word is hashed to a few dimensions; the vector is normalised. No model,
    no network, and identical text always gives an identical vector.
    """

    version = "hashing-test"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for word in text.lower().split():
            digest = hashlib.sha256(word.strip(".,;:!?\"'()").encode()).digest()
            for i in range(0, 6, 2):
                vector[int.from_bytes(digest[i : i + 2], "big") % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


@lru_cache
def get_embedder() -> Embedder:
    """The process-wide embedder (tests override this)."""
    return SentenceTransformerEmbedder()
