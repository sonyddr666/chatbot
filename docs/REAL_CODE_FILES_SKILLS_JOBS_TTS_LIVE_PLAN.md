# Extracao de codigo real: arquivos, Skills, Jobs, SSE, TTS e Live

## Objetivo

Este documento transforma implementacoes reais de cinco repositorios relacionados em uma proposta segura para o chatbot Python atual.

O foco e:

- gerenciamento completo de arquivos por usuario;
- Skills registradas, executadas e auditadas;
- arquivos do Workspace entregues pelo LLM dentro da conversa;
- Jobs persistentes que sobrevivem a fechamento de aba e reconexao;
- streaming SSE reanexavel e independente do provider;
- TTS que comeca enquanto a resposta ainda esta sendo formada;
- modo Live com escuta, timer de silencio, fala, interrupcao e retomada;
- integracao sem destruir a separacao atual entre Workspace, uploads e RAG.

Esta analise nao usa README como prova de funcionalidade. As conclusoes foram extraidas de implementacao, rotas, services, adapters, frontend e testes.

## Snapshot auditado

Auditoria executada em 10 de julho de 2026.

| Repositorio | Branch | Commit auditado | Evidencia principal |
|---|---|---|---|
| `sonyddr666/code-chat-skills` | `main` | `7810cd8915263201d404e798dfa996c2fd268cda` | `server.js`, `public/index.html`, `public/account.js` |
| `sonyddr666/skills-chat` | `main` | `d8f131b27167711339ce00ec1d73f4c904675994` | `server.js`, `public/index.html` |
| `sonyddr666/skillflow-chat` | `main` | `62e23f4d73b40d2f5b17a1b681d8e52bd004e3b9` | `server.js`, `public/index.html` |
| `sonyddr666/skillchat` | `main` | `7fd6529a4cacf66b7595feb256b9cc109c4f9fb6` | `app/services`, `app/routers`, `app/adapters`, `tests` |
| `sonyddr666/code-chat-skills-rag-clean` | `rag-clean` | `e44bc9efbcb2cf79f28dd7ca782720bafb307a75` | `rag/server.js`, `rag/indexer.js`, `rag/retriever.js`, `rag/generator.js` |

Links permanentes:

- `https://github.com/sonyddr666/code-chat-skills/tree/7810cd8915263201d404e798dfa996c2fd268cda`
- `https://github.com/sonyddr666/skills-chat/tree/d8f131b27167711339ce00ec1d73f4c904675994`
- `https://github.com/sonyddr666/skillflow-chat/tree/62e23f4d73b40d2f5b17a1b681d8e52bd004e3b9`
- `https://github.com/sonyddr666/skillchat/tree/7fd6529a4cacf66b7595feb256b9cc109c4f9fb6`
- `https://github.com/sonyddr666/code-chat-skills-rag-clean/tree/e44bc9efbcb2cf79f28dd7ca782720bafb307a75`

## Veredito direto

### Melhor fonte de recursos avancados

`code-chat-skills` possui a implementacao mais completa de:

- filesystem real por usuario;
- anexos persistentes e reidrataveis;
- Skills builtin, HTTP, exec e codigo;
- tools que criam ou anexam arquivos na conversa;
- Jobs de chat persistidos em disco;
- retomada de Jobs pelo frontend;
- TTS dividido em chunks com prefetch;
- STT continuo e Gemini Live;
- tool calls durante o modo Live.

O custo e uma arquitetura muito concentrada:

- `server.js`: aproximadamente 2.244 linhas;
- `public/index.html`: aproximadamente 8.732 linhas.

### Melhor fonte de organizacao

`skillchat` e a melhor referencia estrutural:

- routers separados;
- services separados;
- schemas Pydantic;
- adapters por provider;
- testes por responsabilidade.

Ele nao possui a mesma infraestrutura de Jobs, artifacts, TTS e Live da base Node.

### Fonte que nao deve ser copiada diretamente

`code-chat-skills-rag-clean` contem ideias uteis de Qdrant, BM25 e RRF, mas a branch auditada ainda apresenta falhas de contrato, autenticacao e isolamento descritas adiante.

### Estrategia recomendada

Nao substituir o chatbot atual por nenhum desses repositorios.

O chatbot atual ja tem uma base Python mais segura para multiusuario, Workspace, RAG opt-in e Skills. A estrategia correta e transportar os conceitos avancados da base Node para services pequenos dentro desta arquitetura.

---

# 1. Gerenciamento real de arquivos

## 1.1 Isolamento encontrado na base Node

`code-chat-skills/server.js` cria diretorios por `user.id`:

```js
function userSkillsDir(user) {
  return join(skillsRootDir, user.id);
}

function userWorkspaceDir(user) {
  return join(workspaceRootDir, user.id);
}

function userRunsDir(user) {
  return join(userWorkspaceDir(user), ".runs");
}

function userChatJobsDir(user) {
  return join(userWorkspaceDir(user), ".chat-jobs");
}
```

O path final e validado resolvendo o caminho e calculando a volta ate a raiz:

```js
function workspacePath(user, input) {
  const root = userWorkspaceDir(user);
  const rel = normalizeRelativePath(input);
  const absolute = resolve(root, rel || ".");
  const back = relative(root, absolute);
  if (back.startsWith("..") || back.includes(`..${process.platform === "win32" ? "\\" : "/"}`)) {
    throw new Error("Path escapes workspace root");
  }
  return { rel, absolute };
}
```

Essa e uma defesa correta contra path traversal, desde que symlinks e ownership tambem sejam verificados em operacoes sensiveis.

## 1.2 Estrutura fisica da base Node

```text
skills/
  {user_id}/
    {skill_id}.json

workspace/
  {user_id}/
    arquivos do usuario
    .uploads/
    .outputs/
    .runs/
    .chat-jobs/
```

O chatbot atual usa uma separacao melhor e deve preserva-la:

```text
data/users/{user_id}/
  profile/
  workspace/
  uploads/original/
  rag/extracted/
  rag/manifests/
  skills/user/
  skills/audit/
```

Regra: Jobs e artifacts podem ganhar suas proprias areas, mas uploads e RAG nao devem voltar para dentro do Workspace.

Estrutura alvo:

```text
data/users/{user_id}/
  workspace/
  uploads/original/
  rag/
  skills/
  artifacts/
    metadata/
  jobs/
    chat/{job_id}/
      meta.json
      events.ndjson
      snapshot.json
      result.json
      artifacts.json
```

## 1.3 Rotas encontradas

A base Node implementa operacoes equivalentes a:

```text
GET    /api/fs/list
GET    /api/fs/read
GET    /api/fs/download
POST   /api/fs/write
POST   /api/fs/mkdir
POST   /api/fs/rename
DELETE /api/fs/delete
```

O chatbot atual ja possui:

```text
GET    /api/v1/workspace/tree
GET    /api/v1/workspace/file
PUT    /api/v1/workspace/file
POST   /api/v1/workspace/mkdir
POST   /api/v1/workspace/move
DELETE /api/v1/workspace/path
POST   /api/v1/workspace/patch/preview
POST   /api/v1/workspace/patch/apply
```

Lacunas reais do chatbot atual:

- download autenticado de arquivo do Workspace;
- contrato de artifact associado a uma mensagem;
- anexo visual de arquivo produzido pelo modelo;
- reidratacao de anexo para providers multimodais;
- quota e retencao por usuario.

## 1.4 Reidratacao de anexos

Na base Node, arquivos antigos podem ser lidos em base64 quando uma conversa e reenviada ao modelo. A implementacao limita essa reidratacao aos turnos recentes e conserva `path`, `name`, `mimeType` e URL de download no historico.

Esse conceito e util, mas deve ser adaptado:

- o backend deve decidir se um arquivo pode ser reidratado;
- o frontend nunca deve guardar chaves ou base64 grande em `localStorage`;
- imagens podem virar input multimodal quando o provider suportar;
- documentos de texto devem usar extracao limitada;
- o limite deve ser aplicado antes da leitura completa;
- o arquivo sempre pertence ao `user_id` autenticado.

---

# 2. Skills reais

## 2.1 Registro persistente encontrado

A base Node normaliza uma Skill customizada como:

```json
{
  "id": "minha_skill",
  "builtin": false,
  "enabled": true,
  "name": "minha_skill",
  "description": "Descricao usada pelo modelo",
  "parameters": {
    "type": "OBJECT",
    "properties": {}
  },
  "action": {}
}
```

Ela tambem aceita `code` em vez de `action`. Essa parte nao deve ser copiada sem sandbox.

## 2.2 Tipos de executor encontrados

O codigo real mostra estes conceitos:

- builtin no frontend;
- HTTP request configuravel;
- execucao de processo no backend;
- codigo JavaScript dinamico;
- workflows de varias etapas;
- tools nativas para arquivos e historico.

## 2.3 O que o chatbot atual ja faz melhor

O chatbot atual possui:

- `src/core/skill_registry.py` como catalogo autoritativo;
- `src/core/skill_permissions.py` para permissoes;
- `src/core/skill_runtime.py` para execucao;
- ativacao por usuario em banco;
- auditoria em `skill_runs` e JSONL;
- shell sempre bloqueado;
- acesso ao Workspace apenas por capacidades declaradas;
- `workspace_manager` com plano e confirmacao;
- pesquisa, RAG pessoal, leitura e preview de escrita.

Essa base deve permanecer.

## 2.4 Riscos encontrados que nao devem entrar

### Codigo arbitrario no navegador

`code-chat-skills/public/index.html` executa Skills customizadas com:

```js
const fn = new Function('args', 'convs', 'activeId', p.code);
return fn(args, convs, activeId) ?? { result: 'ok' };
```

Isso nao e sandbox. O codigo pode acessar DOM, rede, conversas e armazenamento do navegador.

### Calculadora com `Function`

```js
const result = Function('"use strict"; return (' + expr + ')')();
```

Uma calculadora deve usar parser matematico com AST e allowlist de operadores.

### Shell na allowlist

A allowlist padrao da base Node inclui `bash` e `sh`. Isso anula boa parte da protecao quando o binario recebe `-c`.

### Estado global da conversa

Varias tools leem `convs[activeId]`. Se o usuario trocar de conversa durante um Job, uma tool pode operar no chat errado.

### Contrato correto para este projeto

Toda execucao precisa receber um contexto imutavel:

```python
@dataclass(frozen=True)
class SkillExecutionContext:
    user_id: int
    conversation_id: int
    session_id: str
    message_id: int
    job_id: str
    skill_name: str
```

Nenhuma Skill deve consultar "conversa ativa" no frontend.

## 2.5 Autoria de Skill por conversa

O plano Hermes existente ja descreve autoria conversacional. A extracao dos repositorios reforca o contrato recomendado:

1. O modelo gera uma proposta estruturada.
2. O backend valida nome, schema, executor e permissoes.
3. A interface mostra diff e capacidades solicitadas.
4. O usuario aprova.
5. A Skill recebe versao imutavel.
6. A ativacao e separada da criacao.
7. Cada execucao gera auditoria.
8. Rollback restaura uma versao anterior.

Executores permitidos inicialmente:

- `http` com host allowlisted;
- `internal_tool` registrada no codigo;
- `workflow` composto apenas de tools registradas;
- `prompt_template` sem execucao externa.

Executores proibidos inicialmente:

- JavaScript livre;
- Python livre;
- shell livre;
- comando fornecido pelo modelo;
- URL arbitraria sem allowlist.

---

# 3. Arquivos entregues pelo LLM na conversa

## 3.1 Funcionalidade comprovada

`code-chat-skills/public/index.html` possui duas tools centrais.

### Anexar arquivo existente

```js
async attach_workspace_file_to_chat(args) {
  const normalizedPath = await resolveExistingWorkspaceFilePath(args.path, {
    conversationId: activeId
  });
  return {
    ok: true,
    answer,
    resolved_path: normalizedPath,
    artifacts: [{
      path: normalizedPath,
      name: fileName,
      mimeType
    }]
  };
}
```

### Criar arquivo textual e anexar

```js
async create_text_file_for_user(args) {
  const payload = await fetchLocalJson('/api/fs/write', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path: normalizedPath,
      content,
      create_dirs: args.create_dirs !== false
    })
  });
  return {
    ok: true,
    answer,
    write: payload,
    artifacts: [{
      path: payload.path || normalizedPath,
      name: fileName,
      mimeType
    }]
  };
}
```

O frontend normaliza respostas com estas chaves:

- `artifacts`;
- `files`;
- `attachments`;
- `artifact`;
- `file`;
- `attachment`.

Depois associa os arquivos a mensagem e gera uma URL de download local.

## 3.2 O que falta no chatbot atual

O chatbot atual consegue criar arquivos por um plano de Workspace, mas a mensagem nao possui um contrato de artifacts. Por isso, o modelo pode criar o arquivo e ainda assim nao entregar um cartao de arquivo na conversa.

## 3.3 Modelo alvo

Nova tabela:

```text
message_artifacts
  id
  user_id
  conversation_id
  message_id
  job_id nullable
  source_area
  relative_path
  display_name
  mime_type
  size_bytes
  checksum
  status
  created_at
```

Valores de `source_area` permitidos:

- `workspace`;
- `upload`;
- `generated`.

`rag` nao deve ser uma fonte de download. RAG e indice derivado, nao arquivo original.

## 3.4 Contrato de API

```json
{
  "id": 41,
  "name": "relatorio.md",
  "mime_type": "text/markdown",
  "size": 4821,
  "source_area": "workspace",
  "path": "relatorios/relatorio.md",
  "download_url": "/api/v1/artifacts/41/download",
  "preview": {
    "kind": "text",
    "available": true
  }
}
```

Rotas propostas:

```text
GET    /api/v1/messages/{message_id}/artifacts
POST   /api/v1/messages/{message_id}/artifacts/from-workspace
GET    /api/v1/artifacts/{artifact_id}
GET    /api/v1/artifacts/{artifact_id}/download
DELETE /api/v1/artifacts/{artifact_id}
```

## 3.5 Tool segura para anexar arquivo

```json
{
  "name": "attach_workspace_file",
  "arguments": {
    "path": "relatorios/resultado.md",
    "display_name": "resultado.md"
  }
}
```

Fluxo:

1. O modelo solicita a tool.
2. O backend usa o `user_id` autenticado.
3. `safe_user_path(user_id, "workspace", path)` resolve o arquivo.
4. O backend valida existencia, arquivo regular, tamanho e MIME.
5. O backend calcula checksum.
6. O artifact e associado a mensagem atual.
7. Um evento `artifact.attached` e emitido.
8. O frontend mostra o cartao imediatamente.

O modelo nunca fornece uma URL de download confiavel. A URL e sempre gerada pelo backend usando o ID do artifact.

## 3.6 Criacao de arquivo continua confirmada

Para criar ou editar:

1. `workspace_manager` prepara o plano.
2. O usuario confirma.
3. O plano e aplicado.
4. O backend emite `workspace.plan_applied`.
5. Arquivos resultantes podem ser anexados a resposta como artifacts.
6. A selecao para RAG continua sendo outra acao explicita.

Criar arquivo, anexar arquivo e indexar no RAG sao tres operacoes diferentes.

---

# 4. Jobs persistentes

## 4.1 Implementacao encontrada

Cada Job da base Node usa:

```js
function chatJobPaths(user, jobId) {
  const dir = join(userChatJobsDir(user), sanitizeId(jobId));
  return {
    dir,
    meta: join(dir, "meta.json"),
    stream: join(dir, "stream.sse"),
    result: join(dir, "result.json")
  };
}
```

Rotas:

```text
POST /api/chat/jobs
GET  /api/chat/jobs/{job_id}
```

O `POST` cria metadata e inicia `executeChatJob()` sem esperar o fim. O `GET` devolve snapshot e informa se o Job ainda esta ativo.

## 4.2 O que funciona

- o Job possui ID estavel;
- o Job nao depende do componente React continuar montado;
- o frontend pode reabrir e consultar o mesmo ID;
- status e resultado ficam em disco;
- erros finais ficam associados ao Job;
- mensagens guardam referencia ao Job;
- ha deduplicacao de estado entre abas.

## 4.3 O que ainda nao e streaming reanexavel

O frontend usa polling:

```js
async function waitForChatJob(jobId, options = {}) {
  while (true) {
    const snapshot = await fetchChatJobSnapshot(jobId, options.signal);
    if (options.onSnapshot) options.onSnapshot(snapshot);
    const status = snapshot?.job?.status || '';
    if (status === 'completed' || status === 'failed') return snapshot;
    await sleepWithSignal(options.pollMs || 250, options.signal);
  }
}
```

Para Gemini, `stream.sse` cresce em disco, mas cada consulta pode devolver e parsear o arquivo inteiro novamente.

Para Codex, o request envia `stream: true`, mas usa:

```js
let response = await sendCodexRequest(true);
let raw = await response.text();
```

Assim, o backend espera o corpo completo antes de produzir `result.json`.

## 4.4 Cancelamento incompleto

Abortar polling no navegador nao cancela automaticamente o provider nem o Job no servidor.

Contrato necessario:

```text
POST /api/v1/chat/jobs/{job_id}/cancel
```

O JobManager deve guardar um `asyncio.Task` e um cancel token por Job ativo.

## 4.5 Modelo alvo para o chatbot atual

Tabela `chat_jobs`:

```text
id UUID/string
user_id
conversation_id
user_message_id
assistant_message_id
provider_id
model_id
status queued|running|waiting_tool|completed|failed|cancelled|interrupted
last_event_seq
error_code nullable
error_message nullable
created_at
started_at nullable
finished_at nullable
heartbeat_at nullable
```

Tabela `chat_job_events`:

```text
id
job_id
user_id
seq
event_type
payload_json
created_at
```

Indice unico:

```text
(job_id, seq)
```

O arquivo `events.ndjson` pode existir como espelho operacional, mas SQLite deve ser a fonte de verdade para consulta e ownership.

## 4.6 Reconciliacao apos restart

Ao iniciar a API:

1. localizar Jobs `running` ou `waiting_tool` sem heartbeat recente;
2. marcar como `interrupted` se o provider nao permitir retomada;
3. preservar texto parcial e artifacts;
4. emitir evento terminal de reconciliacao;
5. permitir regeneracao sem perder a mensagem anterior.

Nao declarar um Job antigo como `completed` apenas porque o processo morreu.

---

# 5. Protocolo de eventos normalizado

## 5.1 Motivo

O frontend atual conhece eventos WebSocket/SSE como `reasoning`, `token`, `skill_activity`, `workspace_plan` e `done`. Isso ja e uma boa base, mas ainda esta ligado a uma requisicao ativa.

Jobs exigem eventos persistidos e reanexaveis.

## 5.2 Envelope

```json
{
  "job_id": "job_01J...",
  "seq": 17,
  "type": "text.delta",
  "created_at": "2026-07-10T20:00:00Z",
  "payload": {
    "delta": "parte da resposta"
  }
}
```

## 5.3 Tipos minimos

```text
job.queued
job.started
context.started
context.completed
reasoning.delta
text.delta
tool.requested
tool.started
tool.completed
tool.failed
skill.started
skill.completed
skill.failed
workspace.plan_created
workspace.plan_applied
artifact.created
artifact.attached
usage.updated
tts.segment_ready
job.completed
job.failed
job.cancelled
job.interrupted
```

## 5.4 SSE por Job

```text
GET /api/v1/chat/jobs/{job_id}/events
```

Exemplo:

```text
id: 17
event: text.delta
data: {"job_id":"job_01J...","seq":17,"payload":{"delta":"parte"}}

```

Headers:

```text
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

Reconexao:

- navegador envia `Last-Event-ID`;
- backend valida ownership do Job;
- eventos com `seq > Last-Event-ID` sao reproduzidos;
- depois o cliente entra no fluxo ao vivo;
- duplicatas sao ignoradas por `(job_id, seq)`.

## 5.5 WebSocket e SSE devem compartilhar a mesma fonte

O projeto pode manter WebSocket para baixa latencia, mas WebSocket nao deve ser a unica fonte de estado.

```text
ProviderAdapter
      |
      v
JobEventStore ---> SSE /events
      |
      +----------> WebSocket autenticado
      |
      +----------> persistencia de mensagem
      |
      +----------> TTS progressivo
```

## 5.6 ProviderAdapter

```python
class ProviderAdapter(Protocol):
    async def stream(
        self,
        request: ProviderRequest,
        cancel: asyncio.Event,
    ) -> AsyncIterator[ProviderEvent]: ...
```

Cada provider converte seu protocolo para eventos comuns. O frontend nao deve saber se a origem e OpenAI Responses, Chat Completions, Gemini SSE ou outro gateway.

---

# 6. TTS encontrado no codigo real

## 6.1 Constantes atuais

`code-chat-skills/public/index.html` usa:

```js
const TTS_FIRST_CHUNK_MAX_CHARS = 120;
const TTS_MAX_CHARS_PER_CHUNK = 250;
const TTS_PREFETCH_AHEAD = 2;
```

## 6.2 Pipeline real

```text
resposta final
  -> limpar Markdown
  -> separar por frases
  -> primeiro chunk ate 120 caracteres
  -> proximos chunks ate 250 caracteres
  -> buscar audio
  -> prefetch de dois chunks
  -> tocar em ordem
  -> revogar Object URLs
```

## 6.3 Pontos bons

- remove blocos de codigo antes de falar;
- segmenta em fronteiras de pontuacao;
- divide frases longas;
- evita request duplicado por chunk;
- usa `AbortController` em fetches;
- mantem sessao numerada para ignorar audio antigo;
- faz prefetch;
- para audio atual e limpa fila;
- mostra progresso do chunk.

## 6.4 Limite atual

`ttsSpeakMsg(idx)` recebe `msgs[idx].text`, ou seja, uma mensagem ja montada. O autoplay comum e disparado no final da resposta.

Isso e TTS progressivo na reproducao, mas nao TTS conectado diretamente aos deltas do modelo.

---

# 7. TTS enquanto a resposta se forma

## 7.1 Estado por Job

```ts
interface ProgressiveTtsState {
  jobId: string
  messageId: number
  receivedText: string
  committedUntil: number
  spokenUntil: number
  segmentBuffer: string
  queue: TtsSegment[]
  currentSegmentId?: string
  enabled: boolean
  playing: boolean
  completed: boolean
  cancelled: boolean
}
```

## 7.2 Segmento

```ts
interface TtsSegment {
  id: string
  start: number
  end: number
  text: string
  status: 'queued' | 'fetching' | 'ready' | 'playing' | 'played' | 'failed'
  audioUrl?: string
}
```

## 7.3 Regra de estabilidade

Nao enviar token por token ao TTS.

Um segmento fica estavel quando:

- tem pelo menos 45 caracteres e termina em `.`, `!`, `?`, `;` ou `:`;
- ou alcanca 190 caracteres e pode ser cortado em espaco;
- nao esta dentro de bloco de codigo aberto;
- nao pertence ao reasoning;
- ainda nao foi comprometido para fala.

No evento `job.completed`, o restante e descarregado.

## 7.4 Fluxo

```text
text.delta
   -> acrescentar receivedText
   -> segmentador incremental
   -> tts.segment_ready persistido
   -> POST /api/v1/tts/synthesize
   -> fila de audio com prefetch 2
   -> reproduzir em ordem
   -> atualizar spokenUntil
```

## 7.5 Seguranca da API TTS

A base Node coloca endpoint e chave de TTS no frontend. Este projeto nao deve copiar isso.

Contrato:

```text
POST /api/v1/tts/synthesize
```

```json
{
  "job_id": "job_01J...",
  "segment_id": "seg_0004",
  "text": "Trecho estavel para fala.",
  "voice_id": "pt-BR-voz",
  "format": "mp3"
}
```

O backend:

- autentica o usuario;
- valida ownership do Job;
- limita tamanho;
- remove texto de reasoning;
- usa a chave secreta apenas no servidor;
- aplica rate limit;
- devolve audio ou URL curta assinada.

## 7.6 Cancelamento

Ao parar ou interromper:

1. pausar audio atual;
2. revogar URLs locais;
3. abortar fetches pendentes;
4. limpar segmentos ainda nao tocados;
5. persistir `spokenUntil`;
6. opcionalmente cancelar o Job do modelo;
7. voltar ao estado de escuta quando Live estiver ativo.

## 7.7 Nao falar

- reasoning interno;
- stack traces;
- JSON de tool;
- blocos de codigo;
- URLs longas;
- mensagens de sistema;
- texto substituido antes de virar segmento estavel.

---

# 8. Modo Live encontrado

## 8.1 Live por SpeechRecognition + chat comum

A base Node possui um modo que:

- inicia reconhecimento continuo do navegador;
- mostra transcricao parcial no input;
- acumula resultados finais;
- reinicia o reconhecimento quando o navegador encerra a sessao;
- usa timer de silencio;
- envia a pergunta pelo chat comum;
- espera a resposta;
- chama TTS;
- retoma a escuta.

Constante real:

```js
const LIVE_SILENCE_MS = 3000;
```

O timer e reiniciado quando o texto muda. Ao vencer, `liveTriggerSend()` envia a pergunta.

## 8.2 Gemini Live nativo

Outra implementacao abre WebSocket do Gemini Live e inclui:

- audio PCM de entrada;
- audio PCM de saida;
- transcricao do usuario;
- transcricao do modelo;
- tool calls;
- barge-in/interrupcao;
- compartilhamento de tela;
- preview de fala;
- persistencia do turno ao terminar.

Esse modo e realmente bidirecional. Ele nao deve ser confundido com SpeechRecognition + request HTTP + TTS.

## 8.3 Estados alvo

```text
IDLE
LISTENING
ENDPOINTING
SENDING
GENERATING
SPEAKING
BARGE_IN
RECONNECTING
ERROR
```

Transicoes principais:

```text
IDLE -> LISTENING
LISTENING -> ENDPOINTING
ENDPOINTING -> SENDING
SENDING -> GENERATING
GENERATING -> SPEAKING
SPEAKING -> LISTENING
SPEAKING -> BARGE_IN
BARGE_IN -> LISTENING
```

## 8.4 Timer configuravel

```json
{
  "endpointing_silence_ms": 1200,
  "minimum_utterance_ms": 250,
  "resume_listening_delay_ms": 150,
  "tts_min_segment_chars": 45,
  "tts_max_segment_chars": 190,
  "tts_prefetch_ahead": 2,
  "barge_in_enabled": true
}
```

Tres segundos e seguro para nao cortar frases, mas deixa a conversa lenta. O alvo inicial recomendado e 1.200 ms configuravel, com fallback para 3.000 ms em navegadores instaveis.

## 8.5 Privacidade

- Live inicia desligado;
- microfone exige acao explicita;
- nenhum audio cru e persistido por padrao;
- transcricao parcial nao entra no RAG;
- somente o turno confirmado e salvo como mensagem;
- configuracao e por usuario;
- indicador visual de microfone e obrigatorio;
- parar deve encerrar tracks de audio;
- TTS deve ser ignorado pelo STT para evitar eco.

## 8.6 AudioWorklet

A implementacao auditada ainda usa `ScriptProcessorNode` em parte da captura. A evolucao deve usar `AudioWorklet` para:

- menor jitter;
- processamento fora da thread principal;
- VAD local;
- medicao de volume;
- melhor separacao entre audio do microfone e UI.

---

# 9. Diagnostico do fork RAG

## 9.1 Ideias aproveitaveis

- chunks com overlap;
- fingerprint SHA-256;
- embeddings por lote;
- Qdrant;
- payload com `userId`, source e chunk index;
- dense retrieval;
- BM25;
- Reciprocal Rank Fusion;
- metadata de qualidade e obsolescencia;
- Jobs para geracao final.

## 9.2 Falhas comprovadas na branch auditada

### Usuario vindo do corpo

`POST /api/rag/ingest` recebe `userId` do request. O usuario deveria vir da sessao autenticada.

### Busca sem isolamento obrigatorio

`/api/rag/query` chama:

```js
hybridSearch(query, { top_k })
```

O filtro `userId` so e aplicado se for enviado em options.

### BM25 global

O indice MiniSearch e reconstruido com ate 10.000 pontos da collection e nao carrega `userId` em seus `storeFields`. A busca sparse pode misturar usuarios.

### Bloco duplicado

`rag/server.js` possui um bloco repetido apos `/api/rag/query`, com chave orfa. A verificacao direta abaixo confirmou o erro na branch auditada:

```powershell
node --check rag/server.js
```

Resultado: `SyntaxError: Unexpected token '}'` na linha 128.

### Retorno inconsistente

`ingestFile()` retorna:

```json
{"fileId":"...","chunkCount":10}
```

Mas a rota usa esse objeto inteiro em `chunks_ingested`.

### Contrato de mensagens incompativel

`generator.js` envia `messages` com `role: system/user` e `content`, enquanto o backend Node normaliza seu proprio contrato. Essa integracao precisa de adapter explicito.

### Autenticacao interna ausente

As chamadas Axios ao backend principal nao mostram cookie ou credencial de servico apropriada.

### Resultado final incorreto

O polling tenta ler `data.job.final_text`, mas o resultado Codex esta dentro do payload persistido.

## 9.3 Decisao para este projeto

Nao importar esse servico RAG.

O chatbot atual ja possui:

- collection por usuario;
- metadata com `user_id`;
- uploads separados;
- ingestao opt-in;
- Workspace selecionado explicitamente;
- manifests;
- delecao de vetores por usuario.

As ideias de busca hibrida podem ser incorporadas depois, mantendo o isolamento atual como invariante obrigatoria.

---

# 10. Comparacao com o chatbot atual

| Capacidade | Chatbot atual | Base Node | Acao |
|---|---|---|---|
| Login e multiusuario | Implementado com token e banco | Sessao em memoria | Manter atual |
| UserSpace seguro | Implementado | Workspace por user ID | Manter atual |
| Workspace CRUD | Implementado | Implementado | Adicionar download/artifacts |
| Upload separado do RAG | Implementado | Upload dentro do Workspace | Manter atual |
| RAG opt-in | Implementado | Fork RAG inseguro | Manter atual |
| Skills com permissao | Implementado | Mais tipos, menos sandbox | Expandir executores seguros |
| IA gerencia arquivos | Plano confirmado | Tool direta | Manter confirmacao atual |
| Arquivo no chat | Nao implementado | Implementado por artifacts | Portar conceito |
| Job persistente | Nao implementado | Meta/stream/result em disco | Criar JobManager modular |
| SSE reanexavel | Nao | Polling de snapshot | Implementar protocolo novo |
| Streaming Codex | Streaming no fluxo ativo | `response.text()` no Job | Manter adapter incremental atual e ligar a Job |
| Thinking persistido | Implementado | Trace local | Manter atual |
| Skill activity persistida | Implementado | Trace local | Manter atual |
| TTS | Nao integrado | Chunks apos resposta | Criar TTS incremental |
| STT/Live | Plano futuro | Implementado no frontend | Portar maquina de estados, nao codigo monolitico |
| Gemini Live | Nao | Implementado | Fase separada opcional |

---

# 11. Arquitetura alvo deste chatbot

```text
Frontend React
  ChatStore
  JobEventClient
  ArtifactRenderer
  ProgressiveTtsSession
  LiveTurnManager
          |
          | WebSocket ou SSE com Last-Event-ID
          v
FastAPI
  chat_job_routes
  artifact_routes
  tts_routes
  live_session_routes opcional
          |
          v
Core
  ChatJobService
  ChatEventStore
  ProviderAdapterRegistry
  ArtifactService
  ProgressiveTtsPolicy
  SkillRuntime
  WorkspaceService
          |
          v
Storage
  SQLite: jobs, events, artifacts, ownership
  UserSpace: snapshots, NDJSON e arquivos
  Chroma: RAG pessoal isolado
```

## 11.1 Novos modulos sugeridos

```text
src/core/chat_jobs.py
src/core/chat_events.py
src/core/artifacts.py
src/core/provider_events.py
src/core/tts.py
src/api/job_routes.py
src/api/artifact_routes.py
src/api/tts_routes.py

frontend/src/jobs/jobEventClient.ts
frontend/src/jobs/jobTypes.ts
frontend/src/artifacts/ArtifactCard.tsx
frontend/src/artifacts/artifactTypes.ts
frontend/src/voice/progressiveTts.ts
frontend/src/voice/liveTurnManager.ts
```

## 11.2 Invariantes

- `user_id` vem da autenticacao, nunca do body.
- Toda leitura de Job filtra por `user_id`.
- Toda leitura de artifact filtra por `user_id`.
- Todo path passa por `safe_user_path`.
- Artifact nao transforma arquivo em RAG.
- RAG nao vira download de arquivo.
- Criacao e edicao pela IA continuam confirmadas.
- Reasoning nunca e enviado ao TTS.
- Secrets ficam somente no backend.
- Skill nao recebe shell livre.
- Evento possui sequencia monotona por Job.
- Um Job pertence a uma conversa imutavel.

---

# 12. Ordem real de implementacao

## Fase 0: contratos, sem alterar chat

Criar:

- tipos de evento;
- schemas de Job;
- schemas de artifact;
- documento de migracao;
- testes de serializacao e ownership.

Nao criar servidor infinito.

Validacao:

```powershell
python -m unittest tests.test_chat_event_contract tests.test_artifact_contract
```

## Fase 1: ArtifactService

Objetivo: anexar arquivo existente do Workspace a uma mensagem sem envolver LLM.

Criar:

- `src/core/artifacts.py`;
- tabela `message_artifacts`;
- download autenticado;
- `ArtifactCard` no frontend.

Testes:

- usuario A nao baixa artifact de B;
- path traversal falha;
- arquivo inexistente falha;
- MIME e checksum sao calculados no backend;
- Workspace permanece fora do RAG;
- history reload restaura o cartao.

## Fase 2: tool `attach_workspace_file`

Objetivo: permitir que o modelo entregue arquivo existente na conversa.

Regras:

- tool recebe path relativo;
- backend injeta contexto imutavel;
- somente leitura;
- arquivo e associado a mensagem em andamento;
- evento `artifact.attached` aparece antes do final;
- nenhuma URL externa e aceita.

## Fase 3: ChatJobService

Objetivo: criar Job persistente sem mudar ainda o streaming do frontend.

Criar:

- tabelas de Job e eventos;
- `ChatJobService`;
- placeholder de mensagem antes do provider;
- status terminal;
- reconciliacao apos restart;
- polling temporario apenas como fallback.

## Fase 4: eventos normalizados

Objetivo: adapters produzirem `reasoning.delta`, `text.delta`, tools e usage.

Migrar um provider por vez.

O fluxo WebSocket atual pode consumir o mesmo EventStore antes da criacao do SSE.

## Fase 5: SSE reanexavel

Criar:

```text
GET  /api/v1/chat/jobs/{id}
GET  /api/v1/chat/jobs/{id}/events
POST /api/v1/chat/jobs/{id}/cancel
```

Testes:

- reconectar com `Last-Event-ID` nao duplica texto;
- Job de A retorna 404 para B;
- cancelar produz evento terminal;
- fechar cliente nao cancela Job;
- restart preserva texto parcial.

## Fase 6: TTS final seguro

Antes do TTS incremental:

- proxy backend;
- voice por usuario;
- botao ouvir/parar;
- reasoning e codigo excluidos;
- chave TTS fora do frontend.

## Fase 7: TTS incremental

- segmentador incremental;
- prefetch 2;
- fila ordenada;
- offset falado;
- cancelamento;
- destaque visual do segmento atual;
- persistencia minima para reconexao.

## Fase 8: Live por STT do navegador

- state machine separada;
- timer configuravel;
- envio pelo mesmo ChatJobService;
- TTS incremental;
- barge-in;
- filtro de eco;
- desligado por padrao.

## Fase 9: Gemini Live opcional

Implementar somente depois do Live comum estar estavel.

- adapter WebSocket dedicado;
- audio PCM;
- transcricao;
- tool context imutavel;
- artifacts de tool;
- cancelamento;
- compartilhamento de tela opcional.

## Fase 10: quotas, retencao e observabilidade

- tamanho maximo por artifact;
- quota total por usuario;
- expiracao de Jobs;
- limpeza de audio temporario;
- metricas de primeiro delta;
- metricas de primeiro audio;
- Jobs falhos por provider;
- tracing por `job_id`.

---

# 13. Regras anti-travamento

- Uma fase altera poucos arquivos.
- Um provider por vez.
- Artifact antes de Job.
- Job antes de SSE reanexavel.
- TTS final antes de TTS incremental.
- Live comum antes de Gemini Live.
- Teste novo primeiro; bateria curta depois.
- Todo comando de teste recebe limite de 45 segundos.
- Nenhum teste inicia servidor permanente.
- Nenhum teste chama provider pago por padrao.
- Use fake adapter deterministico para Jobs.
- Nao executar `tests.test_auth_multiuser` enquanto permanecer historicamente lento.
- Nao copiar arquivos monoliticos dos repositorios Node.
- Nao colocar secrets no frontend.

Comandos curtos:

```powershell
python -m compileall -q src
python -m unittest tests.test_artifacts
python -m unittest tests.test_chat_jobs
python -m unittest tests.test_job_events
npm run build
git diff --check
```

---

# 14. Checklist final

## Artifacts

- [ ] O modelo consegue anexar arquivo existente do Workspace.
- [ ] Criacao confirmada pode devolver artifact na mesma resposta.
- [ ] Artifact aparece antes do texto final quando disponivel.
- [ ] Download exige autenticacao e ownership.
- [ ] Reload restaura artifacts.
- [ ] Imagens suportadas aparecem inline.
- [ ] Arquivo anexado nao entra no RAG automaticamente.

## Jobs

- [ ] Job e criado antes de chamar o provider.
- [ ] Mensagem placeholder e persistida.
- [ ] Fechar a aba nao perde resposta.
- [ ] Reconectar nao duplica deltas.
- [ ] Cancelamento interrompe provider e persistencia.
- [ ] Restart preserva parcial e marca estado correto.
- [ ] Job nunca muda de conversa ou usuario.

## Streaming

- [ ] Providers usam eventos normalizados.
- [ ] `Last-Event-ID` funciona.
- [ ] Thinking e texto final continuam separados.
- [ ] Tools, Skills e artifacts possuem eventos proprios.
- [ ] O frontend nao baixa novamente o stream inteiro a cada 250 ms.

## TTS

- [ ] Chave TTS existe somente no backend.
- [ ] TTS final pode ser parado.
- [ ] TTS incremental comeca antes de `job.completed`.
- [ ] Segmentos nao repetem texto.
- [ ] Reasoning e codigo nao sao falados.
- [ ] Barge-in limpa audio e fetches.
- [ ] `spokenUntil` evita repetir fala apos reconexao.

## Live

- [ ] Microfone inicia desligado.
- [ ] Timer de silencio e configuravel.
- [ ] STT parcial nao polui historico.
- [ ] Turno final usa o mesmo fluxo de Job.
- [ ] Eco do TTS e ignorado.
- [ ] Interrupcao volta rapidamente para escuta.
- [ ] Tracks de microfone sao encerradas ao parar.

## Seguranca

- [ ] Nenhum secret em `localStorage`.
- [ ] Nenhum `Function` ou `new Function`.
- [ ] Nenhum `bash`, `sh` ou shell livre.
- [ ] `user_id` nunca vem do body em rotas internas.
- [ ] RAG denso e sparse filtram usuario obrigatoriamente.
- [ ] Toda tool recebe contexto imutavel.
- [ ] Quotas e retencao estao configuradas.

---

# 15. Prioridade recomendada

A primeira entrega deve ser `ArtifactService`, nao TTS e nao Gemini Live.

Motivo:

1. O Workspace seguro ja existe.
2. A IA ja cria arquivos por plano confirmado.
3. Falta apenas transformar um arquivo real em parte persistente da mensagem.
4. Esse contrato sera reutilizado por Jobs, Skills, RAG, TTS e Live.
5. E uma fase pequena, testavel e com risco controlado.

Sequencia resumida:

```text
ArtifactService
  -> tool attach_workspace_file
  -> ChatJobService
  -> eventos normalizados
  -> SSE reanexavel e cancelamento
  -> TTS final seguro
  -> TTS incremental
  -> Live comum
  -> Gemini Live opcional
```

---

# 16. Conclusao

Os repositorios relacionados possuem recursos valiosos, principalmente artifacts, Jobs recuperaveis, fila TTS e Gemini Live. Eles tambem mostram exatamente o que nao deve ser repetido: monolitos, secrets no navegador, codigo dinamico sem sandbox, shell permissivo, estado global de conversa e RAG sem filtro obrigatorio.

O chatbot atual ja tem a fundacao mais importante:

- autenticacao real;
- isolamento por `user_id`;
- UserSpace seguro;
- Workspace completo;
- uploads separados;
- RAG opt-in;
- Skills com permissoes;
- auditoria;
- streaming de texto e reasoning;
- persistencia de atividades.

A evolucao correta e adicionar artifacts e Jobs como recursos de primeira classe, fazer todos os providers publicarem eventos normalizados e somente depois ligar o TTS incremental e o modo Live a esse fluxo.

O principio central permanece:

```text
Workspace guarda arquivos.
Uploads guardam originais enviados.
RAG guarda indice derivado e opt-in.
Artifacts entregam arquivos na conversa.
Jobs preservam execucao e eventos.
Skills fornecem capacidades governadas.
TTS e Live consomem os mesmos eventos sem alterar ownership.
```
