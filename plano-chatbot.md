# Plano de Desenvolvimento — Chatbot Inteligente

## 1. Visão Geral

**Objetivo:** Criar um chatbot interativo capaz de manter conversas contextuais, responder perguntas com base em uma base de conhecimento, e executar ações quando solicitado.

**Stack sugerida:**
| Camada | Tecnologia |
|--------|------------|
| Frontend | React + TypeScript (Web) ou CLI via Python |
| Backend | Python (FastAPI) ou Node.js (Express) |
| LLM | OpenAI API / Anthropic / Ollama (local) |
| Vetor DB | ChromaDB / Pinecone / Qdrant (memória semântica) |
| Orquestração | LangChain / LlamaIndex /自定义 pipeline |
| Armazenamento | SQLite (dev) → PostgreSQL (prod) |
| Deploy | Docker + Docker Compose |

---

## 2. Fases do Projeto

### Fase 0 — Setup do Ambiente
- [ ] Criar repositório Git
- [ ] Configurar ambiente virtual (Python `venv` ou `poetry` / Node `pnpm`)
- [ ] Definir estrutura de diretórios
- [ ] Configurar linting e formatação (ruff, black, eslint, prettier)
- [ ] Criar arquivo `.env.example` com variáveis de ambiente

### Fase 1 — Núcleo do Chatbot (Modo CLI)
- [ ] Implementar loop de conversa simples (input → LLM → output)
- [ ] Suporte a múltiplos provedores de LLM (OpenAI, Anthropic, Ollama)
- [ ] Gerenciamento de histórico por sessão (janela de contexto)
- [ ] Sistema de prompts (system prompt, user prompt, few-shot)
- [ ] Testes unitários do core

### Fase 2 — Memória e Contexto
- [ ] Implementar memória de curto prazo (histórico em memória)
- [ ] Implementar memória de longo prazo (banco vetorial)
- [ ] Pipeline de chunking + embedding + storage
- [ ] Busca semântica (retrieve top-k chunks relevantes)
- [ ] Estratégia de sumarização quando contexto excede limite

### Fase 3 — Base de Conhecimento (RAG)
- [ ] Ingestão de documentos (PDF, TXT, Markdown, HTML)
- [ ] Chunking inteligente (por parágrafo, seção, ou token)
- [ ] Embeddings com modelo adequado (text-embedding-3-small, all-MiniLM-L6-v2)
- [ ] Indexação no banco vetorial
- [ ] Query augmentation (reescrita de pergunta + busca)
- [ ] Citar fontes nas respostas

### Fase 4 — API REST
- [ ] Endpoints: `POST /chat`, `GET /history`, `POST /ingest`
- [ ] Autenticação via API Key (Bearer token)
- [ ] Rate limiting
- [ ] Streaming de respostas (SSE)
- [ ] Logging estruturado (structlog ou winston)
- [ ] Documentação OpenAPI/Swagger

### Fase 5 — Frontend Web
- [ ] Interface de chat responsiva
- [ ] Componentes: caixa de input, bolhas de mensagem, indicador de digitação
- [ ] Suporte a Markdown e code highlighting nas respostas
- [ ] Histórico de conversas (sidebar)
- [ ] Upload de documentos para a base de conhecimento
- [ ] Tema claro/escuro

### Fase 6 — Funcionalidades Avançadas
- [ ] Ferramentas / Function Calling (calculadora, buscar clima, etc.)
- [ ] Memória persistente por usuário
- [ ] Multilíngue (detecção automática de idioma)
- [ ] Moderação de conteúdo (filtros de segurança)
- [ ] Feedback do usuário (thumbs up/down nas respostas)
- [ ] Avaliação de qualidade (ground-truth comparisons)

### Fase 7 — Produção e Deploy
- [ ] Dockerfile multi-stage
- [ ] docker-compose com serviços (api, db, vector-db, redis)
- [ ] CI/CD (GitHub Actions)
- [ ] Testes de integração e carga
- [ ] Monitoramento (Prometheus + Grafana ou Sentry)
- [ ] Estratégia de cache (Redis)
- [ ] Backup da base de conhecimento

---

## 3. Estrutura de Diretórios (Python)

```
chatbot/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── Makefile / Taskfile.yml
├── pyproject.toml / poetry.lock
├── README.md
├── src/
│   ├── main.py              # Entrypoint (CLI + API)
│   ├── config.py            # Config via pydantic-settings
│   ├── core/
│   │   ├── __init__.py
│   │   ├── llm.py           # Interface com LLMs
│   │   ├── chat.py          # Lógica do loop de conversa
│   │   ├── memory.py        # Memória de curto prazo
│   │   └── prompts.py       # Templates de prompt
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── embedder.py      # Geração de embeddings
│   │   ├── vector_store.py  # Interface com banco vetorial
│   │   ├── chunker.py       # Divisão de documentos
│   │   └── retriever.py     # Busca semântica
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py        # Endpoints REST
│   │   └── schemas.py       # Pydantic models
│   ├── tools/
│   │   ├── __init__.py
│   │   └── calculator.py    # Exemplo de ferramenta
│   └── db/
│       ├── __init__.py
│       ├── models.py        # SQLAlchemy / SQLModel
│       └── migrations/      # Alembic
├── tests/
│   ├── test_core.py
│   ├── test_rag.py
│   └── test_api.py
└── docs/
    └── architecture.md
```

---

## 4. Decisões Técnicas Importantes

| Decisão | Opções | Recomendação Inicial |
|---------|--------|----------------------|
| Orquestrador | LangChain vs LlamaIndex vs manual | LangChain (ecossistema maduro) |
| Vector DB | ChromaDB (local) vs Pinecone (cloud) | ChromaDB para dev, Pinecone para prod |
| Embeddings | OpenAI vs sentence-transformers | OpenAI para começar (mais simples) |
| LLM principal | GPT-4o-mini vs Claude Haiku vs local | GPT-4o-mini (custo × qualidade) |
| Framework API | FastAPI vs Express | FastAPI (async nativo, fácil) |
| Frontend | React vs Svelte vs Streamlit | React + Next.js (ecossistema) |

---

## 5. Riscos e Mitigação

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Custo de API cresce muito | Alto | Fallback para modelo local (Ollama) |
| Respostas alucinadas | Médio | RAG bem feito + validação pós-geração |
| Contexto muito grande | Médio | Chunking + sumarização seletiva |
| Privacidade de dados | Alto | Suporte a modelos locais + criptografia |
| Latência alta | Médio | Streaming, cache Redis, queries otimizadas |

---

## 6. Métricas de Sucesso (OKRs)

- **Qualidade:** ≥ 85% das respostas avaliadas como "úteis" pelo usuário
- **Velocidade:** Tempo até primeira resposta < 2s (streaming incluso)
- **Cobertura:** ≥ 90% das perguntas sobre a base de conhecimento são respondidas corretamente
- **Engenharia:** Testes com cobertura ≥ 80%
- **Deploy:** CI/CD com tempo de deploy < 5 min

---

## 7. Próximos Passos Imediatos

1. **Setup do projeto** — criar repositório, configurar ambiente, dependências
2. **CLI funcional** — loop de chat com OpenAI (~meio período)
3. **Memória + RAG básico** — ingestão de 1 documento + perguntas sobre ele (~1 período)
4. **API + Frontend mínimo** — chat funcional no navegador (~1 período)
5. **Iterar** — ferramentas, melhorias, produção
