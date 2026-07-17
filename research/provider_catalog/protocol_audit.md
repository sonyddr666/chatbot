# Auditoria de protocolos do catálogo models.dev

Data da auditoria: 2026-07-17  
Snapshot auditado: `data/models-dev-cache.json`  
Implementação confrontada: `src/core/llm.py`, `src/core/model_catalog.py` e `src/core/provider_manager.py`

## Resultado executivo

O snapshot contém **167 providers**, **5.690 modelos** e **25 famílias de integração (`npm`)**. Ele é um catálogo de metadados, não uma garantia de que todos os providers falam OpenAI Chat Completions nem de que todos os modelos continuam disponíveis para uma conta específica.

Hoje o produto tem um adapter HTTP realmente genérico para **OpenAI Chat Completions + SSE**, sempre com `Authorization: Bearer`. Isso cobre potencialmente os **132 providers marcados como `@ai-sdk/openai-compatible`**, mas somente quando a URL publicada é realmente compatível, a autenticação é Bearer e o modelo está liberado para a chave. Cinco desses 132 exigem configuração além de uma chave. Providers nativos Anthropic, Google, Vertex, Bedrock e Azure não estão cobertos corretamente pelo adapter genérico.

Conclusão prática: **não é tecnicamente correto prometer “colar qualquer API key e tudo funcionar” para os 167 providers**. Para chegar perto dessa experiência, a UI precisa ser orientada por schema e mostrar somente os campos realmente exigidos por cada provider. Em seguida, cada modelo deve passar por teste de disponibilidade por conta, região e data antes de aparecer como ativo no chat.

## Como os números foram obtidos

- Provider: cada chave de primeiro nível do JSON.
- Modelo: cada entrada de `provider.models`.
- Família de protocolo: o valor de `provider.npm`, que é o melhor discriminador disponível no snapshot.
- Campos obrigatórios: `provider.env`.
- Endpoint: `provider.api`. Ausência de `api` significa que o snapshot não fornece URL pronta.
- Compatibilidade atual: leitura do fluxo de despacho e dos parsers em `src/core/llm.py`; não foi inferida apenas pelo nome do provider.

## Inventário completo por família declarada

| Família no snapshot | Providers | Modelos | Providers |
|---|---:|---:|---|
| `@ai-sdk/openai-compatible` | 132 | 3.957 | stepfun-step-plan, mixlayer, ambient, claudinio, frogbot, llama, lucidquery, github-models, anyapi, abacus, nano-gpt, pioneer, crossmodel, evroc, sarvam, databricks, meganova, fireworks-ai, routing-run, crof, trustedrouter, the-grid-ai, inference, xiaomi, llmgateway, model-oracle-ai, morph, empiriolabs, nova, tencent-token-plan, zhipuai-coding-plan, clarifai, llmtr, cloudferro-sherlock, huggingface, ai-router, ebcloud, umans-ai, stepfun-ai, upstage, stepfun, stackit, lilac, nvidia, wandb, fastrouter, inception, moonshotai-cn, berget, nearai, unorouter, kenari, auriko, abliteration-ai, xiaomi-token-plan-ams, lmstudio, zeldoc, cortecs, neuralwatt, alibaba-token-plan, ollama-cloud, opencode, helicone, siliconflow, github-copilot, hpc-ai, drun, io-net, privatemode-ai, neon, blueclaw, tencent-coding-plan, thinkingmachines, nebius, siliconflow-cn, moark, qiniu-ai, opencode-go, umans-ai-coding-plan, digitalocean, kuae-cloud-coding-plan, requesty, zai-coding-plan, cloudflare-workers-ai, atomic-chat, alibaba-token-plan-cn, sakana, xpersona, ovhcloud, zai, vultr, dinference, synthetic, gmicloud, xiaomi-token-plan-cn, kilo, scaleway, tencent-tokenhub, zenifra, moonshotai, submodel, regolo-ai, lynkr, snowflake-cortex, jiekou, baseten, 302ai, alibaba, modelscope, alibaba-coding-plan-cn, tinfoil, daoxe, bailing, alibaba-coding-plan, orcarouter, qihang-ai, deepseek, longcat, novita-ai, zhipuai, friendli, inferx, poe, chutes, wafer.ai, xiaomi-token-plan-sgp, alibaba-cn, iflowcn, zenmux, poolside, stepfun-ai-step-plan, inceptron |
| `@ai-sdk/anthropic` | 8 | 57 | kimi-for-coding, freemodel, subconscious, minimax-coding-plan, minimax-cn-coding-plan, anthropic, minimax, minimax-cn |
| `@ai-sdk/openai` | 4 | 92 | meta, perplexity-agent, vivgrid, openai |
| `@ai-sdk/azure` | 2 | 212 | azure-cognitive-services, azure |
| `@ai-sdk/xai` | 1 | 9 | xai |
| `@ai-sdk/mistral` | 1 | 30 | mistral |
| `@ai-sdk/google-vertex` | 1 | 39 | google-vertex |
| `@aihubmix/ai-sdk-provider` | 1 | 66 | aihubmix |
| `@ai-sdk/amazon-bedrock` | 1 | 110 | amazon-bedrock |
| `gitlab-ai-provider` | 1 | 22 | gitlab |
| `@ai-sdk/cohere` | 1 | 14 | cohere |
| `venice-ai-sdk-provider` | 1 | 83 | venice |
| `merge-gateway-ai-sdk-provider` | 1 | 93 | merge-gateway |
| `@ai-sdk/cerebras` | 1 | 3 | cerebras |
| `@jerome-benoit/sap-ai-provider-v2` | 1 | 42 | sap-ai-core |
| `@ai-sdk/perplexity` | 1 | 4 | perplexity |
| `@ai-sdk/vercel` | 1 | 3 | v0 |
| `@ai-sdk/deepinfra` | 1 | 40 | deepinfra |
| `@openrouter/ai-sdk-provider` | 1 | 344 | openrouter |
| `@ai-sdk/togetherai` | 1 | 32 | togetherai |
| `@ai-sdk/gateway` | 1 | 306 | vercel |
| `ai-gateway-provider` | 1 | 82 | cloudflare-ai-gateway |
| `@ai-sdk/google-vertex/anthropic` | 1 | 12 | google-vertex-anthropic |
| `@ai-sdk/google` | 1 | 23 | google |
| `@ai-sdk/groq` | 1 | 15 | groq |

Todos os 167 providers aparecem exatamente uma vez nessa tabela.

## Matriz por protocolo real e suporte atual

| Protocolo / integração | Providers | Exigência real | Situação em `llm.py` |
|---|---|---|---|
| OpenAI Chat Completions compatível | Os 132 de `@ai-sdk/openai-compatible`; também vários SDKs especializados podem oferecer uma rota OpenAI | URL, modelo e normalmente token Bearer; alguns exigem host/account | **Suportado com ressalvas** pelo adapter `generate_openai_compatible_stream`. Só entende SSE/JSON no formato OpenAI e só monta `Authorization: Bearer`. |
| OpenAI oficial / gateways OpenAI | openai, meta, perplexity-agent, vivgrid; aihubmix; em tese xai, mistral, cerebras, groq, deepinfra, togetherai, openrouter e outros que exponham rota compatível | Geralmente API key Bearer e endpoint conhecido | **Wire-capable**, mas vários não têm `api` no snapshot e não ficam prontos pelo quick setup. OpenAI oficial funciona por configuração built-in. AIHubMix tem override local. |
| Anthropic Messages | kimi-for-coding, freemodel, subconscious, minimax-coding-plan, minimax-cn-coding-plan, anthropic, minimax, minimax-cn | Header/chave e corpo Anthropic, incluindo versão; endpoint `/messages` | **Não suportado corretamente para providers configurados**. `api_format=anthropic_messages` cai em `get_llm()`, mas, havendo `model_id` e `base_url`, o código cria `ChatOpenAI`, não `ChatAnthropic`. |
| Google Gemini nativo | google | `x-goog-api-key`; payload `contents`; rota `models/{model}:generateContent` ou nova Interactions API | **Não suportado**. Não há serializer/parser Gemini nem header `x-goog-api-key`. |
| Google Vertex Gemini | google-vertex | Project, location e ADC/service account ou token; protocolo Vertex | **Não suportado**. Não há aquisição/refresh de credencial Google nem adapter Vertex. |
| Google Vertex Anthropic | google-vertex-anthropic | Project, location e ADC/service account; rota e envelope de partner models | **Não suportado**. Não é equivalente ao endpoint Anthropic público. |
| Amazon Bedrock ConverseStream | amazon-bedrock | Região e credenciais AWS ou bearer; assinatura/SDK; event stream; model ID ou inference profile | **Não suportado**. Não há SigV4/SDK Bedrock nem parser AWS event stream. |
| Azure OpenAI / Cognitive Services | azure, azure-cognitive-services | Resource/endpoint, deployment name, chave no header `api-key` ou Entra token; em rotas antigas, `api-version` | **Não suportado pelo adapter atual**. Ele envia Bearer e trata o model ID como catálogo, não deployment. |
| Cloudflare Workers AI OpenAI-compatible | cloudflare-workers-ai | API token **e Account ID**; endpoint contém a conta | **Parcialmente suportado**. Existe descoberta de conta e adapter OpenAI. Ainda depende de permissão do token e de haver uma única conta ou escolha explícita. |
| Cloudflare AI Gateway | cloudflare-ai-gateway | API token, Account ID e Gateway ID; escolha de protocolo/rota | **Não suportado como entrada pronta do catálogo**. O snapshot não fornece uma URL única e o schema atual não guarda os três campos de modo tipado. |
| OAuth/account pool interno | codex-chatgpt, antigravity, grok-oauth (são built-ins locais, não entradas equivalentes do snapshot) | Login OAuth, refresh token, conta e protocolos próprios | **Suportado por adapters dedicados** (`codex_client`, `antigravity_client`, `grok_client`). Não deve ser transformado em formulário de API key. |
| SDK/protocolo custom sem endpoint publicado | gitlab, sap-ai-core, v0, vercel, merge-gateway e outros especializados sem `api` | Varia por provider; pode incluir service key JSON, token de sessão, deployment ou gateway | **Não suportado automaticamente**. Marcar como `chat_completions` não cria compatibilidade. |

Referências primárias que confirmam as diferenças de protocolo:

- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages)
- [Gemini generateContent e autenticação `x-goog-api-key`](https://ai.google.dev/api/generate-content)
- [Vertex AI: project, location e Application Default Credentials](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/quickstart)
- [Amazon Bedrock ConverseStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStream.html)
- [Azure OpenAI: deployment, `api-key` e versionamento](https://learn.microsoft.com/en-us/azure/foundry/openai/reference)
- [Cloudflare Workers AI: API token e Account ID](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)
- [Cloudflare AI Gateway: rotas OpenAI, Responses e Anthropic](https://developers.cloudflare.com/ai-gateway/usage/rest-api/)
- [Databricks Foundation Model APIs e diferenças em relação ao formato OpenAI](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/api-reference)

## Providers que não são “somente API key”

O campo `env` do próprio snapshot demonstra que **12 providers** declaram mais de um valor de configuração. Os 155 restantes declaram um único env, mas isso não garante que ele seja uma API key comum: pode ser service key, host, PAT ou token OAuth.

| Provider | Campos declarados | Motivo para formulário específico |
|---|---|---|
| databricks | `DATABRICKS_HOST`, `DATABRICKS_TOKEN` | A URL depende do workspace/host. |
| google-vertex | `GOOGLE_VERTEX_PROJECT`, `GOOGLE_VERTEX_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS` | Project, região e credencial Google/ADC. |
| amazon-bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_BEARER_TOKEN_BEDROCK` | Credenciais alternativas, região e autenticação AWS. Access key + secret devem ser tratados como par; bearer é alternativa, não quarto campo cumulativo. |
| azure-cognitive-services | `AZURE_COGNITIVE_SERVICES_RESOURCE_NAME`, `AZURE_COGNITIVE_SERVICES_API_KEY` | Endpoint deriva do recurso; modelos são deployments. |
| azure | `AZURE_RESOURCE_NAME`, `AZURE_API_KEY` | Endpoint deriva do recurso; modelos são deployments. |
| privatemode-ai | `PRIVATEMODE_API_KEY`, `PRIVATEMODE_ENDPOINT` | Endpoint é instalação específica; o `localhost` do catálogo não serve dentro de qualquer Docker. |
| neon | `NEON_AI_GATEWAY_BASE_URL`, `NEON_AI_GATEWAY_TOKEN` | Gateway é específico do usuário/projeto. |
| cloudflare-workers-ai | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_KEY` | Account ID faz parte da URL. |
| snowflake-cortex | `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_CORTEX_PAT` | Account locator faz parte do hostname. |
| cloudflare-ai-gateway | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_GATEWAY_ID` | Conta e gateway fazem parte do roteamento. |
| google-vertex-anthropic | `GOOGLE_VERTEX_PROJECT`, `GOOGLE_VERTEX_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS` | Mesmo controle de plano do Vertex, com adapter Anthropic parceiro. |
| google | `GOOGLE_API_KEY`, `GOOGLE_GENERATIVE_AI_API_KEY`, `GEMINI_API_KEY` | São aliases/alternativas para a mesma credencial, não três chaves obrigatórias. O protocolo continua sendo Gemini nativo. |

Outros casos de um único campo que **não equivalem a “cole uma API key Bearer”**:

- `sap-ai-core`: `AICORE_SERVICE_KEY` costuma ser um objeto/service binding, não uma chave simples.
- `github-models` e `github-copilot`: `GITHUB_TOKEN` é token GitHub; escopos e, no caso de Copilot, fluxo/entitlement precisam ser validados.
- `gitlab`: `GITLAB_TOKEN` é token da conta GitLab e o provider usa integração própria.
- `lmstudio`, `atomic-chat` e `lynkr`: apontam para loopback. Em Docker, `127.0.0.1` é o próprio container, não a máquina do usuário; host/porta precisam ser configuráveis.
- `vercel`, `v0`, `merge-gateway`, `venice` e outros packages especializados: o snapshot não publica `api`, portanto a URL/protocolo não pode ser inventada a partir do nome do pacote.

## As 23 entradas sem endpoint pronto após o override do AIHubMix

O snapshot não contém `api` para 24 providers. O código corrige apenas AIHubMix com `https://aihubmix.com/v1`; restam **23** sem endpoint pronto:

| Provider | Família | Configuração declarada |
|---|---|---|
| xai | `@ai-sdk/xai` | `XAI_API_KEY` |
| mistral | `@ai-sdk/mistral` | `MISTRAL_API_KEY` |
| google-vertex | `@ai-sdk/google-vertex` | project + location + credentials |
| amazon-bedrock | `@ai-sdk/amazon-bedrock` | AWS credentials + region / bearer alternative |
| gitlab | `gitlab-ai-provider` | `GITLAB_TOKEN` |
| cohere | `@ai-sdk/cohere` | `COHERE_API_KEY` |
| venice | `venice-ai-sdk-provider` | `VENICE_API_KEY` |
| merge-gateway | `merge-gateway-ai-sdk-provider` | `MERGE_GATEWAY_API_KEY` |
| azure-cognitive-services | `@ai-sdk/azure` | resource name + key |
| cerebras | `@ai-sdk/cerebras` | `CEREBRAS_API_KEY` |
| azure | `@ai-sdk/azure` | resource name + key |
| sap-ai-core | custom SAP | `AICORE_SERVICE_KEY` |
| perplexity | `@ai-sdk/perplexity` | `PERPLEXITY_API_KEY` |
| v0 | `@ai-sdk/vercel` | `V0_API_KEY` |
| anthropic | `@ai-sdk/anthropic` | `ANTHROPIC_API_KEY` |
| deepinfra | `@ai-sdk/deepinfra` | `DEEPINFRA_API_KEY` |
| togetherai | `@ai-sdk/togetherai` | `TOGETHER_API_KEY` |
| vercel | `@ai-sdk/gateway` | `AI_GATEWAY_API_KEY` |
| cloudflare-ai-gateway | `ai-gateway-provider` | token + account + gateway |
| google-vertex-anthropic | Vertex Anthropic | project + location + credentials |
| google | `@ai-sdk/google` | uma das chaves Gemini/Google |
| openai | `@ai-sdk/openai` | `OPENAI_API_KEY` (já existe como built-in local) |
| groq | `@ai-sdk/groq` | `GROQ_API_KEY` |

Alguns desses providers oferecem também endpoints OpenAI-compatible oficiais. Eles podem ser conectados ao adapter genérico depois que endpoint, autenticação, versão e limitações forem registrados e testados. Isso não torna automaticamente correto ignorar o `npm` nativo nem permite assumir suporte a todas as modalidades listadas.

## Falhas estruturais encontradas no código atual

1. **Classificação excessivamente ampla.** `model_catalog.py` transforma tudo que não contém `anthropic` no nome do package em `chat_completions`. Google, Bedrock, Azure e packages custom viram OpenAI por padrão, embora não tenham o mesmo wire protocol.
2. **Anthropic configurado usa cliente OpenAI.** Em `get_llm()`, qualquer config com `model_id` e `base_url` retorna `ChatOpenAI` antes do fallback Anthropic. O `api_format=anthropic_messages` não seleciona um adapter Anthropic.
3. **Autenticação fixa.** O adapter genérico só envia `Authorization: Bearer`; não suporta `x-api-key`, `anthropic-version`, `x-goog-api-key`, Azure `api-key`, AWS SigV4 nem headers específicos.
4. **Streaming presumido.** O parser presume SSE estilo OpenAI. Bedrock usa event stream; Gemini/Anthropic têm eventos e envelopes diferentes; alguns gateways retornam JSONL ou SSE com formatos próprios.
5. **`temperature: 0.7` enviado sempre.** Há modelos no snapshot com `temperature: false`. Isso pode causar HTTP 400 mesmo com provider, endpoint e model ID corretos.
6. **Capabilities não são contrato de transporte.** `attachment`, `reasoning`, `tool_call` e modalidades do models.dev dizem o que o modelo pode fazer em algum contexto, não que o adapter atual saiba serializar esses recursos naquele provider.
7. **ID de catálogo não garante disponibilidade.** O erro Kenari `model_not_found` é exemplo esperado: catálogo global e conta real podem divergir por rollout, região, plano, aliases ou remoção.
8. **Loopback em Docker.** URLs `127.0.0.1` do catálogo são inválidas para acessar um serviço na máquina host a partir do container, salvo rede/configuração específica.
9. **Ausência de versão e origem de verificação.** Não há `verified_at`, versão de docs, resultado do teste ou validade por modelo/conta. Um endpoint correto hoje pode mudar amanhã.

## Schema proposto

O schema deve separar **metadados globais do provider**, **credenciais/configuração da conta** e **estado verificado de cada modelo**.

```json
{
  "provider_id": "azure",
  "display_name": "Azure OpenAI",
  "catalog_source": "models.dev",
  "protocol": "azure_openai_v1",
  "adapter": "azure_openai",
  "base_url_template": "https://{resource_name}.openai.azure.com/openai/v1",
  "endpoint_template": "/chat/completions",
  "auth": {
    "type": "header",
    "header": "api-key",
    "prefix": "",
    "secret_field": "api_key",
    "alternatives": ["entra_id"]
  },
  "config_fields": [
    {"id": "resource_name", "required": true, "secret": false},
    {"id": "api_key", "required": true, "secret": true}
  ],
  "model_addressing": "deployment_name",
  "stream": {"transport": "sse", "parser": "openai"},
  "docs_url": "https://learn.microsoft.com/en-us/azure/foundry/openai/reference",
  "verification": {
    "status": "documented_unverified",
    "verified_at": null,
    "verified_against": null
  }
}
```

Campos recomendados no provider:

- `protocol`: enum explícito, por exemplo `openai_chat_completions`, `openai_responses`, `anthropic_messages`, `gemini_generate_content`, `vertex_gemini`, `vertex_anthropic`, `bedrock_converse`, `azure_openai_v1`, `cloudflare_workers_openai`, `oauth_custom`.
- `adapter`: implementação que serializa request e interpreta stream; nunca deduzir apenas pelo npm.
- `base_url_template` e `endpoint_template`: separados para impedir `/chat/completions/chat/completions` e permitir placeholders validados.
- `auth`: tipo, header, prefixo, alternativa OAuth/SigV4 e estratégia de refresh.
- `config_fields`: lista tipada com `required`, `secret`, validação, placeholder, ajuda e possibilidade de descoberta.
- `model_addressing`: `catalog_id`, `provider_id`, `deployment_name`, `endpoint_id`, `arn` ou `inference_profile`.
- `stream.transport` e `stream.parser`: SSE OpenAI, SSE Anthropic, Gemini, AWS event stream, JSONL etc.
- `request_policy`: suporte/remoção de `temperature`, reasoning, tools e multimodal por modelo.
- `docs_url`, `api_key_url`, `source_url`, `source_checked_at` e `source_hash/version`.
- `setup_mode`: `api_key_only`, `multi_field`, `oauth`, `service_account`, `local_endpoint` ou `unsupported`.

Estado recomendado por modelo e por conta:

```json
{
  "catalog_model_id": "deepseek-v4-pro:free",
  "provider_model_id": "deepseek-v4-pro:free",
  "enabled": false,
  "availability": "failed",
  "last_tested_at": "2026-07-17T18:00:00Z",
  "last_test": {
    "phase": "chat_stream",
    "http_status": 400,
    "provider_code": "model_not_found",
    "latency_ms": 412,
    "received_content": false
  }
}
```

Estados seguros: `catalog_only`, `untested`, `testing`, `verified`, `degraded`, `failed`, `removed`. Apenas `verified` deveria ser habilitado automaticamente no seletor do chat; `failed` deve permanecer visível na aba Provider para reteste manual, com o erro preservado.

## Sequência recomendada de implementação

1. Parar de classificar package desconhecido como Chat Completions; usar `unsupported` até haver adapter ou endpoint OpenAI oficialmente documentado.
2. Implementar adapters nativos em ordem de alcance: Anthropic Messages, Gemini, Azure, Vertex, Bedrock.
3. Introduzir auth/header configurável e os schemas de campos antes de promover providers “somente chave”.
4. Importar endpoint e docs como dados versionados, com teste de construção da URL e teste de autenticação.
5. Executar teste por modelo usando a conta real: listar modelos quando a API permitir e depois fazer streaming mínimo. Não habilitar modelos apenas porque aparecem no models.dev.
6. Registrar resultado, latência, primeiro token, conteúdo final e erro normalizado. Retestar sob comando do administrador ou quando o catálogo mudar.
7. No chat, consumir somente o cache local de modelos `verified`; sincronização e testes permanecem na aba Provider.

## Limite de garantia

Mesmo com todos os adapters corretos, não existe garantia permanente de 100% para todos os modelos: disponibilidade depende de conta, saldo, região, plano, allowlist, rate limit e mudanças do provider. A garantia honesta que o sistema pode oferecer é: **endpoint e protocolo documentados, configuração validada, modelo testado com aquela conta e falha preservada/retestável**.
