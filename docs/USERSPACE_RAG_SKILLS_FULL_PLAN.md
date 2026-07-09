# Plano sofisticado: UserSpace, RAG pessoal, workspace e skills

> Objetivo: evoluir o chatbot atual para um sistema multiusuario completo, com login/cadastro, onboarding inicial, RAG isolado por usuario, workspace de arquivos por usuario, providers/preferencias por conta, skills executaveis com permissao e fluxo sem travamentos.

## Resumo direto

O projeto ja tem uma fundacao importante:

- Login, cadastro e token HMAC em `src/core/auth.py`.
- Modelos `User`, `UserProfile`, `Skill` e `UserSkill` em `src/db/models.py`.
- `user_id` em conversas, mensagens e documentos.
- Onboarding que cria memoria inicial no RAG.
- Skills basicas por usuario.
- Frontend com `AuthPanel`, `OnboardingModal` e `SkillsPanel`.

O que ainda falta para ficar realmente redondo:

- Executar smoke manual com backend e frontend antes de exposicao publica.
- Revisar a disponibilidade do mecanismo externo de busca antes de producao.
- Fazer hardening operacional de CORS, secrets, backup e observabilidade antes de exposicao publica.

## Estado implementado

- [x] Login, cadastro, sessao e isolamento de conversas, mensagens e documentos por `user_id`.
- [x] UserSpace por usuario com `profile`, `workspace`, `uploads`, `rag` e `skills`.
- [x] Onboarding salvo no banco, em `profile/onboarding.md` e no RAG pessoal, mantendo somente a versao atual do perfil indexada.
- [x] Workspace autenticado, com bloqueio de path traversal, preview com checksum e snapshot antes de aplicar patch.
- [x] Upload original separado do indice RAG, com salvar primeiro, texto derivado em `rag/extracted`, ingerir depois, parser para TXT/MD/CSV/JSON/PDF/DOCX e manifesto de ingestao.
- [x] RAG com collection e metadata por usuario.
- [x] Providers e preferencias pessoais, com chave mascarada na API/UI.
- [x] SkillRegistry, permissao por capacidade, auditoria no banco/JSONL e runtime por usuario.
- [x] Skills de busca, RAG pessoal, leitura explicita de workspace e preview de escrita sem aplicacao automatica.
- [x] Bateria curta de UserSpace, Workspace, ingestao, RAG, Skills, auth e painel de documentos: 47 testes passaram em 4.371 segundos com corte de 45 segundos.
- [ ] Smoke manual completo e build do frontend antes de exposicao publica.

## Regra de ouro anti-travamento

Nada de implementar tudo num bloco gigante.

Cada entrega deve:

1. Alterar poucos arquivos.
2. Ter teste unitario curto.
3. Rodar em menos de 30 segundos.
4. Nao iniciar servidor infinito durante validacao automatica.
5. Nao rodar `python -m unittest tests.test_auth_multiuser` enquanto ele estiver instavel/lento.
6. Preferir testes focados por arquivo/funcoes novas.
7. Fazer commit pequeno apos cada fase passar.

Comandos seguros de validacao por fase:

```powershell
python -m compileall -q src
python -m unittest tests.test_route_security tests.test_skill_runtime tests.test_auth_required tests.test_skills_context
git diff --check
```

Quando uma fase criar teste novo, rodar somente o teste novo primeiro:

```powershell
python -m unittest tests.test_workspace_service
```

So depois rodar a bateria curta.

## Arquitetura alvo

```txt
Frontend React
  AuthPanel
  OnboardingModal
  Chat
  DocumentsPanel
  WorkspacePanel
  SkillsPanel
  PreferencesPanel
        |
        v
FastAPI
  auth_routes
  chat_routes
  document_routes
  workspace_routes
  skill_routes
  preference_routes
        |
        v
Core services
  AuthService
  UserSpaceService
  FileWorkspaceService
  IngestionService
  PersonalRagService
  PreferenceSuggestionService
  SkillRegistry
  SkillRuntime
        |
        v
Storage
  SQLite/Postgres
  data/users/{user_id}/workspace
  data/users/{user_id}/uploads/original
  data/users/{user_id}/rag
  Chroma collection user_{user_id}_documents
```

## Separacao essencial

RAG nao e workspace.

```txt
Workspace
  Arquivos reais que o usuario pode listar, abrir, editar, mover e deletar.

Uploads
  Arquivos originais enviados pelo usuario.

RAG
  Indice textual/vetorial derivado dos arquivos, usado para busca semantica.
```

Estrutura fisica proposta:

```txt
data/
  users/
    {user_id}/
      profile/
        onboarding.md
        preferences.json
      workspace/
        README.md
        projetos/
      uploads/
        original/
          {file_id}/
            original.pdf
      rag/
        documents/
        extracted/
        manifests/
      skills/
        user/
```

## Principios de seguranca

- Toda rota sensivel exige usuario autenticado.
- Toda query de banco que le dados do usuario filtra por `user_id`.
- Todo caminho de arquivo passa por `safe_join`.
- Bloquear caminho absoluto.
- Bloquear `..`.
- Resolver path final e garantir que ele continua dentro da raiz do usuario.
- Nunca confiar em `UploadFile.filename` como caminho real.
- Gerar nome interno por id/checksum.
- Limitar tamanho por arquivo e por usuario.
- Nunca devolver token/API key sem mascara.
- Skills nao executam shell livre.
- Skills com rede precisam estar habilitadas pelo usuario.
- Mudanca automatica em preferencia/memoria exige confirmacao.

## Plano em fases

### Fase 0: estabilizacao e mapa de contrato

Objetivo: garantir que o que ja existe esta mapeado e que as proximas fases nao quebram auth/chat.

Arquivos provaveis:

- `docs/USERSPACE_RAG_SKILLS_FULL_PLAN.md`
- `docs/PROJECT_SUMMARY.md`
- `tests/test_auth_required.py`
- `tests/test_skill_runtime.py`

Entregas:

- Documentar estado atual.
- Listar rotas protegidas.
- Definir bateria curta oficial.
- Nao mexer ainda em fluxo de chat.

Pronto quando:

- Plano salvo.
- `python -m compileall -q src` passa.
- Bateria curta passa.

### Fase 1: UserSpaceService

Objetivo: criar a raiz segura de cada usuario.

Criar:

- `src/core/userspace.py`
- `tests/test_userspace.py`

Responsabilidades:

```python
get_user_root(user_id: int) -> Path
ensure_user_space(user_id: int) -> UserSpacePaths
safe_user_path(user_id: int, area: str, relative_path: str) -> Path
```

Areas permitidas:

- `profile`
- `workspace`
- `uploads`
- `rag`
- `skills`

Testes obrigatorios:

- Cria todas as pastas de usuario.
- Bloqueia `../secret`.
- Bloqueia caminho absoluto.
- Bloqueia area desconhecida.
- Aceita caminho normal como `projetos/app.md`.

Validacao:

```powershell
python -m unittest tests.test_userspace
python -m compileall -q src
```

Risco:

- Baixo. Nao toca chat.

### Fase 2: criar UserSpace no cadastro e onboarding

Objetivo: toda conta nova ja nasce com pastas e memoria inicial fisica.

Modificar:

- `src/db/repository.py`
- `src/api/routes.py`
- `tests/test_auth_required.py` ou novo `tests/test_user_creation.py`

Mudancas:

- `UserRepo.create_user` chama `ensure_user_space(user.id)` apos criar usuario.
- `UserRepo.ensure_default_user` tambem garante UserSpace do `local-admin`.
- `/onboarding` salva `data/users/{id}/profile/onboarding.md`.
- O conteudo salvo no disco e o conteudo ingerido no RAG devem ser iguais.

Pronto quando:

- Criar usuario gera pastas.
- Onboarding cria arquivo `profile/onboarding.md`.
- Onboarding continua indexando no RAG pessoal.

Validacao:

```powershell
python -m unittest tests.test_user_creation
python -m unittest tests.test_auth_required
```

Risco:

- Baixo/medio. Toca cadastro/onboarding, mas nao mexe provider.

### Fase 3: FileWorkspaceService

Objetivo: criar workspace real por usuario, ainda sem UI complexa.

Criar:

- `src/core/workspace.py`
- `tests/test_workspace_service.py`

Funcoes:

```python
list_tree(user_id: int, path: str = "") -> list[WorkspaceNode]
read_text_file(user_id: int, path: str) -> str
write_text_file(user_id: int, path: str, content: str) -> WorkspaceFileInfo
mkdir(user_id: int, path: str) -> WorkspaceFileInfo
delete_path(user_id: int, path: str) -> bool
move_path(user_id: int, source: str, target: str) -> WorkspaceFileInfo
```

Limites iniciais:

- Texto somente para leitura/escrita.
- Tamanho maximo por arquivo editavel: 1 MB.
- Delete de pasta so se vazia na primeira entrega.
- Sem patch automatico ainda.

Testes obrigatorios:

- Usuario A nao acessa arquivo do usuario B.
- `list_tree` nao mostra arquivos fora da raiz.
- `write_text_file` cria pais quando permitido ou falha de forma clara.
- `read_text_file` bloqueia binario grande.
- `move_path` nao sobrescreve sem regra explicita.

Validacao:

```powershell
python -m unittest tests.test_workspace_service
```

Risco:

- Medio. Mexe com disco, entao `safe_user_path` e obrigatorio.

### Fase 4: rotas REST do workspace

Objetivo: expor workspace para frontend e futuras skills.

Criar:

- `src/api/workspace_routes.py`

Modificar:

- `src/api/app.py` para incluir router.
- `src/api/schemas.py` para schemas do workspace.

Endpoints:

```txt
GET    /api/v1/workspace/tree?path=
GET    /api/v1/workspace/file?path=
PUT    /api/v1/workspace/file
POST   /api/v1/workspace/mkdir
DELETE /api/v1/workspace/path?path=
POST   /api/v1/workspace/move
```

Todos exigem:

```python
user=Depends(get_current_user)
```

Testes:

- Sem token retorna 401.
- Token do usuario A nao acessa arquivo do usuario B.
- Path traversal retorna 400.
- Criar, ler, mover e deletar arquivo simples.

Validacao:

```powershell
python -m unittest tests.test_workspace_routes
python -m unittest tests.test_auth_required
```

Risco:

- Medio. Evitar misturar no `routes.py` gigante; criar router separado.

### Fase 5: upload original separado de ingestao RAG

Objetivo: parar de tratar upload como "texto que some no RAG". O arquivo original deve ser salvo.

Criar:

- `src/core/ingestion.py`
- `tests/test_ingestion.py`

Modificar:

- `src/api/routes.py` ou criar `src/api/document_routes.py`
- `src/db/models.py`
- `src/db/repository.py`

Modelo ideal novo ou expandido:

```txt
workspace_files
- id
- user_id
- area
- relative_path
- original_filename
- mime_type
- size
- checksum
- kind
- created_at
- updated_at

knowledge_documents
- user_id
- file_id nullable
- filename
- source
- status
- chunk_count
- file_size
- parser
- error_message nullable
```

Fluxo novo:

```txt
POST /documents/upload
  salva original em uploads/original/{file_id}/filename
  cria metadado
  marca documento como uploaded, sem criar chunks

POST /documents/{id}/ingest
  reprocessa arquivo salvo

POST /upload
  caminho imediato legado para anexos do chat: salva e ingere na mesma requisicao
```

Parsers:

- `.txt`, `.md`, `.json`, `.csv`: decode UTF-8 com fallback controlado.
- `.pdf`: usar parser real quando dependencia existir.
- `.docx`: usar parser real quando dependencia existir.

Na primeira entrega, se PDF/DOCX nao tiver dependencia, retornar erro claro:

```txt
Parser para .pdf ainda nao disponivel nesta instalacao
```

Pronto quando:

- Upload salva original.
- Documento aparece por usuario.
- RAG usa collection `user_{id}_documents`.
- PDF/DOCX nao entram como lixo binario.

Validacao:

```powershell
python -m unittest tests.test_ingestion
python -m unittest tests.test_rag
```

Risco:

- Alto se tentar fazer parser completo de uma vez.
- Mitigacao: primeiro separar storage/ingestao; parser avancado depois.

### Fase 6: RAG pessoal forte

Objetivo: garantir que RAG nunca mistura usuarios.

Modificar:

- `src/rag/vector_store.py`
- `src/rag/retriever.py`
- `src/api/routes.py`
- `src/core/chat.py`
- `tests/test_rag_isolation.py`

Regras:

- Toda ingestao usa `rag_collection_for_user(user.id)`.
- Toda busca usa `rag_collection_for_user(user.id)`.
- Metadata inclui `user_id`.
- Chat so consulta RAG pessoal quando `use_rag` ou skill `personal_rag` estiver ativa.

Testes:

- Usuario A ingere "segredo A".
- Usuario B ingere "segredo B".
- Busca do A nao retorna B.
- Busca do B nao retorna A.

Validacao:

```powershell
python -m unittest tests.test_rag_isolation
python -m unittest tests.test_rag
```

Risco:

- Medio. O risco real e collection global antiga. Manter fallback migratorio controlado.

### Fase 7: preferencias por usuario

Objetivo: perfil deixar de ser apenas onboarding e virar fonte de personalizacao do chat.

Criar:

- `src/core/preferences.py`
- `tests/test_preferences.py`

Modificar:

- `src/db/models.py`
- `src/db/repository.py`
- `src/api/routes.py` ou `src/api/preference_routes.py`
- `frontend/src/components/SettingsPanel.tsx`

Tabela:

```txt
user_preferences
- id
- user_id
- key
- value_json
- source
- confidence
- created_at
- updated_at
```

Preferencias iniciais:

- `answer_style`
- `default_language`
- `technical_level`
- `code_style`
- `rag_aggressiveness`
- `default_provider`
- `default_model`

Chat deve montar contexto:

```txt
Perfil do usuario
Preferencias confirmadas
Skills habilitadas
RAG pessoal relevante
```

Pronto quando:

- Usuario consegue ler/alterar preferencias.
- Chat usa preferencias no prompt sistemico.
- Preferencias de um usuario nao aparecem para outro.

Validacao:

```powershell
python -m unittest tests.test_preferences
python -m unittest tests.test_skills_context
```

Risco:

- Medio. Nao deixar prompt crescer sem limite.

### Fase 8: sugestoes por LLM com confirmacao

Objetivo: chatbot aprende preferencias, mas nao altera sozinho.

Criar:

- `src/core/preference_suggestions.py`
- `tests/test_preference_suggestions.py`

Tabela:

```txt
preference_suggestions
- id
- user_id
- suggestion_type
- current_value_json
- suggested_value_json
- reason
- confidence
- status
- created_at
- resolved_at
```

Fluxo:

```txt
Chat observa padrao
  |
  v
Cria sugestao pending
  |
  v
Frontend mostra pergunta curta
  |
  v
Usuario aceita/rejeita
  |
  v
Se aceitou, atualiza user_preferences
```

Regras:

- Nao sugerir a cada mensagem.
- Cooldown por tipo de sugestao.
- Nunca salvar segredo como memoria.
- Nunca alterar provider/chave/senha automaticamente.

Validacao:

```powershell
python -m unittest tests.test_preference_suggestions
```

Risco:

- Medio. Controlar frequencia para nao virar spam.

### Fase 9: providers por usuario

Objetivo: tirar dependencia de provider global quando o sistema for multiusuario real.

Criar:

- `src/core/user_provider_manager.py`
- `tests/test_user_providers.py`

Modificar:

- `src/core/provider_manager.py` somente onde necessario.
- `src/api/routes.py` ou `src/api/provider_routes.py`.
- `frontend/src/components/ProviderManager.tsx`.

Tabela:

```txt
user_provider_configs
- id
- user_id
- provider_id
- display_name
- base_url
- model
- api_key_encrypted
- is_enabled
- is_default
- created_at
- updated_at
```

Regras:

- Provider global continua existindo como fallback/admin.
- Usuario pode configurar provider proprio.
- API key salva criptografada ou, no minimo local-dev, nunca retornada crua.
- UI mostra apenas `has_key` e `key_masked`.
- `/providers/test` testa exatamente provider/model selecionado pelo usuario.

Validacao:

```powershell
python -m unittest tests.test_user_providers
python -m unittest tests.test_route_security
```

Risco:

- Alto. Providers mexem no caminho quente do chat.
- Mitigacao: manter fallback global ate user provider estar testado.

### Fase 10: SkillRegistry e SkillRuntime v2

Objetivo: transformar skills de contexto em capacidades governadas.

Criar:

- `src/core/skill_registry.py`
- `src/core/skill_permissions.py`
- `src/core/skill_logs.py`
- `tests/test_skill_registry.py`
- `tests/test_skill_permissions.py`

Evoluir:

- `src/core/skill_runtime.py`

Tipos:

```txt
knowledge
internal_tool
external_search
workflow
workspace_read
workspace_write_preview
shell_guarded_future
```

Skill definition:

```json
{
  "name": "search_and_answer",
  "description": "Pesquisa e responde com fontes.",
  "inputs": {
    "query": "string"
  },
  "permissions": {
    "network": true,
    "workspace_read": false,
    "workspace_write": false,
    "shell": false
  },
  "risk_level": 2
}
```

Logs:

```txt
skill_runs
- id
- user_id
- skill_name
- status
- input_json
- output_summary
- error_message
- started_at
- finished_at
```

Regras:

- Skill so roda se habilitada para usuario.
- Skill de risco 2+ precisa aparecer na UI com descricao.
- Skill de escrita em workspace nunca aplica direto; gera preview.
- Shell fica fora do escopo ate sandbox existir.

Validacao:

```powershell
python -m unittest tests.test_skill_runtime tests.test_skill_registry tests.test_skill_permissions
```

Risco:

- Medio/alto. Evitar shell nesta fase.

### Fase 11: UI de Workspace, Documents e Skills

Objetivo: o usuario conseguir usar as novas capacidades sem gambiarra.

Criar:

- `frontend/src/components/WorkspacePanel.tsx`
- `frontend/src/components/FileTree.tsx`
- `frontend/src/components/FileEditor.tsx`
- `frontend/src/components/DocumentsPanel.tsx`
- `frontend/src/components/PreferenceSuggestions.tsx`

Modificar:

- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/components/SkillsPanel.tsx`
- `frontend/src/components/SettingsPanel.tsx`

Fluxos UI:

- Abrir painel de arquivos.
- Criar pasta.
- Criar arquivo `.md`.
- Editar e salvar.
- Fazer upload para uploads.
- Clicar "ingerir no RAG".
- Ver documentos ingeridos.
- Ativar/desativar skill.
- Aceitar/rejeitar sugestao de preferencia.

Validacao:

```powershell
cd frontend
npm run build
```

Risco:

- Medio. UI pode quebrar build TypeScript.

### Fase 12: diff/patch aprovado pelo usuario

Objetivo: permitir que o chat proponha edicoes em arquivo sem aplicar sozinho.

Criar:

- `src/core/patcher.py`
- `tests/test_patcher.py`
- `frontend/src/components/DiffViewer.tsx`

Endpoints:

```txt
POST /api/v1/workspace/patch/preview
POST /api/v1/workspace/patch/apply
```

Fluxo:

```txt
LLM sugere alteracao
Backend cria diff
Frontend mostra preview
Usuario aprova
Backend aplica
Audit log registra
```

Regras:

- Patch somente dentro do workspace do usuario.
- Aplicar patch exige versao/checksum esperado.
- Se arquivo mudou depois do preview, bloquear e pedir novo preview.
- Snapshot antes de aplicar.

Validacao:

```powershell
python -m unittest tests.test_patcher tests.test_workspace_service
```

Risco:

- Alto. So fazer depois de workspace estar solido.

## Ordem recomendada real

Se a meta e avancar sem quebrar o app:

1. `UserSpaceService`
2. Criacao automatica de pastas no cadastro/onboarding
3. `FileWorkspaceService`
4. Rotas REST do workspace
5. Upload original separado de ingestao
6. RAG pessoal forte
7. Preferencias por usuario
8. Sugestoes por LLM com confirmacao
9. Providers por usuario
10. SkillRuntime v2
11. UI completa
12. Diff/patch aprovado

## Entregas pequenas e commits sugeridos

```txt
feat: add per-user userspace service
feat: initialize userspace during registration
feat: add safe workspace file service
feat: expose authenticated workspace routes
feat: separate upload storage from rag ingestion
feat: enforce personal rag isolation
feat: add user preferences
feat: add preference suggestions workflow
feat: add user provider configs
feat: harden skill registry and permissions
feat: add workspace and documents UI
feat: add approved workspace patch flow
```

## Checklist final de pronto

- Login funciona.
- Cadastro cria usuario e UserSpace.
- Onboarding salva perfil no banco, arquivo fisico e RAG pessoal.
- Conversas sao filtradas por usuario.
- Mensagens sao filtradas por usuario.
- Documentos sao filtrados por usuario.
- RAG usa collection por usuario.
- Workspace nao permite path traversal.
- Usuario nao acessa arquivo de outro usuario.
- Upload salva original.
- PDF/DOCX nao viram lixo binario.
- Preferencias sao por usuario.
- Sugestoes de LLM exigem aceitar/rejeitar.
- Providers nao vazam API key.
- Skills so rodam se habilitadas.
- Skills registram execucao.
- Skills perigosas nao executam shell.
- UI permite usar workspace/documentos/skills sem endpoint manual.
- Testes curtos passam.
- `python -m src.main serve` nao observa `.venv`.

## Bateria final antes de push grande

Nao usar teste conhecido por travar ate ele ser corrigido.

```powershell
python -m compileall -q src
python -m unittest tests.test_route_security tests.test_skill_runtime tests.test_auth_required tests.test_skills_context
python -m unittest tests.test_userspace tests.test_workspace_service tests.test_workspace_routes
python -m unittest tests.test_ingestion tests.test_rag_isolation
git diff --check
```

Frontend:

```powershell
cd frontend
npm run build
```

Smoke manual:

```powershell
python -m src.main serve
```

Em outro terminal:

```powershell
cd frontend
npm run dev
```

Abrir:

```txt
http://localhost:3000
```

## Primeira tarefa que eu faria agora

A primeira implementacao real deve ser a Fase 1: `UserSpaceService`.

Ela e pequena, segura e desbloqueia todo o resto:

- workspace;
- uploads originais;
- RAG fisico por usuario;
- skills por usuario;
- preferencias em arquivo;
- logs/auditoria.

Se isso estiver bem feito, as fases seguintes encaixam sem virar uma bola de fios.
