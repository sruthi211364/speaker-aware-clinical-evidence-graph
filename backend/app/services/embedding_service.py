"""Local embedding generation for the RAG grounding layer.

Uses fastembed (ONNX runtime, no torch) to run bge-small-en-v1.5 locally
rather than calling a hosted embeddings API (e.g. Voyage AI, which Anthropic
recommends for production -- see README for the tradeoff). This keeps the
prototype's only paid dependency at ANTHROPIC_API_KEY.
"""

from functools import lru_cache

_MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _get_model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=_MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    return [vec.tolist() for vec in model.embed(texts)]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
