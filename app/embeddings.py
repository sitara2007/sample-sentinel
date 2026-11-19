from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import structlog

from app.config import get_settings

log = structlog.get_logger(__name__)

_MODEL: Any = None
_LOAD_ATTEMPTED = False


def embeddings_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return load_model() is not None


def load_model() -> Any:
    global _MODEL, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _MODEL
    _LOAD_ATTEMPTED = True
    try:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        _MODEL = SentenceTransformer(settings.embedding_model)
        log.info("embedding_model_loaded", model=settings.embedding_model)
    except Exception as exc:
        log.warning("embedding_model_unavailable", error=str(exc))
        _MODEL = None
    return _MODEL


@lru_cache(maxsize=2048)
def _encode_cached(text: str) -> tuple[float, ...]:
    model = load_model()
    if model is None:
        raise RuntimeError("embedding model unavailable")
    vector = model.encode(text, normalize_embeddings=True)
    return tuple(float(x) for x in vector)


def encode(text: str) -> np.ndarray | None:
    if load_model() is None:
        return None
    return np.asarray(_encode_cached(text), dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)
