# Plano futuro: Context Files e Skills conversacionais

> Status: pesquisa e planejamento somente. Nao implementar nesta etapa.
>
> Data da pesquisa: 2026-07-10.

## Objetivo

Evoluir o chatbot para que ele:

- carregue instrucoes persistentes sem inflar todo prompt;
- descubra contexto conforme entra em uma pasta, arquivo ou tarefa;
- crie e melhore Skills por conversa;
- use Skills apenas quando forem relevantes;
- nunca afirme que executou uma acao sem evento real do backend;
- mantenha isolamento completo entre usuarios;
- exija revisao humana antes de alterar contexto ou Skills.

Este plano se inspira em dois recursos do Hermes Agent:

- [Context Files](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files)
- [Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)

## Conclusao da pesquisa

Context Files e Skills nao sao alternativas. Eles devem coexistir:

```txt
Context Files = fatos, regras e convencoes que orientam o agente.
Skills        = procedimentos e capacidades carregados quando necessarios.
Memory/RAG    = conhecimento recuperavel e historico factual.
Tools         = operacoes reais executadas pelo backend.
```

Aplicacao no projeto:

- Context Files resolvem instrucoes persistentes e contexto por pasta.
- Skills resolvem procedimentos como pesquisa, exportacao, organizacao e automacao.
- RAG continua sendo opt-in para conhecimento semantico.
- Workspace continua sendo armazenamento de arquivos do usuario.
- Nenhum desses recursos substitui uma Tool real para criar ou editar arquivos.

O problema atual de frases como `pode salvar no work?` nao deve ser resolvido apenas com
prompt. A arquitetura futura precisa de intencao estruturada e chamada de Tool, evitando
detectores frageis baseados em poucas palavras exatas.

## O que aproveitar do Hermes

### Context Files

O Hermes:

- carrega um arquivo de contexto principal no inicio;
- descobre arquivos de subdiretorios progressivamente;
- evita carregar tudo no system prompt;
- escaneia prompt injection antes da injecao;
- limita e trunca arquivos grandes;
- separa personalidade global de instrucoes do projeto.

Adotar no chatbot:

- contexto global da aplicacao;
- contexto pessoal do usuario;
- contexto progressivo do Workspace;
- limite por arquivo e limite total por turno;
- scanner de seguranca antes de qualquer injecao;
- cache por checksum e por sessao.

### Skills

O Hermes:

- usa `SKILL.md` como documento principal;
- lista apenas nome, descricao e categoria inicialmente;
- carrega a Skill completa somente quando necessaria;
- permite referencias, templates, scripts e assets;
- cria Skills a partir de URL, pasta, notas ou conversa;
- suporta criar, corrigir, substituir e excluir Skills;
- pode exigir aprovacao para toda escrita;
- registra origem, atualizacoes e auditoria de seguranca.

Adotar no chatbot:

- Skill por usuario em formato portavel;
- indice leve no prompt;
- carregamento progressivo;
- criacao por conversa com plano e diff;
- aprovacao obrigatoria por padrao;
- permissoes de rede, RAG, Workspace e executores declaradas;
- auditoria, versoes e rollback.

Nao adotar diretamente:

- escrita livre de Skills sem aprovacao;
- shell arbitrario dentro de Skills;
- confiar que texto de `SKILL.md` equivale a permissao;
- usar diretorio externo gravavel como fronteira de seguranca;
- carregar conteudo vindo da internet sem scanner e procedencia.

## Arquitetura alvo

```txt
Mensagem do usuario
        |
        v
Intent Router estruturado
  resposta | contexto | skill | tool | workspace
        |
        +--> ContextFileService
        |      indice leve
        |      descoberta progressiva
        |      scanner + limites
        |
        +--> SkillCatalogService
        |      lista metadados
        |      seleciona candidatas
        |      carrega SKILL.md sob demanda
        |
        +--> SkillExecutionService
        |      valida permissoes
        |      chama executor registrado
        |      emite eventos reais
        |
        +--> WorkspacePlanService
               plano + diff + confirmacao
               apply atomico + auditoria
```

Regra central:

```txt
O modelo propoe.
O backend valida e executa.
O frontend comprova.
O banco registra.
```

## Estrutura futura do UserSpace

```txt
data/users/{user_id}/
  profile/
    onboarding.md
    context/
      USER.md
      PREFERENCES.md
  workspace/
    AGENTS.md
    projetos/
      projeto-a/
        AGENTS.md
  uploads/
  rag/
  skills/
    user/
      perplexo-research/
        SKILL.md
        references/
        templates/
        assets/
    pending/
      {change_id}.json
    versions/
      {skill_slug}/{version}/
    audit/
```

O diretorio `scripts/` nao deve ser habilitado na primeira versao. Quando for adicionado,
deve usar executores permitidos e isolados, nunca shell livre.

## Context Files propostos

### Camadas

1. `APP_CONTEXT.md`: arquitetura e regras globais mantidas pelo projeto.
2. `USER.md`: perfil estavel do usuario vindo do onboarding e preferencias aprovadas.
3. `AGENTS.md`: contexto da raiz do Workspace do usuario.
4. `AGENTS.md` aninhado: regras especificas de uma pasta ou projeto.
5. contexto temporario: RAG, pesquisa e resultados de Tools do turno atual.

### Prioridade

```txt
seguranca da aplicacao
  > regras globais
  > regras do usuario aprovadas
  > contexto da raiz do Workspace
  > contexto da subpasta mais proxima
  > pedido atual do usuario
```

Context Files nunca podem:

- conceder permissoes de Tool;
- revelar secrets;
- desativar confirmacoes;
- substituir regras de isolamento;
- autorizar shell ou rede;
- afirmar que uma operacao ocorreu.

### Descoberta progressiva

Na abertura da conversa:

- carregar somente metadados e contexto pessoal curto;
- carregar o contexto da raiz apenas quando o Workspace estiver envolvido.

Ao acessar `workspace/projetos/app/src/main.py`:

- verificar `workspace/AGENTS.md`;
- verificar `workspace/projetos/AGENTS.md`;
- verificar `workspace/projetos/app/AGENTS.md`;
- injetar somente arquivos novos e relevantes;
- marcar diretorios verificados na sessao.

### Limites recomendados

- 20.000 caracteres para contexto principal.
- 8.000 caracteres para cada contexto progressivo.
- 32.000 caracteres no total por turno.
- truncamento preservando inicio e final, com aviso explicito.
- cache por `user_id + path + checksum`.

### Seguranca

Antes de injetar um Context File:

- normalizar Unicode e detectar caracteres invisiveis;
- detectar tentativas de ignorar regras anteriores;
- detectar exfiltracao de chaves e leitura de `.env`;
- detectar HTML oculto e comentarios maliciosos;
- classificar origem como `builtin`, `user`, `workspace` ou `external`;
- bloquear ou pedir confirmacao conforme o risco;
- registrar checksum, motivo e decisao na auditoria.

## Formato futuro de Skill

```yaml
---
name: perplexo-research
description: Pesquisa externa com fontes e resposta verificavel
version: 1.0.0
category: research
permissions:
  network: true
  workspace_read: false
  workspace_write: false
  rag_read: false
  rag_write: false
executor: perplexo_search
triggers:
  - pesquisa atualizada
  - buscar fontes
  - pesquisa profunda
---

# Perplexo Research

## When to Use

Use quando o usuario pedir pesquisa externa ou informacao atualizada.

## Procedure

1. Validar se a Skill esta habilitada para o usuario.
2. Executar o provider registrado no backend.
3. Preservar URLs e metadados das fontes.
4. Emitir atividade de Tool antes da resposta final.

## Pitfalls

- Nunca simular resultado de pesquisa.
- Nunca pedir a chave no chat.
- Nunca afirmar sucesso sem retorno HTTP valido.

## Verification

- SkillRun com status `completed`.
- Resultado persistido.
- Card de Skill visivel com fontes.
```

O `SKILL.md` descreve o procedimento. O campo `executor` deve apontar para um executor
registrado no backend. Texto criado pelo usuario nao pode registrar codigo executavel.

## Progressive disclosure

Nivel 0, sempre barato:

```json
{"name":"perplexo-research","description":"Pesquisa externa com fontes","category":"research"}
```

Nivel 1, quando candidata:

- frontmatter;
- secoes `When to Use`, `Procedure`, `Pitfalls` e `Verification`.

Nivel 2, durante execucao:

- referencia especifica;
- template necessario;
- configuracao nao secreta;
- permissao resolvida para o usuario.

Nunca carregar todas as Skills completas no system prompt.

## Criar uma Skill conversando

### Exemplos aceitos

```txt
Crie uma skill com esse processo que acabamos de fazer.
Aprenda a pesquisar no Perplexo e sempre trazer as fontes.
Transforme esta documentacao em uma skill.
Atualize a skill de pesquisa para usar foco academico.
```

### Fluxo correto

```txt
1. Usuario pede para aprender/criar.
2. Intent Router retorna `skill_change_request` estruturado.
3. Backend coleta apenas fontes autorizadas:
   - mensagens selecionadas;
   - URL fornecida;
   - arquivos explicitamente selecionados;
   - resultados reais de Skills/Tools.
4. SkillAuthor gera um rascunho de SKILL.md.
5. SkillValidator valida schema, tamanho, executor e permissoes.
6. SecurityScanner procura prompt injection, secrets e comandos perigosos.
7. Backend cria mudanca `pending` com diff e resumo.
8. Frontend mostra card de revisao.
9. Usuario aprova ou rejeita.
10. Aprovacao grava versao atomica e atualiza o indice.
11. Evento verde confirma o que realmente foi criado.
```

### O que nao fazer

- nao detectar somente pela palavra `skill`;
- nao deixar o modelo escrever diretamente no disco;
- nao criar executor novo a partir de texto da conversa;
- nao incluir todo historico sem selecao ou limite;
- nao copiar secrets presentes em mensagens;
- nao habilitar automaticamente uma Skill recem-criada;
- nao permitir que uma Skill altere a propria permissao.

## Intent Router estruturado

Substituir gradualmente detectores por substring por uma saida validada:

```json
{
  "intent": "skill_change_request",
  "action": "create",
  "target": "perplexo-research",
  "references": ["current_conversation", "https://docs.example.com"],
  "confidence": 0.94,
  "requires_confirmation": true
}
```

Intencoes iniciais:

- `answer_only`
- `research_request`
- `workspace_change_request`
- `workspace_reference_followup`
- `context_file_change_request`
- `skill_run_request`
- `skill_change_request`
- `rag_ingest_request`

O roteador deve combinar:

1. regras deterministicas para comandos explicitos;
2. classificacao estruturada para linguagem natural;
3. estado recente de planos e Tools;
4. fallback seguro para pergunta de confirmacao curta.

## Modelo de dados futuro

### SkillDefinition

```txt
id
owner_user_id nullable
slug
name
description
category
version
source_type
source_uri
trust_level
executor
content_path
checksum
status
created_at
updated_at
```

### SkillChange

```txt
id
user_id
skill_id nullable
action
status: pending | approved | rejected | applied | failed
before_checksum
after_checksum
diff
risk_report_json
created_at
resolved_at
```

### ContextFileRecord

```txt
id
user_id nullable
path
scope
source_type
checksum
scan_status
scan_report_json
last_loaded_at
```

## APIs futuras

```txt
GET    /api/v1/context-files
GET    /api/v1/context-files/{id}
POST   /api/v1/context-files/scan
POST   /api/v1/context-files/changes
POST   /api/v1/context-files/changes/{id}/approve
DELETE /api/v1/context-files/changes/{id}

GET    /api/v1/skills/catalog
GET    /api/v1/skills/{slug}
POST   /api/v1/skills/author
POST   /api/v1/skills/changes/{id}/approve
DELETE /api/v1/skills/changes/{id}
POST   /api/v1/skills/{slug}/run
GET    /api/v1/skills/{slug}/versions
POST   /api/v1/skills/{slug}/rollback
```

Todas exigem autenticacao. Toda consulta filtra por proprietario e escopo.

## Interface futura

### Contexto

- aba `Contexto` dentro das configuracoes;
- lista de arquivos ativos e onde foram descobertos;
- indicador de tamanho e truncamento;
- status do scanner;
- botao para desabilitar um contexto sem excluir;
- visualizacao do que foi carregado no turno atual.

### Skills

- catalogo leve por usuario;
- botao `Criar conversando`;
- editor de `SKILL.md` com preview;
- permissoes visiveis;
- executor visivel e nao editavel por texto livre;
- diff antes de criar ou atualizar;
- versoes e rollback;
- atividade ao vivo: selecionada, carregada, executando, concluida ou falhou.

### Chat

Cards distintos:

```txt
Contexto carregado
Skill selecionada
Tool executada
Mudanca aguardando aprovacao
Mudanca aplicada
```

Isso impede que o usuario confunda texto gerado pelo modelo com acao real.

## Ordem real de implementacao

### Fase 0: contratos e scanner

- definir schemas de Context File, Skill e mudanca pendente;
- criar scanner de texto reutilizavel;
- adicionar limites e checksums;
- nao alterar o chat ainda.

Pronto quando:

- scanner bloqueia injecao, secrets e caracteres invisiveis;
- schemas rejeitam permissao ou executor desconhecido.

### Fase 1: ContextFileService

- carregar `USER.md` aprovado;
- indexar contexto da raiz do Workspace;
- cachear por checksum;
- registrar o que foi carregado.

Pronto quando:

- dois usuarios nunca recebem contexto um do outro;
- arquivo bloqueado nunca entra no prompt.

### Fase 2: descoberta progressiva

- observar caminhos usados por Workspace e Tools;
- caminhar pelos ancestrais virtuais;
- carregar contexto apenas uma vez por sessao/checksum;
- mostrar evento de contexto no frontend.

### Fase 3: Skill em arquivo e catalogo leve

- materializar Skills atuais como definicoes versionadas;
- manter compatibilidade com SkillRegistry existente;
- carregar apenas metadados no inicio;
- carregar conteudo completo sob demanda.

### Fase 4: SkillAuthor com aprovacao

- criar Skill por texto, URL ou conversa selecionada;
- gerar diff pendente;
- validar e escanear;
- aprovar, rejeitar e persistir versao.

### Fase 5: Intent Router estruturado

- adicionar intencoes tipadas;
- usar estado recente para referencias como `ele` e `isso`;
- manter regras deterministicas como fallback;
- registrar decisao e confianca para depuracao.

### Fase 6: UI e observabilidade

- catalogo, editor, diff e historico;
- cards de contexto e Skill no chat;
- metricas de selecao incorreta, falhas e tempo;
- painel de auditoria por usuario.

### Fase 7: fontes externas e bundles

- instalar Skills por URL/GitHub somente apos scanner;
- registrar origem e checksum;
- suportar bundles de Skills;
- nunca executar script externo automaticamente.

## Regras anti-travamento

Cada fase deve:

1. alterar poucos arquivos;
2. incluir no maximo um servico principal novo;
3. ter teste focado antes de integracao;
4. concluir em commit separado;
5. nao iniciar servidor infinito durante teste;
6. usar timeout de ate 45 segundos;
7. manter compatibilidade com chat e Skills existentes;
8. parar a fase se o schema ou a seguranca ainda estiverem ambiguos.

## Testes essenciais

### Context Files

- isolamento por `user_id`;
- prioridade correta;
- descoberta progressiva;
- cache e invalidacao por checksum;
- truncamento com marcador;
- bloqueio de injection e secret;
- nenhum arquivo bloqueado chega ao modelo.

### Skills

- catalogo nivel 0 nao carrega corpo completo;
- Skill so carrega quando selecionada;
- executor desconhecido e rejeitado;
- permissao declarada nao supera permissao do usuario;
- criacao gera mudanca pendente;
- nada e gravado antes da aprovacao;
- aprovacao atomica cria versao;
- rollback restaura checksum anterior;
- Skill de outro usuario nunca aparece;
- Tool falha nao pode produzir card de sucesso.

### Intent Router

- `crie uma skill com isso` cria intencao de autoria;
- `pode salvar no work?` referencia o plano/arquivo recente;
- `como criar uma skill?` permanece pergunta, nao execucao;
- baixa confianca nao executa escrita;
- confirmacoes curtas usam o estado pendente correto.

## Checklist final de pronto

- [ ] Context Files globais, pessoais e de Workspace estao separados.
- [ ] Contexto progressivo funciona sem inflar o prompt inicial.
- [ ] Todo contexto passa pelo scanner.
- [ ] Skills usam formato portavel e versionado.
- [ ] Skills podem ser criadas por conversa, URL ou arquivo selecionado.
- [ ] Toda escrita de Skill exige aprovacao por padrao.
- [ ] Executor e permissao nao podem ser inventados pelo modelo.
- [ ] O chat mostra evidencias reais de carregamento e execucao.
- [ ] O Intent Router entende referencias e variacoes naturais.
- [ ] Nenhum usuario acessa contexto ou Skill de outro.
- [ ] Auditoria, versao e rollback estao funcionando.
- [ ] RAG continua opt-in e separado do Workspace.
- [ ] Testes focados concluem em menos de 45 segundos.

## Primeira tarefa recomendada

Criar apenas o contrato e o scanner, sem ligar ao chat:

```txt
ContextFileRecord
SkillDefinitionV2
SkillChange
ContextSecurityScanner
```

Essa fundacao reduz o risco das fases seguintes e evita repetir o problema atual de deixar
o modelo confundir uma resposta textual com uma acao executada.

## Fontes oficiais pesquisadas

- Hermes Agent, Context Files:
  https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files
- Hermes Agent, Skills System:
  https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
