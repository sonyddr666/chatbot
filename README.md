# Chatbot Inteligente

Chatbot com RAG (Retrieval-Augmented Generation), memória semântica e suporte a múltiplos provedores de LLM.

## Stack

- **LLM:** OpenAI / Anthropic / Ollama
- **Orquestração:** LangChain
- **Vector DB:** ChromaDB (dev) / Pinecone (prod)
- **API:** FastAPI
- **Armazenamento:** SQLite / PostgreSQL

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

pip install -r requirements.txt
cp .env.example .env
# Edite .env com suas chaves

python -m src.main
```

## Comandos

```bash
# CLI interativa
python -m src.main chat

# Ingestão de documentos
python -m src.main ingest --file documento.pdf

# API server
python -m src.main serve
```
