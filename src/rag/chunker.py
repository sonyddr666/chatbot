"""Divisão inteligente de documentos em chunks."""

from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter


def get_text_splitter(
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> RecursiveCharacterTextSplitter:
    """Retorna um splitter configurado para documentos."""
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )


def split_text(text: str, chunk_size: int = 1000) -> List[str]:
    """Divide um texto em chunks."""
    splitter = get_text_splitter(chunk_size=chunk_size)
    return splitter.split_text(text)


def split_documents(documents: List[str], chunk_size: int = 1000) -> List[str]:
    """Divide múltiplos documentos em chunks."""
    all_chunks = []
    for doc in documents:
        all_chunks.extend(split_text(doc, chunk_size))
    return all_chunks
