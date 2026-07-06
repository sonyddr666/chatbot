"""Geração de embeddings — com fallback automático."""

from typing import List, Optional
from langchain_core.embeddings import Embeddings

from src.config import settings

_embedder: Optional[Embeddings] = None


def get_embedder() -> Embeddings:
    """Retorna o melhor modelo de embeddings disponível."""
    global _embedder
    if _embedder is not None:
        return _embedder

    # Tenta OpenAI
    if settings.openai_api_key:
        try:
            from langchain_openai import OpenAIEmbeddings
            _embedder = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.openai_api_key,
            )
            return _embedder
        except Exception:
            pass

    # Fallback: HuggingFace (local, gratuito)
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        _embedder = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
        )
        return _embedder
    except Exception:
        pass

    # Último fallback: embeddings dummy (para dev/test)
    from langchain_core.embeddings import Embeddings as BaseEmbeddings

    class DummyEmbeddings(BaseEmbeddings):
        def embed_documents(self, texts: List[str]) -> List[List[float]]:
            return [[0.0] * 384 for _ in texts]
        def embed_query(self, text: str) -> List[float]:
            return [0.0] * 384

    _embedder = DummyEmbeddings()
    return _embedder


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Gera embeddings para uma lista de textos."""
    return get_embedder().embed_documents(texts)


def embed_query(text: str) -> List[float]:
    """Gera embedding para uma query."""
    return get_embedder().embed_query(text)
