"""Orquestração de busca semântica + formatação de contexto."""

from typing import List, Optional

from src.rag.vector_store import similarity_search


def retrieve_context(
    query: str,
    k: int = 4,
    min_score: Optional[float] = None,
    collection_name: str = "documents",
) -> str:
    """Busca chunks relevantes e retorna como texto formatado para contexto."""
    documents = similarity_search(query, k=k, collection_name=collection_name)

    if not documents:
        return ""

    context_parts = []
    for i, doc in enumerate(documents, 1):
        source = doc.metadata.get("source", "desconhecida")
        context_parts.append(f"[{i}] (fonte: {source})\n{doc.page_content}")

    return "\n\n".join(context_parts)
