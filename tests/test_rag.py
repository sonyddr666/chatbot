"""Testes do módulo RAG."""

import pytest
from src.rag.chunker import split_text, split_documents


class TestChunker:
    def test_split_text_curto(self):
        chunks = split_text("Texto curto.", chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0] == "Texto curto."

    def test_split_text_longo(self):
        text = "Palavra " * 500  # ~3500 chars
        chunks = split_text(text, chunk_size=500)
        assert len(chunks) > 1

    def test_split_documents_multiplos(self):
        docs = ["Doc um. " * 50, "Doc dois. " * 50]
        chunks = split_documents(docs, chunk_size=300)
        assert len(chunks) >= 2


class test_embedder:
    def test_get_embedder_returns_embeddings(self):
        from src.rag.embedder import get_embedder
        embedder = get_embedder()
        assert hasattr(embedder, "embed_documents")
        assert hasattr(embedder, "embed_query")
