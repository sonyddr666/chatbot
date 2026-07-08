# Chatbot Multiusuario com RAG Pessoal, Workspace e Skills

Aplicacao full-stack de chatbot com FastAPI, React/Vite, autenticacao, RAG por usuario, workspace seguro de arquivos, uploads separados da indexacao, providers por usuario, preferencias, sugestoes assistidas e skills com permissao.

Repositorio alvo: `sonyddr666/chatbot`.

## Visao Geral

O projeto evoluiu de um chatbot single-user para uma base multiusuario. Cada usuario autenticado tem:

- Login e cadastro proprios.
- Token de acesso usado por REST, SSE e WebSocket.
- Conversas, mensagens, documentos, preferencias, providers e skills filtrados por `user_id`.
- UserSpace fisico em `data/users/{user_id}`.
- RAG pessoal em collection propria `user_{user_id}_documents`.
- Workspace separado de uploads e separado do indice RAG.
- Onboarding inicial que salva perfil no banco, arquivo fisico e RAG pessoal.
- Providers pessoais com chave mascarada no retorno da API.
- Preferencias editaveis e sugestoes que exigem aceitar/rejeitar.
- Skills habilitaveis por usuario, com bloqueio de shell e log de execucao.
- UI para chat, documentos RAG, workspace, providers, settings e skills.

## Stack

- Backend: FastAPI, Uvicorn, SQLAlchemy, SQLite.
- Frontend: React, Vite, TypeScript, Tailwind.
- LLM: OpenAI, Anthropic, Ollama e providers OpenAI-compatible/custom.
- RAG: ChromaDB via LangChain.
- Embeddings: Hugging Face por padrao, OpenAI opcional.
- Upload/parsing: TXT, MD, JSON, CSV, PDF via `pypdf`, DOCX via `python-docx`.
- Streaming: WebSocket principal com fallback HTTP/SSE.
- Testes: `unittest`, dependencias de `pytest` declaradas para testes existentes que usam estilo pytest.

## Arquitetura Atual

```txt
frontend/
  React/Vite
  AuthPanel
  OnboardingModal
  Chat
  DocumentsPanel
  WorkspacePanel
  SkillsPanel
  SettingsPanel
  ProviderManager

src/
  api/
    app.py              FastAPI + WebSocket autenticado
    routes.py           Auth, chat, RAG, providers, skills, prefs
    workspace_routes.py Workspace e patch aprovado
    schemas.py          Schemas Pydantic
  core/
    auth.py             Senha, token, helpers de auth/RAG
    auth_required.py    Resolve usuario por Bearer token
    userspace.py        Pastas seguras por usuario
    workspace.py        Operacoes de arquivo por usuario
    ingestion.py        Upload original + extracao de texto
    patcher.py          Preview/apply patch com checksum e snapshot
    skill_runtime.py    Execucao segura de skills habilitadas
    skill_permissions.py Bloqueio de shell e skills desativadas
    user_provider_manager.py Providers pessoais
    preference_suggestions.py Sugestoes confirmaveis
  db/
    models.py           Modelos e migracoes SQLite leves
    repository.py       Repositorios filtrados por usuario
  rag/
    personal.py         Helpers de RAG isolado
    vector_store.py     Chroma
    retriever.py        Busca semantica
```

## Separacao de Dados

RAG nao e workspace.

```txt
Workspace
  Arquivos reais que o usuario pode listar, abrir, editar, mover e deletar.

Uploads
  Arquivos originais enviados pelo usuario.

RAG
  Texto extraido, chunkado e indexado em collection vetorial por usuario.
```

Estrutura criada por usuario:

```txt
data/
  users/
    {user_id}/
      profile/
        onboarding.md
      workspace/
      uploads/
        original/
          {upload_id}/
            arquivo.ext
      rag/
        documents/
        extracted/
        manifests/
      skills/
        user/
        audit/
```

## Funcionalidades Implementadas

### Autenticacao e Multiusuario

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- Senha com hash.
- Token assinado usado como `Authorization: Bearer <token>`.
- Rotas sensiveis exigem usuario autenticado.
- WebSocket `/ws?token=...` valida usuario antes de aceitar chat.
- Conversas e mensagens usam session id escopado por usuario.

### Onboarding Inicial

- `POST /api/v1/onboarding`
- Salva perfil em `user_profiles`.
- Gera `profile/onboarding.md`.
- Indexa o perfil inicial no RAG pessoal.
- Registra documento `perfil-inicial.md` em `knowledge_documents`.

### Chat

- `POST /api/v1/chat`
- `POST /api/v1/chat/stream`
- `POST /api/v1/chat/regenerate`
- `WebSocket /ws`
- Usa provider efetivo do usuario.
- Usa preferencias confirmadas no prompt.
- Usa skills habilitadas como contexto operacional.
- Usa RAG pessoal quando solicitado ou quando a skill `personal_rag` esta habilitada.
- Salva mensagens com metadados de provider/modelo.
- Cria sugestoes de preferencia sem derrubar o fluxo principal.

### Conversas, Mensagens e Export

- `GET /api/v1/conversations`
- `GET /api/v1/conversations/{session_id}`
- `PUT /api/v1/conversations/{session_id}/title`
- `DELETE /api/v1/conversations/{session_id}`
- `POST /api/v1/session/{session_id}/clear`
- `POST /api/v1/feedback`
- `PUT /api/v1/messages/{message_id}`
- `GET /api/v1/export/{session_id}?format=txt|json`
- Todas as operacoes sensiveis filtram por usuario autenticado.

### RAG Pessoal e Documentos

- `POST /api/v1/ingest`
- `POST /api/v1/upload`
- `GET /api/v1/documents`
- `DELETE /api/v1/documents/{doc_id}`
- Collection por usuario: `user_{user_id}_documents`.
- Metadata sempre forca `user_id` do usuario autenticado.
- Upload salva o original antes de indexar.
- A listagem de documentos retorna:
  - `filename`
  - `source`
  - `chunks`
  - `size`
  - `upload_path`
  - `checksum`
  - `status`
  - `parser`
  - `created_at`
- PDF e DOCX usam parser real, nao entram como lixo binario.

### Workspace por Usuario

- `GET /api/v1/workspace/tree?path=`
- `GET /api/v1/workspace/file?path=`
- `PUT /api/v1/workspace/file`
- `POST /api/v1/workspace/mkdir`
- `DELETE /api/v1/workspace/path?path=`
- `POST /api/v1/workspace/move`
- Operacoes passam por `safe_user_path`.
- Bloqueia path traversal e caminho absoluto.
- Usuario nao acessa workspace de outro usuario.
- Leitura/escrita inicial limitada a texto.
- Arquivo editavel limitado a 1 MB.

### Patch Aprovado no Workspace

- `POST /api/v1/workspace/patch/preview`
- `POST /api/v1/workspace/patch/apply`
- Preview gera diff e checksum esperado.
- Apply exige `expected_checksum`.
- Se o arquivo mudou depois do preview, a aplicacao bloqueia.
- Cria snapshot antes de aplicar.
- Registra auditoria em `skills/audit/workspace_patches.jsonl`.

### Preferencias e Sugestoes

- `GET /api/v1/preferences`
- `PUT /api/v1/preferences/{key}`
- `GET /api/v1/preference-suggestions`
- `POST /api/v1/preference-suggestions/{suggestion_id}/resolve`
- Preferencias ficam por usuario.
- Sugestoes ficam `pending` ate o usuario aceitar ou rejeitar.
- Aceitar uma sugestao atualiza `user_preferences`.
- Rejeitar nao altera preferencia.

### Providers

- Providers globais continuam como fallback.
- Providers pessoais ficam em `user_provider_configs`.
- `GET /api/v1/providers/user`
- `POST /api/v1/providers/user`
- `POST /api/v1/providers/user/{config_id}/activate`
- `GET /api/v1/providers/active-config`
- `POST /api/v1/providers/test`
- `GET /api/v1/health` mostra provider global quando publico e provider do usuario quando recebe token.
- Chaves pessoais sao mascaradas no retorno (`has_key`, `key_masked`).
- O chat usa o provider ativo do usuario quando configurado.

### Skills

Skills padrao:

- `simple_search`
- `search_and_answer`
- `personal_rag`

Endpoints:

- `GET /api/v1/skills`
- `PUT /api/v1/skills/{skill_name}`
- `GET /api/v1/skills/runs`

Regras:

- Skill so roda se estiver habilitada para o usuario.
- Skill com `requires_shell=True` nao executa.
- Busca web so roda quando uma skill de busca esta habilitada e a mensagem indica intencao de pesquisa.
- Execucoes ficam em `skill_runs`.

### Pool Codex/ChatGPT

O backend tem rotas autenticadas para pool OAuth/Codex:

- Listar contas e stats.
- Adicionar/remover contas.
- Refresh de tokens.
- Device Code OAuth.
- Extrair auth JSON.

As rotas publicas retornam dados sanitizados e nao devem expor `access_token` ou `refresh_token`.

## Frontend

UI disponivel em `http://localhost:3000` durante desenvolvimento.

Paineis principais:

- Login/cadastro.
- Onboarding inicial.
- Chat com WebSocket.
- Historico de conversas.
- Gerenciador de providers/modelos.
- Settings com preferencias e sugestoes.
- DocumentsPanel para upload/lista/delete de documentos RAG.
- WorkspacePanel para arquivo/pasta e patch preview/apply.
- SkillsPanel para ativar/desativar skills e ver logs.

## Como Rodar Localmente

### 1. Backend

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m src.main serve
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main serve
```

O backend sobe em:

```txt
http://0.0.0.0:8000
```

Localmente, acesse:

```txt
http://127.0.0.1:8000
```

### 2. Frontend

Em outro terminal:

```powershell
cd frontend
npm install
npm run dev
```

Abra:

```txt
http://localhost:3000
```

### Importante Sobre `python -m src.main`

```powershell
python -m src.main
```

sem argumento entra no modo CLI/chat.

Para rodar a API usada pelo frontend, use:

```powershell
python -m src.main serve
```

## Variaveis de Ambiente

O projeto le `.env` automaticamente via `pydantic-settings`.

Principais variaveis:

```env
DATABASE_URL=sqlite:///./data/chatbot.db
AUTH_SECRET_KEY=troque-este-segredo
USER_DATA_DIR=./data/users
API_PORT=8000

LLM_PROVIDER=custom_openai
CUSTOM_PROFILE=opencode-zen-free
CUSTOM_API_KEY=
CUSTOM_BASE_URL=
CUSTOM_MODEL=

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OPENCODE_ZEN_API_KEY=
OPENCODE_GO_API_KEY=

EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=all-MiniLM-L6-v2
VECTOR_DB_TYPE=chroma
CHROMA_PERSIST_DIR=./data/chroma

ENABLE_RAG=true
ENABLE_MODERATION=true
ENABLE_MULTILANG=true
MAX_UPLOAD_SIZE_MB=10
```

## Comandos Uteis

```powershell
# Backend API
python -m src.main serve

# CLI simples
python -m src.main chat

# Frontend dev
cd frontend
npm run dev

# Build frontend
cd frontend
npm run build

# Compilar Python
python -m compileall -q src
```

Observacao: o modo `python -m src.main ingest --file arquivo.pdf` ainda nao e o caminho funcional principal. Use upload pela API/UI para documentos.

## Testes Seguros e Curtos

Bateria usada nas fases recentes, evitando testes conhecidos por travar:

```powershell
python -m unittest tests.test_route_security tests.test_skill_runtime tests.test_auth_required tests.test_skills_context tests.test_userspace tests.test_workspace_service tests.test_workspace_routes tests.test_ingestion tests.test_rag_isolation tests.test_preferences tests.test_preference_suggestions tests.test_user_providers tests.test_user_provider_llm tests.test_skill_permissions tests.test_skill_runs tests.test_patcher tests.test_requirements tests.test_frontend_documents_panel tests.test_frontend_preference_suggestions tests.test_frontend_user_providers tests.test_frontend_workspace_patch_api tests.test_frontend_workspace_patch_ui
```

Outros checks:

```powershell
python -m compileall -q src
git diff --check

cd frontend
npm run build
```

Regra operacional atual: nao rodar `python -m unittest tests.test_auth_multiuser` ate ele ser estabilizado, porque ja foi tratado como teste problematico/lento no fluxo do projeto.

## Seguranca Implementada

- Rotas sensiveis exigem token.
- WebSocket exige token.
- Dados de conversas, mensagens, documentos, preferencias, providers e skills sao filtrados por usuario.
- Paths de workspace/upload passam por validacao de area e resolucao segura.
- Bloqueia `..` e caminhos absolutos no UserSpace.
- API keys pessoais nao voltam cruas para o frontend.
- Tokens de pool Codex sao sanitizados nas respostas publicas.
- Skills com shell ficam bloqueadas.
- Patch de workspace exige checksum e cria snapshot.

## Limites Conhecidos

- A criptografia local de API key pessoal usa codificacao local simples para ambiente dev; para producao, trocar por KMS/Fernet/secret manager.
- CORS esta amplo para desenvolvimento local.
- `python -m src.main ingest` ainda esta como placeholder.
- Smoke manual completo exige dois terminais: backend em `serve` e frontend em `npm run dev`.
- A UI builda, mas o bundle principal ainda gera aviso de chunk grande do Vite.

## O Que Nao Deve Ir Para o GitHub

Nao subir:

- `.env`
- `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `data/`
- logs
- caches
- `__pycache__/`
- `.pytest_cache/`

Esses arquivos sao runtime local, dependencias, build output ou dados sensiveis.

## Status Atual

Funcionalidades principais implementadas e verificadas em bateria curta:

- Login e cadastro.
- Multiusuario.
- UserSpace por usuario.
- RAG pessoal.
- Upload original separado da indexacao.
- PDF/DOCX com parser real.
- Workspace seguro.
- Patch aprovado com diff/checksum/snapshot.
- Preferencias por usuario.
- Sugestoes confirmaveis.
- Providers pessoais.
- Skills com permissao/log.
- UI para chat, documentos, workspace, providers, settings e skills.

Ainda falta, antes de chamar de producao final:

- Smoke manual completo de ponta a ponta em ambiente real.
- Revisao de seguranca de producao para CORS e criptografia de secrets.
- Estabilizar ou substituir o teste `tests.test_auth_multiuser`.
