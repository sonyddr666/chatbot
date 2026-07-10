# Estado de implementacao

## Resultado

A arquitetura UserSpace, RAG pessoal, Workspace e Skills esta implementada para cada usuario autenticado. A fonte de identidade em todos os fluxos e o `user_id` obtido do token, nunca um identificador enviado pelo frontend.

## UserSpace

Cada conta recebe esta estrutura em `data/users/{user_id}`:

```txt
profile/
  onboarding.md
workspace/
uploads/
  original/{upload_id}/arquivo.ext
rag/
  extracted/{extraction_id}-arquivo.txt
  manifests/{manifest_id}-arquivo.json
skills/
  user/
  audit/
    workspace_plans/{plan_id}.json
```

`safe_user_path` permite apenas as areas `profile`, `workspace`, `uploads`, `rag` e `skills`. Caminhos absolutos, `..`, areas desconhecidas e tentativas de sair da raiz do usuario sao bloqueados.

## Fluxo de dados

```txt
upload original
  -> uploads/original
  -> documento com status uploaded
  -> acao explicita "Ingerir no RAG"
     -> extracao em rag/extracted
     -> chunks no RAG user_{user_id}_documents
     -> manifesto em rag/manifests
```

- O DocumentsPanel usa duas etapas: enviar e depois clicar em `Ingerir no RAG`.
- O endpoint de compatibilidade `/api/v1/upload` tambem apenas salva o original; nenhum upload normal entra automaticamente no RAG.
- Cada documento guarda checksum, parser, status, IDs vetoriais, caminho do original, caminho do texto extraido e caminho do manifesto.
- Excluir um documento remove vetores, original, texto extraido e manifesto do mesmo usuario.
- Refazer onboarding grava o perfil novo antes de remover os chunks e documentos de onboarding anteriores.

## RAG pessoal

- RAG e opt-in para uploads e arquivos do Workspace.
- Upload, criacao manual e criacao pela IA nunca indexam silenciosamente.
- O usuario pode selecionar `Ingerir no RAG` em Documentos ou `Selecionar para RAG` no Workspace.
- A IA pode sugerir arquivos criados/editados, mas o usuario marca quais deseja e confirma em uma segunda acao.
- Toda insercao, consulta e exclusao usa `user_{user_id}_documents`.
- O metadata dos chunks recebe o `user_id` autenticado.
- O chat usa RAG quando solicitado ou quando a skill `personal_rag` esta habilitada.
- O texto de cada chunk tem limite de 1000 caracteres; o chat recupera no maximo quatro chunks por consulta.

## Workspace

- Arquivos e pastas existem apenas em `workspace/` do usuario.
- A API autenticada permite listar, ler, escrever, criar pasta, mover e remover.
- O frontend mostra arvore recursiva de pastas e arquivos, com expandir/recolher e caminho visual.
- Itens internos podem ser arrastados para pastas e arquivos de texto externos podem ser importados, sempre com confirmacao.
- Pastas nao vazias podem ser apagadas recursivamente somente apos confirmacao explicita.
- Criar, editar, importar, mover e apagar no Workspace nao afeta o RAG automaticamente.
- Arquivos textuais tem limite de 1 MB.
- Nao e permitido apagar a raiz, mover a raiz, usar destino vazio, sobrescrever um destino existente ou mover uma pasta para dentro dela mesma.
- Patch exige checksum, cria snapshot e registra auditoria antes de aplicar.

## Skills

As skills sao registradas globalmente, mas habilitadas por usuario e auditadas no banco e em `skills/audit/skill_runs.jsonl`.

- `simple_search`: pesquisa web simples com fontes.
- `search_and_answer`: pesquisa e prepara contexto para a resposta.
- `personal_rag`: forca consulta ao RAG pessoal.
- `workspace_read`: le arquivo somente com `@workspace:read caminho/do/arquivo.md`.
- `workspace_write_preview`: gera apenas diff com `@workspace:preview caminho/do/arquivo.md`, linha `---` e novo conteudo.
- `workspace_manager`: detecta pedidos naturais no chat, usa a IA para planejar `mkdir`, `write_file`, `move` e `delete`, persiste o plano no UserSpace e so executa apos confirmacao visual.

Shell permanece bloqueado. A compatibilidade com o formato legado de skills de busca foi mantida sem conceder acesso a workspace ou shell.

## APIs principais

```txt
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/onboarding

POST /api/v1/documents/upload
POST /api/v1/documents/{doc_id}/ingest
GET  /api/v1/documents
GET  /api/v1/documents/{doc_id}/manifest
DELETE /api/v1/documents/{doc_id}

GET  /api/v1/workspace/tree
GET  /api/v1/workspace/file
PUT  /api/v1/workspace/file
POST /api/v1/workspace/mkdir
POST /api/v1/workspace/move
DELETE /api/v1/workspace/path
POST /api/v1/workspace/patch/preview
POST /api/v1/workspace/patch/apply
POST /api/v1/workspace/ai/plan
GET  /api/v1/workspace/ai/plans/{plan_id}
POST /api/v1/workspace/ai/plans/{plan_id}/apply
DELETE /api/v1/workspace/ai/plans/{plan_id}
POST /api/v1/workspace/rag/ingest

GET /api/v1/skills
PUT /api/v1/skills/{skill_name}
GET /api/v1/skills/runs
```

## Regras anti-travamento

- Fases pequenas e commits separados.
- Nenhum teste de longa duracao foi usado.
- A bateria curta roda em processo isolado e e interrompida apos 45 segundos.
- O teste historicamente lento `tests.test_auth_multiuser` continua fora da bateria curta.
- O chat limita chunks de RAG, buscas a no maximo cinco resultados e contexto de skill de workspace a 12000 caracteres.

## Validacao executada

Comando executado com corte automatico de 45 segundos:

```powershell
python -m unittest tests.test_userspace tests.test_workspace_agent tests.test_workspace_rag tests.test_workspace_service tests.test_workspace_routes tests.test_ingestion tests.test_rag_isolation tests.test_skill_permissions tests.test_skills_context tests.test_skill_runtime tests.test_skill_runs tests.test_auth_required tests.test_frontend_workspace_manager tests.test_frontend_workspace_patch_ui tests.test_frontend_workspace_patch_api tests.test_frontend_documents_panel
```

Resultado consolidado: `63` testes passaram em `6.499s`.

Aviso nao bloqueante observado: `StarletteDeprecationWarning` para o adaptador atual de `TestClient` e `httpx`.

## Build do frontend

Comando executado com corte automatico de 45 segundos:

```powershell
npm run build
```

Resultado: TypeScript e Vite concluiram o build de producao em `669ms`.

Aviso nao bloqueante observado: o bundle JavaScript principal ficou em `1,151.05 kB` (`372.49 kB` gzip), acima do limite de aviso de `500 kB`. Isso nao impede a execucao; code splitting pode reduzir o tamanho em uma etapa futura.

## Fora desta validacao

- O smoke manual anterior confirmou login, cadastro, onboarding e persistencia. O novo gerenciador da IA, arvore drag-and-drop e RAG opt-in ainda precisam do reteste visual final.
