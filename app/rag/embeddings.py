"""Dense encoder for the vector branch.

`Alibaba-NLP/gte-base-en-v1.5` is a symmetric 768-dim model: queries and
passages go through the same path with no instruction prefix (unlike the BGE
family, which needs one on the query side only). It ships custom modelling code
on the Hub, so sentence-transformers loads it with `trust_remote_code=True`.

There is deliberately no hashing/lexical fallback when the model is missing. A
fallback that silently returns meaningless vectors keeps every query answering
and every test passing while dense retrieval quietly does nothing -- the same
failure mode the app already refuses for its planner.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Sequence

DEFAULT_MODEL = "Alibaba-NLP/gte-base-en-v1.5"
# Pinned to a commit, never to a branch. `main` moving would silently change
# every vector in a database whose rows all claim to come from one model, and
# the resulting cosine numbers would look entirely reasonable.
DEFAULT_REVISION = "a829fd0e060bb84554da0dfd354d0de0f7712b7f"
EMBEDDING_DIM = 768

# Weights live here rather than in the ambient HF cache, so the model a
# deployment runs is a thing you can point at, copy, and check.
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "parcelpilot" / "models"

# Models that want an instruction prefix on the query side only. Keyed off the
# model name rather than a config flag so a symmetric model cannot silently
# inherit a prefix meant for another one: a wrong prefix raises no error
# anywhere, it just quietly costs recall.
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingUnavailable(RuntimeError):
    """The encoder could not be loaded, so dense retrieval cannot run."""


class GteEncoder:
    """Lazily loaded sentence-transformers encoder, L2-normalised output.

    Normalising here means pgvector's cosine distance (`<=>`) over the stored
    vectors is exactly `1 - dot`, so the SQL ordering is the true cosine
    ordering with no extra work at query time.
    """

    def __init__(self, model_name: str | None = None, *, revision: str | None = None,
                 cache_dir: Path | None = None, dim: int = EMBEDDING_DIM):
        self.model_name = model_name or os.getenv("PARCELPILOT_EMBEDDING_MODEL", DEFAULT_MODEL)
        # A pin only means something for the model it was taken from.
        default_revision = DEFAULT_REVISION if self.model_name == DEFAULT_MODEL else None
        self.revision = revision or os.getenv("PARCELPILOT_EMBEDDING_REVISION") or default_revision
        self.cache_dir = Path(os.getenv("PARCELPILOT_MODEL_CACHE", str(cache_dir or DEFAULT_CACHE_DIR)))
        self.dim = dim
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer

                        self.cache_dir.mkdir(parents=True, exist_ok=True)
                        self._model = SentenceTransformer(
                            self.model_name,
                            revision=self.revision,
                            cache_folder=str(self.cache_dir),
                            trust_remote_code=True,
                        )
                    except Exception as exc:  # noqa: BLE001 - re-raised with context
                        raise EmbeddingUnavailable(
                            f"Could not load the embedding model {self.model_name!r}: {exc}"
                        ) from exc
        return self._model

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(list(texts), show_progress_bar=False, normalize_embeddings=True)
        out = [[float(value) for value in row] for row in vectors]
        for row in out:
            if len(row) != self.dim:
                raise EmbeddingUnavailable(
                    f"{self.model_name!r} emits {len(row)} dimensions, but the schema stores "
                    f"vector({self.dim}). Changing models needs a migration and a full re-embed."
                )
        return out

    @property
    def fingerprint(self) -> str:
        """What the stored vectors were produced by. Written to `embedding_model`."""
        return f"{self.model_name}@{self.revision}" if self.revision else self.model_name

    def encode_query(self, query: str) -> list[float]:
        if "bge" in self.model_name.lower():
            return self.encode([_BGE_QUERY_PREFIX + query])[0]
        return self.encode([query])[0]
