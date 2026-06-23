"""Optional semantic embedding layer (pluggable, lazy).

Backend: fastembed (ONNX) — fast cold-start, light install, friendly to
`uv tool install`. Default model is multilingual (notes may be Turkish).
Everything degrades to FTS5 when the ``embed`` extra is absent.
"""

from __future__ import annotations

from collections.abc import Sequence

# Multilingual MiniLM: fast + stable, handles Turkish. 384-dim.
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_DIM = 384


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL, dim: int = DEFAULT_DIM):
        self.model_name = model_name
        self.dim = dim
        self._model = None

    @staticmethod
    def is_available() -> bool:
        try:
            import fastembed  # noqa: F401
            import sqlite_vec  # noqa: F401
        except Exception:
            return False
        return True

    def _ensure(self):
        if self._model is None:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from fastembed import TextEmbedding

                self._model = TextEmbedding(self.model_name)
        return self._model

    def encode_one(self, text: str) -> list[float]:
        model = self._ensure()
        vec = next(iter(model.embed([text])))
        return [float(x) for x in vec]

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._ensure()
        return [[float(x) for x in v] for v in model.embed(list(texts))]
