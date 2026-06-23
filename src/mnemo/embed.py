"""Optional semantic embedding layer (pluggable, lazy-loaded).

Default model is multilingual (notes may be Turkish). Heavy ML deps live behind
the ``embed`` extra; the rest of mnemo works on FTS5 alone if they are absent.

This module is wired but not yet used by the index in F1 — semantic search
(vector store via sqlite-vec) lands in F2/F4. Kept here so the interface is
fixed and importable without pulling torch.
"""

from __future__ import annotations

from collections.abc import Sequence

# Multilingual MiniLM: fast + stable, handles Turkish notes.
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model = None

    @staticmethod
    def is_available() -> bool:
        try:
            import sentence_transformers  # noqa: F401
        except Exception:
            return False
        return True

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: Sequence[str]):
        """Return L2-normalized embeddings for a batch of texts."""
        model = self._ensure()
        return model.encode(list(texts), normalize_embeddings=True)
