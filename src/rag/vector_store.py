"""Interface com banco vetorial (ChromaDB por padrão)."""

from typing import List, Optional
from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config import settings
from src.rag.embedder import get_embedder


def get_vector_store(collection_name: str = "documents") -> Chroma:
    """Retorna (e cria se não existir) o banco vetorial."""
    embedder = get_embedder()

    if settings.vector_db_type == "chroma":
        return Chroma(
            collection_name=collection_name,
            embedding_function=embedder,
            persist_directory=settings.chroma_persist_dir,
        )
    else:
        raise ValueError(f"Vector DB type não suportado: {settings.vector_db_type}")


def add_documents(
    texts: List[str],
    metadatas: Optional[List[dict]] = None,
    collection_name: str = "documents",
) -> List[str]:
    """Adiciona documentos ao banco vetorial e retorna os IDs."""
    vector_store = get_vector_store(collection_name)

    documents = [
        Document(page_content=text, metadata=metadata or {})
        for text, metadata in zip(texts, metadatas or [{}] * len(texts))
    ]

    ids = vector_store.add_documents(documents)
    # ChromaDB salva automaticamente
    return ids


def delete_documents(
    ids: List[str],
    collection_name: str = "documents",
) -> None:
    """Remove documentos do banco vetorial pelos IDs conhecidos."""
    if not ids:
        return
    vector_store = get_vector_store(collection_name)
    vector_store.delete(ids=ids)


def similarity_search(
    query: str,
    k: int = 4,
    collection_name: str = "documents",
) -> List[Document]:
    """Busca os K chunks mais similares à query."""
    vector_store = get_vector_store(collection_name)
    return vector_store.similarity_search(query, k=k)
