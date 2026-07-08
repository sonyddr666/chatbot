"""Helpers for per-user RAG isolation."""

from typing import Optional

from src.core.auth import rag_collection_for_user
from src.rag.retriever import retrieve_context
from src.rag.vector_store import add_documents, delete_documents


def user_rag_collection(user_id: int) -> str:
    return rag_collection_for_user(user_id)


def add_user_documents(
    user_id: int,
    texts: list[str],
    metadatas: Optional[list[dict]] = None,
) -> list[str]:
    isolated_metadatas = []
    for metadata in metadatas or [{}] * len(texts):
        isolated_metadatas.append({**(metadata or {}), "user_id": user_id})
    return add_documents(
        texts,
        isolated_metadatas,
        collection_name=user_rag_collection(user_id),
    )


def retrieve_user_context(
    user_id: int,
    query: str,
    k: int = 4,
    min_score: Optional[float] = None,
) -> str:
    return retrieve_context(
        query,
        k=k,
        min_score=min_score,
        collection_name=user_rag_collection(user_id),
    )


def delete_user_documents(user_id: int, ids: list[str]) -> None:
    delete_documents(ids, collection_name=user_rag_collection(user_id))
