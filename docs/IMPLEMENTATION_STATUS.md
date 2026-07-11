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

- `perplexo_search`: usa a API HTTP Perplexo para pesquisa web, profunda e academica com fontes. E habilitada por usuario, envia `user_id` isolado, nunca expoe `MCP_API_KEY` e pode usar a busca simples como fallback.
- `simple_search`: pesquisa web simples com fontes.
- `search_and_answer`: pesquisa e prepara contexto para a resposta.
- `personal_rag`: forca consulta ao RAG pessoal.
- `workspace_read`: le arquivo somente com `@workspace:read caminho/do/arquivo.md`.
- `workspace_write_preview`: gera apenas diff com `@workspace:preview caminho/do/arquivo.md`, linha `---` e novo conteudo.
- `workspace_manager`: detecta pedidos naturais no chat, usa a IA para planejar `mkdir`, `write_file`, `move` e `delete`, persiste o plano no UserSpace e so executa apos confirmacao visual.

Shell permanece bloqueado. A compatibilidade com o formato legado de skills de busca foi mantida sem conceder acesso a workspace ou shell.

O painel de Skills permite salvar por usuario o modelo, foco, periodo e uso de fallback da `perplexo_search`. O teste de conexao consulta somente `/health`; a execucao consulta somente `/search`. Endpoints de tokens e credenciais do servidor externo nao sao expostos ao modelo.

- Pesquisas concluidas geram um evento autenticado `skill_activity`. A resposta mostra um bloco verde expansivel `Ferramentas e Skills` com nome, estado e links reais das fontes.
- O modelo recebe instrucao explicita de que resultados presentes no contexto ja foram executados, evitando pedir uma segunda autorizacao depois da pesquisa.
- `messages.reasoning` e `messages.skill_activities_json` preservam Thinking e atividades apos atualizar ou reabrir a conversa.
- `skill_runs.output_summary` guarda a saida completa da pesquisa e o painel permite expandir o resultado, sem o corte antigo de 2.000 caracteres.

## Streaming e Thinking

- OpenCode/DeepSeek usa o SSE nativo de `/chat/completions`, sem passar pelo adaptador que descartava `reasoning_content`.
- O backend reconhece `reasoning_content`, `reasoning` e `thinking` separadamente do conteudo final.
- WebSocket e HTTP/SSE enviam estados de contexto, skills e geracao antes do primeiro token.
- A interface mostra esses estados no balao da resposta em andamento.
- O bloco Thinking continua visivel quando a resposta final comeca a chegar.
- Somente a ultima mensagem fica marcada como streaming.
- Blocos grandes retornados por providers sem granularidade sao repartidos para exibicao progressiva.
- A preferencia `use_thinking` agora tambem e enviada pelo fallback HTTP/SSE.

No teste real com `deepseek-v4-flash-free`, o gateway enviou `reasoning_content` em SSE e o novo adaptador entregou o primeiro Thinking ao aplicativo antes do primeiro token da resposta final.

## Live, STT e Inworld TTS

- O modo Live mantem STT continuo via reconhecimento de fala do Chrome/Edge.
- O TTS nativo do navegador foi removido; todo audio e solicitado ao backend Inworld autenticado.
- O frontend transforma somente a resposta final em trechos estaveis de 24 a 150 caracteres enquanto o streaming ainda esta ativo.
- Ate dois trechos MP3 sao preparados em paralelo e reproduzidos na ordem para reduzir o tempo ate a primeira fala.
- Vozes clonadas `IVC` do workspace Inworld aparecem antes das vozes de sistema.
- A voz e as preferencias ficam separadas por usuario do aplicativo.
- Interromper cancela reconhecimento, audio, downloads pendentes e a resposta ativa antes de voltar a ouvir.
- A chave `INWORLD_API_KEY` nunca e enviada ao frontend.
- O codigo, os mocks e um smoke real com voz clonada do workspace Inworld foram validados.

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
GET /api/v1/skills/perplexo/status
POST /api/v1/skills/perplexo/test

GET  /api/v1/tts/inworld/status
GET  /api/v1/tts/inworld/voices
POST /api/v1/tts/inworld/synthesize
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

Resultado consolidado mais recente: `71` testes passaram em `15.141s`.

Aviso nao bloqueante observado: `StarletteDeprecationWarning` para o adaptador atual de `TestClient` e `httpx`.

### Validacao da Skill Perplexo

Comando curto executado com limite automatico:

```powershell
python -m unittest tests.test_perplexo_search tests.test_skill_runtime tests.test_skill_permissions tests.test_skills_context
```

Resultado: `11` testes passaram em `0.381s`. Foram validados autenticacao por `X-API-Key`, isolamento por `user_id`, formatacao de fontes, selecao automatica de pesquisa profunda, fallback e permissoes.

O teste real de `GET https://api.ghost1.cloud/health` retornou HTTP `200` com estado `healthy`. Uma chamada real de `POST /search` tambem foi concluida e retornou resposta com fonte. A chave permaneceu somente no `.env` ignorado pelo Git.

## Build do frontend

Comando executado com corte automatico de 45 segundos:

```powershell
npm run build
```

Resultado mais recente: TypeScript e Vite concluiram o build de producao em `788ms`.

Aviso nao bloqueante observado: o bundle JavaScript principal ficou em `1,162.19 kB` (`375.03 kB` gzip), acima do limite de aviso de `500 kB`. Isso nao impede a execucao; code splitting pode reduzir o tamanho em uma etapa futura.

### Validacao do Live/Inworld TTS

```powershell
python -m unittest tests.test_inworld_tts tests.test_frontend_live_voice
```

Resultado: `7` testes passaram em `0.036s`. Tambem passaram `python -m compileall -q src`
e a build TypeScript/Vite. Foram validados autenticacao Basic somente no backend,
ordem das vozes clonadas, filtro de idioma, payload MP3 de baixa latencia, limites,
segmentacao progressiva e ausencia de `SpeechSynthesisUtterance`.

No smoke real, a API retornou `28` vozes em portugues, incluindo `14` vozes clonadas
`IVC`. Um trecho de `50` caracteres foi sintetizado com uma voz clonada usando
`inworld-tts-2`; a resposta teve `68.781` bytes e assinatura MP3 valida. A chave ficou
somente no `.env` local ignorado pelo Git e nao foi registrada nos logs do teste.

## Smoke visual isolado

Em 10 de julho de 2026, backend e frontend foram iniciados com banco, UserSpace e Chroma temporarios, sem usar nem alterar `data/` ou `.env` do usuario. O navegador real confirmou:

- cadastro e login automatico da conta temporaria;
- modal de onboarding e WebSocket conectado;
- criacao de pasta e arquivo no Workspace, edicao e salvamento com confirmacao visual;
- arquivo de Workspace permanecendo fora do RAG;
- upload aparecendo imediatamente em Documentos como `Aguardando RAG`, com `0 chunks`;
- ingestao somente apos clique explicito em `Ingerir no RAG`;
- transicao do documento para `indexed`, com `37 chunks` e texto derivado em `rag/extracted`;
- painel de Skills carregando as sete habilidades e seus estados por usuario.

Os dois servidores e todo o armazenamento temporario foram encerrados e removidos ao final do smoke.
