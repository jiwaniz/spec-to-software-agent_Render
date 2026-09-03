"""
Embeds the example bank once and provides a retrieve() function to find
the closest gold-standard example for a given (in-progress) spec.

No vector DB — at 5-10 documents, a numpy array + cosine similarity is
simpler, free, and just as fast as FAISS/Chroma would be here.

Run `python -m app.rag.retrieval` once locally to build/cache the
embeddings to disk (embeddings.npy). This needs internet access on
first run to download the sentence-transformers model — it then caches
locally and works offline after that.
"""

import os
import numpy as np
from sentence_transformers import SentenceTransformer

# HF Spaces' ZeroGPU tier requires at least one @spaces.GPU-decorated
# function to exist, or the Space fails its startup check. This project
# has no real GPU workload (Groq runs the LLM externally, and this
# embedding model is small enough for CPU) -- but wrapping the one
# encode() call site lets the app deploy on the free ZeroGPU tier when
# a Space's CPU Basic option isn't selectable. Falls back to a no-op
# decorator for local development, where the `spaces` package isn't
# installed and isn't needed.
try:
    import spaces
    _gpu_decorator = spaces.GPU
except ImportError:
    def _gpu_decorator(func):
        return func

from app.rag.example_bank import EXAMPLE_BANK, spec_to_text
from app.schemas import SpecOutput

_MODEL_NAME = "all-MiniLM-L6-v2"
_CACHE_PATH = os.path.join(os.path.dirname(__file__), "embeddings.npy")

_model: SentenceTransformer | None = None
_bank_embeddings: np.ndarray | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


@_gpu_decorator
def _encode(texts: list[str]) -> np.ndarray:
    return _get_model().encode(texts, normalize_embeddings=True)


def _get_bank_embeddings() -> np.ndarray:
    global _bank_embeddings
    if _bank_embeddings is not None:
        return _bank_embeddings

    if os.path.exists(_CACHE_PATH):
        _bank_embeddings = np.load(_CACHE_PATH)
        return _bank_embeddings

    texts = [spec_to_text(s) for s in EXAMPLE_BANK]
    embeddings = _encode(texts)
    np.save(_CACHE_PATH, embeddings)
    _bank_embeddings = embeddings
    return embeddings


def retrieve(query_spec: SpecOutput, top_k: int = 1) -> list[SpecOutput]:
    """Return the top_k closest gold-standard examples to query_spec."""
    query_text = spec_to_text(query_spec)
    query_embedding = _encode([query_text])[0]

    bank_embeddings = _get_bank_embeddings()
    # embeddings are normalized, so dot product == cosine similarity
    similarities = bank_embeddings @ query_embedding
    top_indices = np.argsort(similarities)[::-1][:top_k]
    return [EXAMPLE_BANK[i] for i in top_indices]


def embedding_similarity(text_a: str, text_b: str) -> float:
    """Used by the Validation Agent to score requirement <-> code/test similarity."""
    emb = _encode([text_a, text_b])
    return float(emb[0] @ emb[1])


if __name__ == "__main__":
    # Builds and caches embeddings.npy. Run this once locally after
    # `pip install sentence-transformers` and with internet access.
    print("Building embeddings for the example bank...")
    _get_bank_embeddings()
    print(f"Cached to {_CACHE_PATH}")

    # Quick sanity check
    test_spec = EXAMPLE_BANK[1]  # Expense Tracking
    matches = retrieve(test_spec, top_k=1)
    print(f"Nearest match to '{test_spec.domain}' spec: '{matches[0].domain}' (should be itself)")
