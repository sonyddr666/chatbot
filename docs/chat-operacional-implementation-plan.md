# Plano de Implementação — Chat Operacional

> Objetivo: transformar o chat atual em um chat operacional: streaming real, thinking/status visível, persistência robusta, renderer rico, anexos inteligentes, workspace de arquivos, diffs aprováveis e hooks futuros de voz.

---

## 0. Inventário atual do projeto

Estado observado no código atual.

### Já existe

| Área | Status | Onde |
|---|---:|---|
| Streaming HTTP SSE | Parcial/funcional | `src/api/routes.py` → `/api/v1/chat/stream` |
| Streaming WebSocket | Funcional | `src/api/app.py` → `/ws` |
| Frontend recebendo chunks | Funcional | `frontend/src/lib/api.ts`, `useWebSocket.ts`, `useChatStore.ts` |
| Reasoning separado | Parcial | `src/core/llm.py`, `ChatMessage.tsx`, `ThinkingBlock.tsx` |
| Thinking colapsável | Já existe | `frontend/src/components/ThinkingBlock.tsx` |
| Markdown renderer | Já existe | `ChatMessage.tsx` com `ReactMarkdown` |
| GFM/tabelas markdown | Já existe | `remark-gfm` |
| Code highlight | Já existe | `react-syntax-highlighter` |
| Botão copiar código | Já existe | `CodeBlock` em `ChatMessage.tsx` |
| Botão regenerar | Já existe | `ChatMessageBubble` + store |
| Botão parar geração | Parcial UI | `ChatInput`/store tem `stopGeneration`, mas não cancela request real ainda |
| Persistência SQLite | Existe | `src/db/models.py`, `repository.py` |
| Histórico no frontend | Existe | `Sidebar`, `useChatStore.setSession()` |
| Metadata modelo por resposta | Implementado agora | `provider_id/model_id/model_name` nas mensagens |
| Provider/Codex pool | Existe | `account_pool.py`, `ProviderManager.tsx` |

### Ainda falta ou está incompleto

| Área | Falta |
|---|---|
| Cancelamento real | AbortController no HTTP SSE e cancelamento por conexão WebSocket |
| Salvar resposta parcial se cair | Persistir assistant parcial/interrompida |
| Eventos de progresso padronizados | `status` existe, mas não há schema forte de eventos |
| Tool calls visuais | Sem cards de ferramenta ainda |
| Message parts estruturadas | Hoje mensagem é basicamente `content` string + reasoning |
| HTML seguro | Não renderizar HTML cru sem sanitização |
| JSON/table/card viewer | Ainda não há viewer dedicado |
| Upload/anexos no chat | Upload existe para RAG/documentos, não como anexo por mensagem |
| Capability router multimodal | Não existe tabela real por modelo/provider |
| Workspace/diff/patch | Não existe ainda |
| TTS/STT integrado ao fluxo do chat | Não integrado aqui ainda |

---

## 1. Decisões rápidas pendentes

Antes de implementar as próximas fases, responder estas perguntas evita retrabalho.

### Perguntas mais rápidas de decidir

1. **Streaming padrão deve ser WebSocket ou HTTP SSE?**
   - Hoje o app prefere WebSocket quando conectado.
   - Sugestão: manter WebSocket como principal e HTTP SSE como fallback.

2. **Quando clicar em parar, salva parcial ou descarta?**
   - Sugestão: salvar como mensagem assistant com status `interrupted`.

3. **Thinking aparece aberto ou fechado por padrão?**
   - Sugestão: fechado quando finalizado, aberto enquanto está chegando.

4. **HTML vindo do modelo deve ser renderizado?**
   - Sugestão: por padrão não. Se permitir, usar sanitização obrigatória.

5. **Anexos devem entrar primeiro só como texto extraído ou multimodal real?**
   - Sugestão: começar com extração de texto para PDF/TXT/DOCX/CSV e preview de imagem; multimodal real depois.

6. **Workspace de arquivos pode editar automaticamente ou sempre exige aprovação?**
   - Sugestão: sempre exige aprovação via diff.

7. **TTS fala resposta parcial ou só final?**
   - Sugestão: só final.

---

## 2. Arquitetura alvo

```txt
Frontend
  ChatInput
  ChatMessageStreaming
  ThinkingBlock
  MessageRenderer
  AttachmentManager
  ToolCallCards
  FileWorkspacePanel
        ↓
Backend API
  /chat/stream ou /ws
  /attachments/*
  /workspace/*
  /tools/*
        ↓
Core
  ChatEngine
  LLM Router
  Capability Router
  Attachment Processor
  Tool Runner
  Diff/Patch Engine
        ↓
Storage
  SQLite mensagens/conversas
  Arquivos temporários
  Vector DB/RAG
  Audit log de operações
```

Princípio central:

```txt
Provider/model gera conteúdo.
Backend normaliza eventos.
Frontend renderiza partes estruturadas.
Banco salva estado suficiente para retomar após restart.
```

---

## 3. Modelo de mensagem ideal

Hoje a mensagem é principalmente:

```json
{
  "role": "assistant",
  "content": "texto final"
}
```

Modelo alvo:

```json
{
  "id": 123,
  "role": "assistant",
  "content": "fallback markdown completo",
  "status": "completed",
  "provider_id": "codex-chatgpt",
  "provider_name": "Codex ChatGPT",
  "model_id": "gpt-5.4-mini",
  "model_name": "GPT-5.4 Mini (Codex)",
  "parts": [
    {
      "type": "markdown",
      "content": "Resumo em markdown..."
    },
    {
      "type": "code",
      "language": "python",
      "content": "print('oi')"
    },
    {
      "type": "tool_call",
      "name": "search_docs",
      "status": "completed",
      "result_summary": "3 documentos encontrados"
    }
  ],
  "reasoning": {
    "mode": "summary",
    "content": "Resumo do raciocínio quando provider permitir"
  },
  "created_at": "..."
}
```

### Status da mensagem

```txt
streaming
completed
interrupted
failed
regenerated
```

---

## 4. Eventos de streaming padronizados

Backend deve emitir eventos normalizados independentemente do provider.

### Start

```json
{
  "type": "start",
  "session_id": "default",
  "provider_id": "codex-chatgpt",
  "model_id": "gpt-5.4-mini"
}
```

### Status/progresso

```json
{
  "type": "status",
  "stage": "retrieving_context",
  "text": "Consultando base de conhecimento..."
}
```

### Reasoning summary

```json
{
  "type": "reasoning",
  "mode": "summary",
  "text": "Resumo parcial..."
}
```

### Token/content

```json
{
  "type": "content",
  "text": "Olá"
}
```

### Tool call

```json
{
  "type": "tool_call",
  "tool_call_id": "tool_123",
  "name": "read_file",
  "status": "running"
}
```

### Done

```json
{
  "type": "done",
  "message_id": 123,
  "status": "completed"
}
```

### Error

```json
{
  "type": "error",
  "message": "401 token expirado"
}
```

---

## 5. Fase 1 — Streaming robusto, parar geração e salvar parcial

### Objetivo

Fazer a experiência básica ficar sólida: resposta viva, cancelável e persistente mesmo se cair.

### Já existe

- SSE HTTP.
- WebSocket.
- Frontend renderizando chunks.
- Botão parar visual.

### Falta

1. **Cancelamento real HTTP SSE**
   - Usar `AbortController` no frontend.
   - Passar abort para `fetch`.
   - Backend detectar desconexão, parar geração quando possível.

2. **Cancelamento real WebSocket**
   - Frontend mandar:

```json
{ "type": "cancel", "session_id": "..." }
```

   - Backend manter task ativa por sessão e cancelar.

3. **Salvar parcial**
   - Ao interromper ou cair conexão:
     - salvar assistant com conteúdo acumulado;
     - `status = interrupted`;
     - manter metadata de modelo.

4. **Evitar duplicidade user/assistant**
   - Garantir que user message é salvo uma vez.
   - Garantir que assistant parcial/final atualiza a mesma mensagem, não cria várias.

### Arquivos prováveis

```txt
src/api/app.py
src/api/routes.py
src/core/chat.py
src/db/models.py
src/db/repository.py
frontend/src/lib/api.ts
frontend/src/hooks/useChatStore.ts
frontend/src/hooks/useWebSocket.ts
frontend/src/components/ChatInput.tsx
```

### Schema DB sugerido

Adicionar em `messages`:

```txt
status TEXT default 'completed'
parent_message_id INTEGER nullable
error TEXT nullable
completed_at DATETIME nullable
```

### Complexidade

Média.

### Risco

Médio, porque mexe no fluxo de streaming e persistência.

---

## 6. Fase 2 — Thinking colapsado + eventos de progresso + tool cards

### Objetivo

Dar visibilidade real do que o app está fazendo sem prometer chain-of-thought bruto.

### Modos de thinking

```txt
none
summary
synthetic_status
```

### Já existe

- `ThinkingBlock.tsx`.
- Evento `reasoning`.
- Evento `status` simples.

### Falta

1. Padronizar `thinking_mode` por provider/model.
2. Separar:
   - reasoning oficial do provider;
   - status sintético do app;
   - tool calls.
3. Criar cards visuais de tool call:

```txt
🔎 Buscando documentos...
📄 Lendo arquivo X...
🛠 Aplicando patch...
✅ Concluído
❌ Falhou
```

### Arquivos prováveis

```txt
frontend/src/components/ThinkingBlock.tsx
frontend/src/components/ChatMessage.tsx
frontend/src/components/ToolCallCard.tsx
src/core/llm.py
src/core/chat.py
src/api/app.py
src/api/routes.py
```

### Complexidade

Baixa a média.

### Risco

Baixo se for só visual/eventos.

---

## 7. Fase 3 — Renderer rico de mensagens

### Objetivo

Renderizar bem Markdown, código, tabelas, JSON, cards e futuramente HTML seguro.

### Já existe

- Markdown.
- GFM.
- Code highlight.
- Copy button.

### Falta

1. `MessageRenderer` dedicado.
2. Suporte a `message.parts`.
3. JSON viewer colapsável.
4. Tabela responsiva melhor.
5. Cards estruturados.
6. HTML sanitizado se aprovado.

### Part types iniciais

```ts
type MessagePart =
  | { type: 'markdown'; content: string }
  | { type: 'code'; language?: string; content: string }
  | { type: 'json'; data: unknown }
  | { type: 'table'; columns: string[]; rows: unknown[][] }
  | { type: 'tool_call'; name: string; status: string; data?: unknown }
  | { type: 'file'; file_id: string; name: string }
  | { type: 'image'; url: string; alt?: string }
```

### Segurança HTML

Regra recomendada:

```txt
HTML cru do modelo NÃO renderiza por padrão.
Se renderizar, passa por DOMPurify.
```

### Arquivos prováveis

```txt
frontend/src/components/MessageRenderer.tsx
frontend/src/components/JsonViewer.tsx
frontend/src/components/TableViewer.tsx
frontend/src/components/ToolCallCard.tsx
frontend/src/lib/api.ts
src/db/models.py
```

### Complexidade

Média.

### Risco

Médio se HTML entrar; baixo se ficar em markdown/json/tabela.

---

## 8. Fase 4 — Anexos + capability router

### Objetivo

Permitir arquivos/imagens no chat com comportamento correto por modelo.

### Componentes

```txt
AttachmentManager
AttachmentPreview
AttachmentProcessor
ModelCapabilityRouter
```

### Capabilities por modelo

```json
{
  "text_input": true,
  "image_input": false,
  "pdf_input": false,
  "document_input": true,
  "audio_input": false,
  "video_input": false,
  "file_search": true,
  "tools": false
}
```

### Fluxo de anexo

```txt
usuário arrasta arquivo
frontend mostra preview
backend valida MIME/tamanho
backend salva temporário
backend extrai conteúdo ou prepara multimodal
chat recebe referência do anexo
router decide como enviar ao provider
```

### Fallback text-only

```txt
Imagem → bloquear ou OCR/descrição
PDF → extrair texto
DOCX/TXT/MD/CODE → extrair texto
CSV/XLSX → converter para markdown/tabela/resumo
```

### Tabelas necessárias

```txt
attachments
- id
- session_id
- filename
- mime_type
- size
- storage_path
- extracted_text
- created_at
- expires_at
```

### Arquivos prováveis

```txt
src/api/routes.py
src/core/attachments.py
src/core/model_capabilities.py
src/db/models.py
frontend/src/components/AttachmentManager.tsx
frontend/src/components/AttachmentPreview.tsx
frontend/src/components/ChatInput.tsx
```

### Complexidade

Alta.

### Risco

Alto, por segurança, MIME, storage e diferenças entre providers.

---

## 9. Fase 5 — Workspace de arquivos + diff/patch

### Objetivo

Permitir manipular arquivos do projeto com aprovação explícita.

### Regras

```txt
IA nunca edita direto sem aprovação.
Modelo propõe diff.
Frontend mostra diff.
Usuário aprova.
Backend aplica patch.
Sistema salva snapshot/audit log.
```

### Endpoints sugeridos

```txt
GET  /api/v1/workspace/tree
GET  /api/v1/workspace/file?path=...
POST /api/v1/workspace/patch/preview
POST /api/v1/workspace/patch/apply
POST /api/v1/workspace/snapshot
POST /api/v1/workspace/rollback
```

### Segurança

```txt
bloquear path traversal
limitar root permitido
bloquear arquivos sensíveis por padrão
exigir confirmação para delete/move
logar operações
```

### Arquivos prováveis

```txt
src/core/workspace.py
src/core/patcher.py
src/api/workspace_routes.py
frontend/src/components/FileWorkspace.tsx
frontend/src/components/DiffViewer.tsx
```

### Complexidade

Alta.

### Risco

Alto.

---

## 10. Fase 6 — TTS/STT

### Objetivo

Encaixar voz no fluxo sem atrapalhar chat.

### Regras recomendadas

```txt
STT vira mensagem normal.
TTS fala só resposta final.
Thinking não vai para TTS.
Botão parar fala separado de parar geração.
Fila de fala.
Seleção de voz.
```

### Eventos

```json
{
  "type": "speech_status",
  "status": "speaking"
}
```

### Complexidade

Média.

### Risco

Baixo/médio dependendo do motor TTS/STT já existente.

---

## 11. Quick wins — mais rápidas de fazer agora

Ordem recomendada se quiser avançar sem quebrar tudo.

### 1. Melhorar botão parar geração

- HTTP: `AbortController`.
- UI marca assistant como `interrupted`.
- Backend tenta salvar parcial.

**Dificuldade:** média.  
**Impacto:** alto.

### 2. Padronizar eventos `status`

Hoje já existem status soltos. Criar schema:

```txt
retrieving_context
thinking
calling_provider
streaming
saving
completed
```

**Dificuldade:** baixa.  
**Impacto:** médio.

### 3. Mostrar badge provider/model já implementado

Já foi feito no passo anterior. Só validar visual.

**Dificuldade:** feita.  
**Impacto:** médio.

### 4. Corrigir histórico/reload

Já foi feito no passo anterior:

- reparar `messages_count`;
- reidratar memória do banco;
- carregar sessão no frontend ao abrir.

**Dificuldade:** feita.  
**Impacto:** alto.

### 5. Criar `MessageRenderer` separando do `ChatMessageBubble`

Refactor visual sem mexer no backend.

**Dificuldade:** baixa/média.  
**Impacto:** médio.

### 6. JSON viewer simples

Detectar bloco JSON ou part JSON e renderizar colapsável.

**Dificuldade:** baixa.  
**Impacto:** médio.

---

## 12. Ordem recomendada real

```txt
1. Cancelamento real + salvar parcial
2. Eventos de status padronizados
3. MessageRenderer refactor
4. JSON/table/cards
5. AttachmentManager texto/PDF simples
6. Capability router
7. Multimodal real por provider
8. Workspace files + diff
9. TTS/STT
```

---

## 13. Checklist de implementação por fase

### Fase 1 checklist

- [ ] Adicionar `status` em `messages`.
- [ ] Criar `assistant` placeholder no DB antes do stream.
- [ ] Atualizar conteúdo parcial durante stream ou no final/interrupção.
- [ ] HTTP SSE com `AbortController`.
- [ ] WebSocket com mensagem `cancel`.
- [ ] Backend cancela task ativa.
- [ ] UI mostra `interrompido`.
- [ ] Histórico preserva parcial após restart.

### Fase 2 checklist

- [ ] Criar enum de `status event`.
- [ ] Normalizar provider reasoning para `summary`.
- [ ] Separar `reasoning` de `synthetic_status`.
- [ ] Tool call card visual.
- [ ] Persistir tool events se necessário.

### Fase 3 checklist

- [ ] Criar `MessageRenderer`.
- [ ] Criar `MessagePart` no frontend.
- [ ] Adicionar `parts_json` no backend/DB.
- [ ] JSON viewer.
- [ ] Table viewer.
- [ ] Sanitização HTML se aprovado.

### Fase 4 checklist

- [ ] Tabela `attachments`.
- [ ] Upload por mensagem.
- [ ] Preview frontend.
- [ ] MIME allowlist.
- [ ] Limpeza automática.
- [ ] Extrair texto PDF/TXT/DOCX/CSV.
- [ ] Capability router por modelo.
- [ ] Fallback text-only.

### Fase 5 checklist

- [ ] Tree de arquivos.
- [ ] Read file seguro.
- [ ] Patch preview.
- [ ] Diff viewer.
- [ ] Apply patch com aprovação.
- [ ] Snapshot/rollback.
- [ ] Audit log.

### Fase 6 checklist

- [ ] STT input.
- [ ] TTS final response.
- [ ] Stop speech.
- [ ] Voice selector.
- [ ] Queue de fala.

---

## 14. Riscos principais

| Risco | Mitigação |
|---|---|
| XSS via HTML/Markdown | Não renderizar HTML cru; DOMPurify se habilitar |
| Perda de resposta parcial | Criar mensagem assistant antes do stream e atualizar status |
| Duplicação de mensagens | Usar IDs persistentes e update, não só insert |
| Provider sem reasoning oficial | Usar `synthetic_status`, não inventar chain-of-thought |
| Modelo sem multimodal | Capability router + fallback de extração |
| IA editar arquivo errado | Diff + aprovação + sandbox/path allowlist |
| Tokens/secrets vazarem | Nunca mandar token pro frontend; mascarar tudo |

---

## 15. Veredito

O projeto já tem uma base boa:

```txt
streaming existe
websocket existe
markdown existe
thinking block existe
persistência existe
provider/model por resposta começou
```

O próximo passo mais valioso é:

```txt
cancelamento real + salvar parcial + status consistente
```

Depois disso, o renderer e anexos ficam muito mais fáceis, porque a base de eventos e persistência já estará correta.
