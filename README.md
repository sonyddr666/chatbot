# Chatbot Multiusuario com RAG Pessoal, Workspace, Providers e Skills

Aplicacao full-stack de chatbot com backend FastAPI e frontend React/Vite. O projeto foi evoluido para suportar login, cadastro, usuarios separados, RAG pessoal por usuario, onboarding inicial, workspace seguro de arquivos, uploads separados da indexacao, providers pessoais, preferencias, sugestoes inteligentes e skills com permissao/log.

Repositorio alvo: `sonyddr666/chatbot`.

## Status Atual

O projeto hoje e uma base funcional de chatbot multiusuario. As funcionalidades principais ja implementadas sao:

- Login.
- Cadastro.
- Autenticacao por token.
- Multiusuario com isolamento por `user_id`.
- Conversas e mensagens por usuario.
- Onboarding inicial.
- Perfil inicial salvo no banco, em arquivo e no RAG pessoal.
- Refazer onboarding substitui o perfil anterior no RAG pessoal.
- RAG pessoal por usuario.
- Upload de documentos separado do workspace.
- Arquivos originais preservados em pasta propria.
- Parsing real de TXT, MD, JSON, CSV, PDF e DOCX.
- Listagem e remocao de documentos RAG.
- Limpeza de chunks vetoriais ao apagar documento.
- Registro de falha quando upload/parsing da erro.
- Workspace fisico por usuario.
- Operacoes seguras de arquivo/pasta no workspace.
- Gerenciador visual com arvore recursiva, drag-and-drop, importacao e confirmacoes.
- IA capaz de planejar criacao, edicao, movimentacao, renomeacao e exclusao de arquivos/pastas.
- Plano da IA persistido e executado somente depois da confirmacao do usuario.
- RAG opt-in para uploads e arquivos do Workspace; sugestoes nunca indexam automaticamente.
- Patch aprovado com preview, diff, checksum, snapshot e auditoria.
- Preferencias por usuario.
- Sugestoes de preferencias aceitas/rejeitadas manualmente.
- Providers pessoais por usuario.
- Fallback para providers globais.
- Chaves de provider mascaradas no retorno da API.
- Uso do provider ativo do usuario no chat.
- Skills por usuario.
- Bloqueio de skills que exigem shell.
- Log de execucao de skills.
- Skill `personal_rag` forca consulta ao RAG pessoal quando habilitada.
- UI para auth, onboarding, chat, documentos, workspace, skills, providers e settings.
- Build do frontend validado.
- Bateria curta de testes segura documentada.

## Stack

- Backend: FastAPI, Uvicorn, SQLAlchemy e SQLite.
- Frontend: React, TypeScript, Vite e Tailwind.
- LLM: OpenAI, Anthropic, Ollama e providers custom/OpenAI-compatible.
- RAG: ChromaDB via LangChain.
- Embeddings: Hugging Face por padrao, OpenAI opcional.
- Upload/parsing: texto simples, Markdown, JSON, CSV, PDF com `pypdf`, DOCX com `python-docx`.
- Streaming: WebSocket principal e rota HTTP/SSE.
- Testes: `unittest`; dependencias de `pytest` declaradas para testes existentes em estilo pytest.

## Visao Geral

Cada usuario autenticado tem um espaco proprio:

- Conta propria com usuario/senha.
- Token usado em REST, streaming e WebSocket.
- Perfil inicial proprio.
- Conversas proprias.
- Mensagens proprias.
- Documentos proprios.
- RAG proprio.
- Workspace proprio.
- Uploads proprios.
- Providers pessoais.
- Preferencias pessoais.
- Skills habilitadas/desabilitadas por usuario.
- Historico de execucao de skills por usuario.

O objetivo da arquitetura e impedir mistura de dados entre usuarios. O workspace nao e o RAG. O upload original nao e o indice vetorial. O provider global nao sobrescreve provider pessoal ativo quando o usuario tem configuracao propria.

## Arquitetura de Pastas

```txt
frontend/
  src/
    App.tsx
    components/
      AuthPanel.tsx
      OnboardingModal.tsx
      ChatInput.tsx
      ChatMessage.tsx
      DocumentsPanel.tsx
      WorkspacePanel.tsx
      SkillsPanel.tsx
      SettingsPanel.tsx
      ProviderManager.tsx
      DiffViewer.tsx
    hooks/
      useChatStore.ts
      useWebSocket.ts
    lib/
      api.ts

src/
  api/
    app.py
    routes.py
    workspace_routes.py
    schemas.py
  core/
    auth.py
    auth_required.py
    userspace.py
    workspace.py
    ingestion.py
    patcher.py
    skill_runtime.py
    skill_permissions.py
    user_provider_manager.py
    provider_manager.py
    preference_suggestions.py
    llm.py
    chat.py
  db/
    models.py
    repository.py
  rag/
    personal.py
    vector_store.py
    retriever.py
    chunker.py
    embedder.py
  tools/
    web_search.py
    calculator.py
    weather.py
```

## Separacao de Dados

O projeto separa tres conceitos que antes costumam se misturar:

- Workspace: arquivos reais que o usuario cria, edita, move e apaga.
- Uploads: arquivos originais preservados; somente os selecionados pelo usuario viram conhecimento no RAG.
- RAG: texto extraido, chunkado e indexado em collection vetorial.

Estrutura fisica criada por usuario:

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
          workspace_patches.jsonl
```

Collection vetorial por usuario:

```txt
user_{user_id}_documents
```

Exemplo:

```txt
user_1_documents
user_2_documents
```

## Fluxo Principal do Usuario

1. Usuario faz cadastro.
2. Backend cria conta e garante o UserSpace em `data/users/{user_id}`.
3. Usuario faz login.
4. Frontend guarda o token e usa nas chamadas autenticadas.
5. Usuario preenche onboarding inicial.
6. Backend salva o perfil no banco.
7. Backend grava `profile/onboarding.md`.
8. Backend indexa o perfil inicial no RAG pessoal.
9. Usuario conversa no chat.
10. Chat usa provider efetivo, preferencias, skills e RAG pessoal quando aplicavel.
11. Usuario pode subir documentos, editar workspace, configurar provider, ajustar preferencias e ativar skills.

## Funcionalidades Detalhadas

### Login, Cadastro e Auth

Implementado:

- Cadastro de usuario.
- Login com senha.
- Hash de senha.
- Token assinado.
- `GET /api/v1/auth/me` para recuperar o usuario logado.
- Protecao de rotas sensiveis com `Authorization: Bearer <token>`.
- WebSocket protegido com `?token=...`.

Rotas:

```txt
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

### Multiusuario

Implementado:

- `users` separa contas.
- `user_profiles` separa onboarding/perfil.
- `conversations` e `messages` filtram por usuario.
- `knowledge_documents` filtra documentos por usuario.
- `user_preferences` separa preferencias.
- `preference_suggestions` separa sugestoes.
- `user_provider_configs` separa providers pessoais.
- `user_skills` separa ativacao de skills.
- `skill_runs` separa logs de skills.
- RAG usa collection propria por usuario.
- UserSpace fisico usa pasta propria por usuario.

### Onboarding Inicial

Implementado:

- Formulario inicial no frontend.
- Salvamento do perfil no banco.
- Geracao de arquivo Markdown no UserSpace.
- Ingestao do perfil no RAG pessoal.
- Criacao de documento `perfil-inicial.md`.

Rota:

```txt
POST /api/v1/onboarding
```

Campos principais:

- Nome de exibicao.
- Objetivo de uso.
- Preferencias.
- Provider preferido.
- Tom/estilo esperado.
- Informacoes que ajudam o chatbot a responder melhor.

### Chat

Implementado:

- Chat REST.
- Chat streaming.
- OpenCode usa SSE direto para preservar `reasoning_content` do DeepSeek e os tokens da resposta final.
- O balão mostra estados de processamento antes do primeiro token: contexto, skills e modelo pensando.
- O bloco Thinking aparece durante o raciocinio e permanece acessivel enquanto a resposta final e transmitida.
- O bloco expansivel `Ferramentas e Skills` confirma cada pesquisa concluida, informa a Skill usada e mostra links das fontes.
- Respostas que chegam em um bloco grande sao divididas visualmente para evitar que o texto apareca inteiro de uma vez.
- Regeneracao de resposta.
- WebSocket autenticado.
- Historico por sessao.
- Mensagens salvas com metadados de provider/modelo.
- Uso de provider ativo do usuario.
- Uso de preferencias confirmadas.
- Uso de skills habilitadas como contexto.
- Uso de RAG pessoal quando a mensagem pede conhecimento/documentos ou quando `personal_rag` esta habilitada.
- Criacao nao bloqueante de sugestoes de preferencia.

Rotas:

```txt
POST /api/v1/chat
POST /api/v1/chat/stream
POST /api/v1/chat/regenerate
WS   /ws?token=<token>
```

### Conversas, Mensagens, Feedback e Export

Implementado:

- Listar conversas.
- Abrir conversa.
- Renomear conversa.
- Apagar conversa.
- Limpar sessao.
- Editar mensagem.
- Registrar feedback.
- Exportar conversa em TXT ou JSON.

Rotas:

```txt
GET    /api/v1/conversations
GET    /api/v1/conversations/{session_id}
PUT    /api/v1/conversations/{session_id}/title
DELETE /api/v1/conversations/{session_id}
POST   /api/v1/session/{session_id}/clear
PUT    /api/v1/messages/{message_id}
POST   /api/v1/feedback
GET    /api/v1/export/{session_id}?format=txt
GET    /api/v1/export/{session_id}?format=json
```

### RAG Pessoal

Implementado:

- Helper central para adicionar documentos no RAG do usuario.
- Helper central para recuperar contexto do RAG do usuario.
- Helper central para apagar documentos/chunks do RAG do usuario.
- Metadata sempre recebe `user_id` do usuario autenticado.
- Collection sempre deriva de `user_id`, nao de input livre do frontend.
- Manual ingest registra documento no banco.
- Upload de documentos pode registrar o original sem indexar.
- Ingestao posterior usa somente o original salvo do mesmo usuario.
- Delecao remove documento do banco e chunks vetoriais.

Rotas:

```txt
POST   /api/v1/ingest
POST   /api/v1/upload
POST   /api/v1/documents/upload
POST   /api/v1/documents/{doc_id}/ingest
GET    /api/v1/documents
DELETE /api/v1/documents/{doc_id}
```

Campos retornados na listagem de documentos:

- `id`
- `filename`
- `source`
- `chunks`
- `size`
- `upload_path`
- `extracted_path`
- `checksum`
- `status`
- `parser`
- `error_message`
- `manifest_path`
- `created_at`

Status esperados:

- `indexed`: documento salvo e indexado no RAG.
- `uploaded`: original salvo, aguardando o usuario pedir ingestao.
- `error`: upload registrado, mas parsing/indexacao falhou.

### Upload e Parsing

Implementado:

- Upload original salvo antes de indexar.
- DocumentsPanel usa envio em duas etapas: salvar original e depois "Ingerir no RAG".
- `/api/v1/upload` e `/api/v1/documents/upload` apenas salvam o original; a ingestao exige selecao posterior.
- Caminho fisico fica dentro de `uploads/original/{upload_id}`.
- Depois da ingestao pelo DocumentsPanel, o texto derivado fica em `rag/extracted/` do mesmo usuario.
- Checksum salvo para rastreabilidade.
- Parser usado fica salvo no banco.
- Erro de parsing fica salvo em `error_message`.
- Arquivos PDF e DOCX sao extraidos com parser real.
- Falha de parsing nao deve derrubar a integridade do usuario; ela vira documento com status de erro.

Formatos suportados:

- `.txt`
- `.md`
- `.json`
- `.csv`
- `.pdf`
- `.docx`

### Workspace por Usuario

Implementado:

- Listar arvore de arquivos.
- Ler arquivo.
- Criar/editar arquivo.
- Criar pasta.
- Apagar arquivo/pasta.
- Mover/renomear arquivo/pasta.
- Bloqueio de path traversal.
- Bloqueio de caminho absoluto.
- Resolucao por `safe_user_path`.
- Isolamento fisico por usuario.
- Leitura/escrita inicial voltada para texto.
- Limite de arquivo editavel.
- Arvore visual recursiva com pastas aninhadas.
- Drag-and-drop de itens internos com confirmacao antes de mover.
- Importacao de arquivos de texto externos com confirmacao.
- Exclusao recursiva de pasta nao vazia somente apos confirmacao.
- Selecao explicita de arquivo do Workspace para o RAG.

Rotas:

```txt
GET    /api/v1/workspace/tree?path=
GET    /api/v1/workspace/file?path=
PUT    /api/v1/workspace/file
POST   /api/v1/workspace/mkdir
DELETE /api/v1/workspace/path?path=
POST   /api/v1/workspace/move
POST   /api/v1/workspace/rag/ingest
```

### Gerenciamento do Workspace pela IA

Pedidos naturais como `crie uma pasta e um README.md sobre mim` sao interceptados pelo `workspace_manager`. A IA gera um plano estruturado, mas nao recebe escrita direta e silenciosa.

Fluxo:

1. Usuario descreve a operacao no chat.
2. IA devolve um plano com criacao, edicao, movimentacao ou exclusao.
3. Frontend mostra cada acao e o diff dos arquivos.
4. Usuario escolhe `Confirmar e executar` ou cancela.
5. Backend valida novamente caminhos e checksums, executa e registra auditoria.
6. Arquivos criados/editados continuam fora do RAG.
7. O cartao pode sugerir RAG, mas apenas os arquivos marcados pelo usuario sao ingeridos.

Rotas:

```txt
POST   /api/v1/workspace/ai/plan
GET    /api/v1/workspace/ai/plans/{plan_id}
POST   /api/v1/workspace/ai/plans/{plan_id}/apply
DELETE /api/v1/workspace/ai/plans/{plan_id}
```

### Patch Aprovado no Workspace

Implementado:

- Preview de alteracao antes de aplicar.
- Diff para o usuario revisar.
- Checksum esperado.
- Bloqueio se o arquivo mudou entre preview e apply.
- Snapshot antes de aplicar.
- Log de auditoria em JSONL.

Rotas:

```txt
POST /api/v1/workspace/patch/preview
POST /api/v1/workspace/patch/apply
```

Fluxo:

1. Frontend pede preview.
2. Backend retorna diff e checksum.
3. Usuario aprova.
4. Frontend envia apply com `expected_checksum`.
5. Backend valida checksum.
6. Backend cria snapshot.
7. Backend aplica alteracao.
8. Backend registra auditoria.

### Preferencias

Implementado:

- Preferencias por usuario.
- Criar/atualizar preferencia por chave.
- Preferencias confirmadas entram no contexto do chat.

Rotas:

```txt
GET /api/v1/preferences
PUT /api/v1/preferences/{key}
```

Exemplos de preferencias:

- Tom de resposta.
- Idioma.
- Nivel de detalhe.
- Estilo de codigo.
- Stack preferida.
- Regras pessoais do usuario.

### Sugestoes de Preferencia

Implementado:

- O backend pode sugerir ajustes de preferencia a partir do uso.
- Sugestoes ficam pendentes.
- Usuario aceita ou rejeita.
- Aceitar aplica em `user_preferences`.
- Rejeitar nao altera configuracao.
- Falhas no processo de sugestao nao bloqueiam o chat.

Rotas:

```txt
GET  /api/v1/preference-suggestions
POST /api/v1/preference-suggestions/{suggestion_id}/resolve
```

### Providers Globais e Pessoais

Implementado:

- Providers globais continuam existindo.
- Providers pessoais sao por usuario.
- Usuario pode criar provider pessoal.
- Usuario pode ativar provider pessoal.
- Chat usa provider pessoal ativo quando existe.
- API key pessoal nao volta crua para o frontend.
- Respostas mostram `has_key` e mascara.
- Teste de provider usa configuracao efetiva do usuario.
- Mutacoes globais de provider exigem admin.

Rotas pessoais:

```txt
GET  /api/v1/providers/user
POST /api/v1/providers/user
POST /api/v1/providers/user/{config_id}/activate
GET  /api/v1/providers/active-config
POST /api/v1/providers/test
```

Rotas globais/admin:

```txt
GET    /api/v1/providers/manage
GET    /api/v1/providers/manage/{provider_id}
POST   /api/v1/providers/manage
PUT    /api/v1/providers/manage/{provider_id}
PUT    /api/v1/providers/manage/{provider_id}/api-key
DELETE /api/v1/providers/manage/{provider_id}
POST   /api/v1/providers/manage/{provider_id}/activate
GET    /api/v1/providers/manage/{provider_id}/models
POST   /api/v1/providers/manage/{provider_id}/models
PUT    /api/v1/providers/manage/{provider_id}/models/{model_id}
DELETE /api/v1/providers/manage/{provider_id}/models/{model_id}
```

Outras rotas:

```txt
POST /api/v1/providers/activate-model
GET  /api/v1/providers/status
GET  /api/v1/health
GET  /api/v1/config
GET  /api/v1/profiles
```

### Skills

Skills padrao:

- `perplexo_search`
- `simple_search`
- `search_and_answer`
- `personal_rag`
- `workspace_read`
- `workspace_write_preview`

Implementado:

- Listagem de skills.
- Ativar/desativar skill por usuario.
- Log de execucao.
- Skill so executa se estiver habilitada.
- Skills com `requires_shell=True` ficam bloqueadas.
- Busca web so roda quando skill de busca esta habilitada e a mensagem indica intencao de pesquisa.
- `perplexo_search` usa `POST /search` com `X-API-Key`, separa o historico externo por `user_id` e inclui fontes na resposta.
- Pedidos de pesquisa profunda ou academica ajustam automaticamente modelo, foco e periodo.
- Se o Perplexo estiver indisponivel, a skill pode usar a pesquisa simples como fallback sem travar o chat.
- O painel permite configurar modelo, foco, periodo, fallback e testar a conexao sem mostrar a chave.
- `personal_rag` registra execucao quando forca uso do RAG pessoal.
- `workspace_read` so le arquivo com comando explicito `@workspace:read caminho/do/arquivo.md`.
- `workspace_write_preview` so gera diff com `@workspace:preview caminho/do/arquivo.md`, uma linha `---` e o novo conteudo; nunca aplica a alteracao.

Rotas:

```txt
GET /api/v1/skills
PUT /api/v1/skills/{skill_name}
GET /api/v1/skills/runs
GET /api/v1/skills/perplexo/status
POST /api/v1/skills/perplexo/test
```

### Pool Codex/ChatGPT

O backend tambem inclui rotas autenticadas para pool OAuth/Codex.

Implementado:

- Listar contas.
- Ver estatisticas.
- Adicionar/remover conta.
- Refresh de conta.
- Refresh geral.
- Atualizacao de quota.
- Escolha de melhor conta.
- Device Code OAuth.
- Extracao de auth JSON.
- Sanitizacao de respostas para nao expor tokens crus.

Rotas:

```txt
GET    /api/v1/codex/pool/{provider_id}
GET    /api/v1/codex/pool/{provider_id}/stats
POST   /api/v1/codex/pool/{provider_id}/accounts
DELETE /api/v1/codex/pool/{provider_id}/accounts/{account_id}
POST   /api/v1/codex/pool/{provider_id}/accounts/{account_id}/refresh
POST   /api/v1/codex/pool/{provider_id}/refresh-all
POST   /api/v1/codex/pool/{provider_id}/update-quota
GET    /api/v1/codex/pool/{provider_id}/best
POST   /api/v1/codex/device-code/request
POST   /api/v1/codex/device-code/poll/{request_id}
GET    /api/v1/codex/device-code/status/{request_id}
POST   /api/v1/codex/extract-auth
```

### Health, Metricas e Stats

Rotas:

```txt
GET /api/v1/health
GET /api/v1/metrics
GET /api/v1/stats
GET /
GET /docs
```

Comportamento importante:

- `/api/v1/health` publico mostra provider global.
- `/api/v1/health` com token pode mostrar provider efetivo do usuario.
- `/docs` aponta para Swagger/OpenAPI.

## Frontend

O frontend fica em `frontend/` e roda em `http://localhost:3000`.

Principais telas/componentes:

- `AuthPanel`: login e cadastro.
- `OnboardingModal`: criacao do perfil inicial.
- `ChatInput` e `ChatMessage`: conversa.
- `Sidebar`: historico/sessoes.
- `ModelSelector`: escolha/modelo/provider.
- `ProviderManager`: providers globais e pessoais.
- `SettingsPanel`: preferencias e sugestoes.
- `DocumentsPanel`: upload, listagem e remocao de documentos RAG.
- `WorkspacePanel`: arquivos/pastas e patch aprovado.
- `DiffViewer`: visualizacao de diff antes de aplicar patch.
- `SkillsPanel`: skills habilitadas e logs.

### Proxy do Frontend

O Vite usa proxy para falar com o backend. O backend precisa estar rodando antes do frontend tentar abrir WebSocket.

Se aparecer erro parecido com:

```txt
vite ws proxy error ECONNREFUSED
```

significa que o frontend tentou conectar no backend e a API nao estava acessivel em `127.0.0.1:8000` naquele momento.

## Como Rodar Localmente

### Backend

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

Backend:

```txt
http://127.0.0.1:8000
```

Swagger:

```txt
http://127.0.0.1:8000/docs
```

### Frontend

Em outro terminal:

```powershell
cd frontend
npm install
npm run dev
```

Frontend:

```txt
http://localhost:3000
```

### Comando Correto da API

Para rodar a API usada pelo frontend:

```powershell
python -m src.main serve
```

Este comando sozinho:

```powershell
python -m src.main
```

nao e o servidor completo do frontend. Sem argumento, ele entra no fluxo CLI/interativo definido pelo projeto.

## Variaveis de Ambiente

O projeto le `.env` via `pydantic-settings`.

Principais variaveis:

```env
DATABASE_URL=sqlite:///./data/chatbot.db
AUTH_SECRET_KEY=troque-este-segredo
USER_DATA_DIR=./data/users
API_HOST=0.0.0.0
API_PORT=8000

LLM_PROVIDER=custom_openai
CUSTOM_PROFILE=opencode-zen-free
CUSTOM_API_KEY=
CUSTOM_BASE_URL=
CUSTOM_MODEL=

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2
OPENCODE_ZEN_API_KEY=
OPENCODE_GO_API_KEY=

PERPLEXO_BASE_URL=https://api.ghost1.cloud
MCP_API_KEY=
PERPLEXO_TIMEOUT_SECONDS=25

EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=all-MiniLM-L6-v2
VECTOR_DB_TYPE=chroma
CHROMA_PERSIST_DIR=./data/chroma

ENABLE_RAG=true
ENABLE_MODERATION=true
ENABLE_MULTILANG=true
ENABLE_CACHE=true
MAX_UPLOAD_SIZE_MB=10
```

## Comandos Uteis

```powershell
# Rodar backend API
python -m src.main serve

# Rodar CLI/chat simples
python -m src.main chat

# Validacao rapida da Skill Perplexo
python -m unittest tests.test_perplexo_search tests.test_skill_runtime

# Rodar frontend
cd frontend
npm run dev

# Build frontend
cd frontend
npm run build

# Compilar Python
python -m compileall -q src

# Checar diferencas antes de commit
git status --short
git diff -- README.md
```

## Testes Seguros e Curtos

Bateria curta usada no projeto, evitando teste conhecido como problematico/lento:

```powershell
python -m unittest tests.test_route_security tests.test_skill_runtime tests.test_auth_required tests.test_skills_context tests.test_userspace tests.test_workspace_service tests.test_workspace_routes tests.test_ingestion tests.test_rag_isolation tests.test_preferences tests.test_preference_suggestions tests.test_user_providers tests.test_user_provider_llm tests.test_skill_permissions tests.test_skill_runs tests.test_patcher tests.test_requirements tests.test_frontend_documents_panel tests.test_frontend_preference_suggestions tests.test_frontend_user_providers tests.test_frontend_workspace_patch_api tests.test_frontend_workspace_patch_ui
```

Checks adicionais:

```powershell
python -m compileall -q src
git diff --check

cd frontend
npm run build
```

Regra operacional atual:

```txt
Nao rodar python -m unittest tests.test_auth_multiuser ate ele ser estabilizado.
```

Esse teste foi tratado como problematico/lento no fluxo do projeto.

## Seguranca Implementada

Implementado:

- Rotas sensiveis exigem token.
- WebSocket exige token.
- Conversas filtradas por usuario.
- Mensagens filtradas por usuario.
- Documentos filtrados por usuario.
- Preferencias filtradas por usuario.
- Sugestoes filtradas por usuario.
- Providers pessoais filtrados por usuario.
- Skills filtradas por usuario.
- Logs de skills filtrados por usuario.
- Workspace passa por `safe_user_path`.
- Bloqueio de `..` no workspace/UserSpace.
- Bloqueio de caminhos absolutos.
- Upload original fica dentro do UserSpace do usuario.
- Collection RAG deriva do usuario autenticado.
- API keys pessoais nao voltam cruas para o frontend.
- Tokens do pool Codex sao sanitizados nas respostas publicas.
- Skills com shell ficam bloqueadas.
- Patch de workspace exige checksum.
- Patch de workspace cria snapshot antes de aplicar.
- Mutacoes globais de provider exigem admin.

## Dados Que Nao Devem Ir Para o GitHub

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
- arquivos locais de banco
- chaves/API keys
- tokens OAuth
- uploads reais de usuario

Esses arquivos sao dados locais, dependencias, build output ou informacao sensivel.

## Docker e Makefile

O repositorio contem:

- `Dockerfile`
- `docker-compose.yml`
- `Makefile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`

Eles servem como base para empacotamento/deploy, mas o fluxo de desenvolvimento local mais direto e:

```powershell
python -m src.main serve
cd frontend
npm run dev
```

## Banco de Dados

Modelos principais:

- `users`
- `user_profiles`
- `user_preferences`
- `preference_suggestions`
- `user_provider_configs`
- `conversations`
- `messages`
- `knowledge_documents`
- `skills`
- `user_skills`
- `skill_runs`

O projeto usa migracoes SQLite leves dentro do proprio fluxo de inicializacao/repository, em vez de Alembic formal.

## Documentacao Complementar

Arquivos uteis no repositorio:

- `docs/PROJECT_SUMMARY.md`
- `docs/USERSPACE_RAG_SKILLS_FULL_PLAN.md`
- `docs/MULTIUSER_PERSONALIZED_CHATBOT_PLAN.md`
- `docs/chat-operacional-implementation-plan.md`
- `DOCS_STATUS.md`
- `plano-chatbot.md`

O README e o manual principal. Os arquivos em `docs/` guardam historico, planos e detalhes de evolucao.

## Limites Conhecidos

Ainda nao tratar como producao final sem revisar:

- CORS esta amplo para desenvolvimento local.
- Criptografia/codificacao local de API key pessoal deve ser trocada por KMS/Fernet/secret manager em producao.
- `python -m src.main ingest --file arquivo.pdf` ainda nao e o caminho principal funcional; use upload pela API/UI.
- Smoke manual completo precisa de dois terminais: backend em `serve` e frontend em `npm run dev`.
- Bundle principal do frontend pode emitir aviso de chunk grande do Vite.
- O teste `tests.test_auth_multiuser` precisa ser estabilizado ou substituido.

## Checklist de Uso

Para testar o fluxo principal:

1. Rodar backend com `python -m src.main serve`.
2. Rodar frontend com `cd frontend` e `npm run dev`.
3. Abrir `http://localhost:3000`.
4. Criar conta.
5. Fazer onboarding inicial.
6. Enviar mensagem no chat.
7. Subir documento em Documents.
8. Clicar "Ingerir no RAG" no documento enviado.
9. Perguntar algo sobre o documento.
10. Criar arquivo no Workspace.
11. Testar patch preview/apply.
12. Criar provider pessoal.
13. Ativar provider pessoal.
14. Criar preferencia.
15. Aceitar/rejeitar sugestao.
16. Ativar/desativar skill.
17. Conferir logs de skills.
18. Com `workspace_read` ativa, enviar `@workspace:read caminho/do/arquivo.md`.
19. Com `workspace_write_preview` ativa, enviar `@workspace:preview caminho/do/arquivo.md`, depois `---` e o conteudo proposto.

## Resumo Final

O estado detalhado de implementacao, separacao de dados, APIs, Skills e validacao esta em `docs/IMPLEMENTATION_STATUS.md`.

Este projeto agora cobre o nucleo pedido:

- Login.
- Cadastro.
- Multiusuario.
- RAG por usuario.
- Onboarding inicial.
- Skills.
- Providers pessoais.
- Preferencias inteligentes.
- Workspace isolado.
- Uploads separados do RAG.
- UI funcional para operar tudo isso.

O proximo passo tecnico antes de chamar de producao e fazer smoke manual completo, revisar CORS/secrets e estabilizar a bateria total de testes.
