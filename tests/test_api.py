"""Testes da API REST."""

import os
import pytest
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)

# Pular testes de integração se não tiver API key
skip_if_no_key = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY não configurada",
)


class TestHealth:
    def test_health_return_ok(self):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "llm_provider" in data
        assert "vector_db" in data


class TestChat:
    @skip_if_no_key
    def test_chat_sem_rag(self):
        response = client.post(
            "/api/v1/chat",
            json={"message": "Olá", "session_id": "test-session"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["session_id"] == "test-session"


class TestIngest:
    def test_ingest_texto_vazio(self):
        response = client.post(
            "/api/v1/ingest",
            json={"text": "", "source": "test"},
        )
        assert response.status_code == 400

    @skip_if_no_key
    def test_ingest_texto_valido(self):
        response = client.post(
            "/api/v1/ingest",
            json={"text": "Texto de teste para ingestão.", "source": "test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["chunks_count"] >= 1
        assert len(data["ids"]) == data["chunks_count"]
