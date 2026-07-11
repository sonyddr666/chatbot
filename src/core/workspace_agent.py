"""Confirmed AI plans for complete per-user workspace management."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import unicodedata
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from src.core.llm import generate
from src.core.patcher import apply_workspace_patch, preview_workspace_patch
from src.core.skill_permissions import can_execute_skill
from src.core.userspace import safe_user_path
from src.core.workspace import delete_path, mkdir, move_path, read_text_file, write_text_file
from src.db.repository import ConversationRepo, SkillRepo, SkillRunRepo


MAX_PLAN_ACTIONS = 20
MAX_INVENTORY_CHARS = 40000
MAX_INVENTORY_ITEMS = 300
PLANNER_TIMEOUT_SECONDS = 30
ROUTER_TIMEOUT_SECONDS = 12
PLAN_EXPIRY = timedelta(hours=1)
PLAN_ID_RE = re.compile(r"^[a-f0-9]{32}$")
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".csv", ".yaml", ".yml",
    ".toml", ".ini", ".py", ".js", ".jsx", ".ts", ".tsx", ".html",
    ".css", ".scss", ".xml", ".sql", ".sh", ".ps1",
}
SEARCH_SKILL_NAMES = {"perplexo_search", "simple_search", "search_and_answer", "web_search"}
MAX_RECENT_SEARCH_CHARS = 12000
MAX_HISTORY_EXPORT_BYTES = 950 * 1024


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _workspace_router_messages(
    user_id: int,
    message: str,
    session_id: str | None = None,
) -> list:
    recent_lines: list[str] = []
    if session_id:
        for item in ConversationRepo.get_history(session_id, limit=6, user_id=user_id):
            content = str(item.content or "").strip().replace("\x00", "")
            if len(content) > 800:
                content = content[:800] + " [truncado]"
            recent_lines.append(f"{item.role}: {content}")
    recent_context = "\n".join(recent_lines) or "[sem mensagens anteriores]"
    latest_file = _latest_applied_workspace_file(user_id) or "[nenhum arquivo recente]"
    system = """Voce classifica intencao. Nao responda ao usuario e nao execute ferramentas.
Decida pelo significado completo se a mensagem ATUAL pede uma operacao real em arquivo ou
pasta do Workspace deste aplicativo.

Escolha workspace apenas quando o usuario estiver pedindo claramente, agora, para criar,
salvar, editar, mover, renomear, organizar ou apagar um arquivo/pasta digital no Workspace.

Escolha chat para conversa, definicao de personalidade, system prompt colado, regras de
humor, exemplos, citacoes, hipoteses, objetos fisicos, explicacoes, perguntas sobre como
fazer algo ou qualquer pedido ambiguo. Palavras como criar, colocar, isso, arquivo e
workspace dentro de um texto colado nao transformam o texto em uma operacao.

Na duvida escolha chat. Retorne somente JSON estrito, sem markdown:
{"intent":"chat|workspace","confidence":0.0,"reason":"resumo curto"}"""
    human = (
        f"Ultimo arquivo realmente aplicado: {latest_file}\n\n"
        f"Conversa recente:\n{recent_context}\n\n"
        f"Mensagem ATUAL a classificar:\n{message}"
    )
    return [SystemMessage(content=system), HumanMessage(content=human)]


def workspace_request_candidate(message: str) -> bool:
    """Avoid an extra LLM call when the message cannot be a Workspace action."""
    text = str(message or "").strip().lower()
    if not text:
        return False
    if "@workspace" in text or "workspace" in text:
        return True

    action = re.search(
        r"\b(cri(?:a|ar|e)|salv(?:a|ar|e)|edit(?:a|ar|e)|mov(?:a|er|e)|"
        r"renome(?:ia|ar|ie)|organiz(?:a|ar|e)|apag(?:a|ar|ue)|exclu(?:i|ir|a)|"
        r"escrev(?:a|er|e)|atualiz(?:a|ar|e))\b",
        text,
    )
    if not action:
        return False
    target = re.search(
        r"\b(arquivo|documento|doc|pasta|diretorio|diretório|markdown|txt|json|csv|pdf|"
        r"readme|\.md|\.txt|\.json|\.csv|ele|ela|isso)\b",
        text,
    )
    return bool(target)


async def model_requests_workspace(
    user_id: int,
    message: str,
    provider_config: dict | None = None,
    session_id: str | None = None,
) -> bool:
    """Route with semantic model judgment; every failure safely becomes normal chat."""
    if not workspace_request_candidate(message):
        return False
    try:
        raw = await asyncio.wait_for(
            generate(
                _workspace_router_messages(user_id, message, session_id),
                provider_config=provider_config,
            ),
            timeout=ROUTER_TIMEOUT_SECONDS,
        )
        decision = _extract_json(raw)
        confidence = float(decision.get("confidence", 0))
        return decision.get("intent") == "workspace" and confidence >= 0.85
    except Exception:
        return False


def workspace_manager_enabled(user_id: int) -> bool:
    for skill in SkillRepo.list_for_user(user_id):
        if skill.get("name") == "workspace_manager":
            return can_execute_skill(skill, "workspace_write")
    return False


def workspace_plan_message(plan: dict) -> str:
    """Persist a hidden plan reference that the frontend can restore after reload."""
    return (
        "Preparei um plano seguro para o Workspace. "
        "Revise as operacoes e confirme para executar.\n\n"
        f"<!-- workspace-plan:{plan['id']} -->"
    )


def workspace_plan_status_context(user_id: int, limit: int = 5) -> str:
    """Expose recent real plan status so stale chat messages cannot override it."""
    folder = safe_user_path(user_id, "skills", "audit/workspace_plans")
    if not folder.is_dir():
        return ""
    plans: list[dict] = []
    for path in sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        plans.append(plan)
    if not plans:
        return ""
    lines = [
        "Estado real recente dos planos do Workspace:",
        "Use apenas se o usuario perguntar sobre essas operacoes. Nao mencione espontaneamente.",
        "O status abaixo prevalece sobre mensagens antigas; se estiver applied, nao peca nova confirmacao.",
    ]
    for plan in plans:
        lines.append(f"- {plan.get('id')}: status={plan.get('status')}; resumo={plan.get('summary', '')}")
    return "\n".join(lines)


def _latest_applied_workspace_file(user_id: int) -> str:
    """Resolve references such as 'edite ele' from the latest real applied plan."""
    folder = safe_user_path(user_id, "skills", "audit/workspace_plans")
    if not folder.is_dir():
        return ""
    paths = sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if plan.get("status") != "applied":
            continue
        for action in reversed(plan.get("actions") or []):
            if action.get("operation") != "write_file":
                continue
            relative_path = str(action.get("path") or "")
            if relative_path and safe_user_path(user_id, "workspace", relative_path).is_file():
                return relative_path
    return ""


def _conversation_export_requested(instruction: str) -> bool:
    folded = _fold(instruction)
    history_reference = re.search(
        r"\b(?:chat|chats|conversa|conversas|historico|mensagem|mensagens)\b",
        folded,
    )
    complete_reference = re.search(
        r"\b(?:todos|todas|completo|completos|completa|completas|inteiro|inteira|dados)\b",
        folded,
    )
    return bool(history_reference and complete_reference)


def _explicit_workspace_file(instruction: str) -> str:
    match = re.search(
        r"([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:md|markdown|txt|json|csv|yaml|yml))",
        instruction,
        re.IGNORECASE,
    )
    return match.group(1).replace("\\", "/") if match else ""


def _conversation_export_markdown(
    user_id: int,
    instruction: str,
    session_id: str | None = None,
) -> tuple[str, int, int]:
    folded = _fold(instruction)
    all_sessions = bool(re.search(
        r"\b(?:todos os chats|todos chats|todas as conversas|todas conversas|historico completo)\b",
        folded,
    ))
    selected_session = None if all_sessions else session_id
    conversations = ConversationRepo.export_for_user(user_id, selected_session)
    lines = [
        "# Historico completo das conversas",
        "",
        f"Exportado em: {datetime.now(timezone.utc).isoformat()}",
        f"Escopo: {'todas as conversas' if all_sessions else 'conversa atual'}",
        "",
    ]
    message_count = 0
    for conversation in conversations:
        messages = list(conversation.get("messages") or [])
        if messages and messages[-1].get("role") == "user":
            if str(messages[-1].get("content") or "").strip() == instruction.strip():
                messages.pop()
        if not messages:
            continue
        lines.extend([
            f"## {conversation.get('title') or 'Conversa sem titulo'}",
            "",
            f"- Sessao: `{conversation.get('session_id') or ''}`",
            f"- Criada em: {conversation.get('created_at') or ''}",
            f"- Atualizada em: {conversation.get('updated_at') or ''}",
            "",
        ])
        for index, message in enumerate(messages, start=1):
            message_count += 1
            role = "Usuario" if message.get("role") == "user" else "Assistente"
            lines.extend([
                f"### {index}. {role}",
                "",
                f"Data: {message.get('created_at') or ''}",
            ])
            if message.get("provider_name") or message.get("model_name"):
                lines.append(
                    f"Modelo: {message.get('provider_name') or ''} / {message.get('model_name') or ''}"
                )
            lines.extend(["", str(message.get("content") or ""), ""])
            reasoning = str(message.get("reasoning") or "").strip()
            if reasoning:
                lines.extend(["#### Raciocinio salvo", "", reasoning, ""])
            try:
                activities = json.loads(message.get("skill_activities_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                activities = []
            if activities:
                lines.extend([
                    "#### Skills e ferramentas",
                    "",
                    "```json",
                    json.dumps(activities, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ])
    if all_sessions:
        skill_runs = list(reversed(SkillRunRepo.list_for_user(user_id, limit=10000)))
        if skill_runs:
            lines.extend(["# Registro completo de Skills e ferramentas", ""])
            for run in skill_runs:
                lines.extend([
                    f"## {run.get('skill_name') or 'skill'} - {run.get('status') or 'unknown'}",
                    "",
                    f"Inicio: {run.get('started_at') or ''}",
                    f"Fim: {run.get('finished_at') or ''}",
                    "",
                    "### Entrada",
                    "",
                    "```json",
                    str(run.get("input_json") or "{}"),
                    "```",
                    "",
                ])
                output = str(run.get("output_summary") or "").strip()
                if output:
                    lines.extend(["### Resultado salvo", "", output, ""])
                error = str(run.get("error_message") or "").strip()
                if error:
                    lines.extend(["### Erro salvo", "", error, ""])
    content = "\n".join(lines).rstrip() + "\n"
    if len(content.encode("utf-8")) > MAX_HISTORY_EXPORT_BYTES:
        raise ValueError("O historico completo excede o limite de um arquivo; exporte em partes")
    return content, len(conversations), message_count


def _conversation_export_plan(
    user_id: int,
    instruction: str,
    session_id: str | None = None,
) -> dict:
    target = _explicit_workspace_file(instruction) or _latest_applied_workspace_file(user_id)
    if not target:
        target = "historico-conversas.md"
    content, conversation_count, message_count = _conversation_export_markdown(
        user_id,
        instruction,
        session_id,
    )
    return {
        "summary": (
            f"Atualizar {target} com {message_count} mensagens de "
            f"{conversation_count} conversas salvas."
        ),
        "actions": [{"operation": "write_file", "path": target, "content": content}],
    }


def _validate_relative_path(user_id: int, raw_path: str) -> str:
    value = str(raw_path or "").strip().replace("\\", "/")
    if value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        raise ValueError("Caminho absoluto nao e permitido no workspace")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Caminho de workspace invalido")
    if any(part.startswith(".") for part in path.parts):
        raise ValueError("A IA nao pode gerenciar caminhos internos ocultos")
    normalized = path.as_posix()
    safe_user_path(user_id, "workspace", normalized)
    return normalized


def _workspace_inventory(user_id: int) -> str:
    root = safe_user_path(user_id, "workspace")
    lines: list[str] = []
    used = 0
    for index, item in enumerate(sorted(root.rglob("*"), key=lambda path: path.as_posix().lower())):
        if index >= MAX_INVENTORY_ITEMS:
            lines.append("[inventario truncado por quantidade]")
            break
        relative = item.relative_to(root).as_posix()
        if any(part.startswith(".") for part in PurePosixPath(relative).parts):
            continue
        if item.is_dir():
            entry = f"[pasta] {relative}\n"
        else:
            entry = f"[arquivo] {relative} ({item.stat().st_size} bytes)\n"
            if item.suffix.lower() in TEXT_EXTENSIONS and item.stat().st_size <= 16000:
                try:
                    content = item.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    content = ""
                if content:
                    entry += f"--- conteudo de {relative} ---\n{content}\n--- fim ---\n"
        if used + len(entry) > MAX_INVENTORY_CHARS:
            lines.append("[inventario truncado]")
            break
        lines.append(entry)
        used += len(entry)
    return "".join(lines) or "[workspace vazio]"


def _recent_search_context(user_id: int, instruction: str) -> str:
    """Reuse the latest real search only when the user explicitly refers to it."""
    folded = _fold(instruction)
    references_search = re.search(
        r"\b(?:pesquisa|pesquisou|pesquisado|resultado|resultados|fonte|fontes|busca|buscou)\b",
        folded,
    )
    if not references_search:
        return ""

    for run in SkillRunRepo.list_for_user(user_id, limit=20):
        if run.get("skill_name") not in SEARCH_SKILL_NAMES or run.get("status") != "completed":
            continue
        output = str(run.get("output_summary") or "").strip()
        if not output:
            continue
        query = ""
        try:
            query = str(json.loads(run.get("input_json") or "{}").get("query") or "").strip()
        except (TypeError, json.JSONDecodeError):
            pass
        if len(output) > MAX_RECENT_SEARCH_CHARS:
            output = output[:MAX_RECENT_SEARCH_CHARS] + "\n[resultado truncado]"
        return f"Consulta: {query}\nResultado real da pesquisa:\n{output}"
    return ""


def _planner_messages(instruction: str, inventory: str, search_context: str = "") -> list:
    system = """Voce e o planejador seguro do Workspace pessoal do usuario.
Converta o pedido em JSON estrito, sem markdown e sem explicacoes fora do JSON.
Formato: {"summary":"resumo curto","actions":[...]}
Operacoes permitidas:
- {"operation":"mkdir","path":"pasta"}
- {"operation":"write_file","path":"pasta/arquivo.ext","content":"conteudo completo"}
- {"operation":"move","source":"origem","target":"destino"}
- {"operation":"delete","path":"caminho","recursive":true}
Use write_file tanto para criar quanto para editar; ao editar, devolva o conteudo final completo.
Pode combinar varias operacoes e criar nomes sensatos quando o usuario nao informar um nome.
Nunca use caminhos absolutos, '..', shell, rede ou caminhos ocultos. No maximo 20 acoes.
Nao diga que nao possui acesso: voce esta apenas criando um plano que sera confirmado pelo usuario.
Se houver uma pesquisa recente abaixo, use seus dados e fontes no conteudo solicitado."""
    research = f"\n\nPesquisa recente confirmada pelo backend:\n{search_context}" if search_context else ""
    human = f"Pedido do usuario:\n{instruction}{research}\n\nWorkspace atual:\n{inventory}"
    return [SystemMessage(content=system), HumanMessage(content=human)]


def _extract_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("A IA nao retornou um plano JSON valido")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Plano da IA invalido")
    return value


def _fallback_plan(instruction: str) -> dict:
    """Cover common direct requests if a provider returns malformed JSON."""
    folded = _fold(instruction)
    username_match = re.search(r"usuario(?:\s+se\s+chama|\s+e|\s*:)?\s+([A-Za-z0-9_.-]+)", folded)
    username = username_match.group(1) if username_match else "usuario"

    creation_requested = bool(re.search(r"\b(?:crie|criar|cria|escreva|salve)\b", folded))
    file_requested = bool(re.search(r"\b(?:arquivo|documento|nota|md|markdown|txt|json|csv|yaml|yml)\b", folded))
    if creation_requested and file_requested:
        path_match = re.search(r"([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:md|txt|json|csv|yaml|yml))", instruction, re.IGNORECASE)
        extension_match = re.search(
            r"\b(?:(?:arquivo|documento|nota)\s+)?(?:(?:em|no formato)\s+)?(md|markdown|txt|json|csv|yaml|yml)\b",
            folded,
        )
        extension = extension_match.group(1) if extension_match else "md"
        extension = "md" if extension == "markdown" else extension
        if path_match:
            file_path = path_match.group(1)
            folder = PurePosixPath(file_path).parent.as_posix()
        elif "sobre mim" in folded:
            folder = "sobre-mim"
            file_path = f"{folder}/README.{extension}"
        else:
            folder = "novo-projeto" if "pasta" in folded else ""
            file_path = f"{folder + '/' if folder else ''}documento.{extension}"

        if extension == "json":
            content = json.dumps({"usuario": username}, ensure_ascii=False, indent=2) + "\n"
        else:
            content = f"# Sobre mim\n\nMeu usuario se chama `{username}`.\n"
        actions = []
        if folder and folder != ".":
            actions.append({"operation": "mkdir", "path": folder})
        actions.append({"operation": "write_file", "path": file_path, "content": content})
        return {"summary": "Criar a estrutura e o arquivo solicitados.", "actions": actions}

    raise ValueError("Nao foi possivel transformar o pedido em operacoes seguras")


def _normalized_operation(raw: str) -> str:
    aliases = {
        "mkdir": "mkdir", "create_folder": "mkdir", "criar_pasta": "mkdir",
        "write_file": "write_file", "create_file": "write_file", "edit_file": "write_file",
        "criar_arquivo": "write_file", "editar_arquivo": "write_file",
        "move": "move", "rename": "move", "mover": "move", "renomear": "move",
        "delete": "delete", "remove": "delete", "apagar": "delete", "deletar": "delete",
    }
    operation = aliases.get(_fold(raw).replace(" ", "_"))
    if not operation:
        raise ValueError(f"Operacao de workspace nao permitida: {raw}")
    return operation


def _new_file_diff(path: str, content: str) -> str:
    return "".join(difflib.unified_diff([], content.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}"))


def _prepare_actions(user_id: int, raw_actions: object) -> list[dict]:
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError("O plano nao possui acoes")
    if len(raw_actions) > MAX_PLAN_ACTIONS:
        raise ValueError(f"O plano excede o limite de {MAX_PLAN_ACTIONS} acoes")

    prepared: list[dict] = []
    for raw in raw_actions:
        if not isinstance(raw, dict):
            raise ValueError("Acao de workspace invalida")
        operation = _normalized_operation(str(raw.get("operation") or raw.get("op") or ""))

        if operation == "mkdir":
            path = _validate_relative_path(user_id, raw.get("path", ""))
            target = safe_user_path(user_id, "workspace", path)
            if target.exists() and not target.is_dir():
                raise ValueError(f"Ja existe um arquivo em {path}")
            prepared.append({"operation": operation, "path": path, "exists": target.is_dir()})
            continue

        if operation == "write_file":
            path = _validate_relative_path(user_id, raw.get("path", ""))
            content = str(raw.get("content") or "")
            if len(content.encode("utf-8")) > 1024 * 1024:
                raise ValueError(f"Conteudo muito grande para {path}")
            target = safe_user_path(user_id, "workspace", path)
            if target.is_dir():
                raise ValueError(f"O destino {path} e uma pasta")
            if target.is_file():
                preview = preview_workspace_patch(user_id, path, content)
                prepared.append({
                    "operation": operation,
                    "path": path,
                    "content": content,
                    "mode": "edit",
                    "expected_checksum": preview.expected_checksum,
                    "new_checksum": preview.new_checksum,
                    "diff": preview.diff,
                })
            else:
                prepared.append({
                    "operation": operation,
                    "path": path,
                    "content": content,
                    "mode": "create",
                    "expected_checksum": None,
                    "new_checksum": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "diff": _new_file_diff(path, content),
                })
            continue

        if operation == "move":
            source = _validate_relative_path(user_id, raw.get("source", ""))
            target = _validate_relative_path(user_id, raw.get("target", ""))
            source_path = safe_user_path(user_id, "workspace", source)
            target_path = safe_user_path(user_id, "workspace", target)
            if not source_path.exists():
                raise FileNotFoundError(source)
            if target_path.exists():
                raise FileExistsError(target)
            prepared.append({"operation": operation, "source": source, "target": target})
            continue

        path = _validate_relative_path(user_id, raw.get("path", ""))
        target = safe_user_path(user_id, "workspace", path)
        if not target.exists():
            raise FileNotFoundError(path)
        prepared.append({"operation": "delete", "path": path, "recursive": bool(raw.get("recursive", target.is_dir()))})

    return prepared


def _plan_path(user_id: int, plan_id: str) -> Path:
    if not PLAN_ID_RE.fullmatch(plan_id or ""):
        raise ValueError("Identificador de plano invalido")
    return safe_user_path(user_id, "skills", f"audit/workspace_plans/{plan_id}.json")


def _write_plan(user_id: int, plan: dict) -> None:
    path = _plan_path(user_id, str(plan["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def get_workspace_plan(user_id: int, plan_id: str) -> dict:
    path = _plan_path(user_id, plan_id)
    if not path.is_file():
        raise FileNotFoundError(plan_id)
    plan = json.loads(path.read_text(encoding="utf-8"))
    if int(plan.get("user_id", -1)) != int(user_id):
        raise PermissionError("Plano pertence a outro usuario")
    return plan


async def create_workspace_plan(
    user_id: int,
    instruction: str,
    provider_config: dict | None = None,
    session_id: str | None = None,
) -> dict:
    if not workspace_manager_enabled(user_id):
        raise PermissionError("A skill workspace_manager esta desabilitada")
    inventory = _workspace_inventory(user_id)
    search_context = _recent_search_context(user_id, instruction)
    if _conversation_export_requested(instruction):
        proposal = _conversation_export_plan(user_id, instruction, session_id)
    else:
        try:
            raw = await asyncio.wait_for(
                generate(
                    _planner_messages(instruction, inventory, search_context),
                    provider_config=provider_config,
                ),
                timeout=PLANNER_TIMEOUT_SECONDS,
            )
            proposal = _extract_json(raw)
            if not proposal.get("actions"):
                proposal = _fallback_plan(instruction)
        except Exception:
            proposal = _fallback_plan(instruction)

    actions = _prepare_actions(user_id, proposal.get("actions"))
    plan = {
        "id": uuid4().hex,
        "user_id": user_id,
        "instruction": instruction,
        "summary": str(proposal.get("summary") or "Plano de gerenciamento do workspace."),
        "status": "pending",
        "actions": actions,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + PLAN_EXPIRY).isoformat(),
    }
    _write_plan(user_id, plan)
    SkillRunRepo.create(
        user_id,
        "workspace_manager",
        "completed",
        {"plan_id": plan["id"], "instruction": instruction, "action_count": len(actions)},
        output_summary="Plano criado; aguardando confirmacao do usuario.",
    )
    return plan


def apply_workspace_plan(user_id: int, plan_id: str) -> dict:
    plan = get_workspace_plan(user_id, plan_id)
    if plan.get("status") != "pending":
        raise ValueError(f"Plano nao esta pendente: {plan.get('status')}")
    expires_at = datetime.fromisoformat(str(plan["expires_at"]))
    if datetime.now(timezone.utc) > expires_at:
        plan["status"] = "expired"
        _write_plan(user_id, plan)
        raise ValueError("Plano expirado; gere um novo")

    results: list[dict] = []
    try:
        for action in plan.get("actions", []):
            operation = action["operation"]
            if operation == "mkdir":
                info = mkdir(user_id, action["path"])
                results.append({"operation": operation, "path": info.path})
            elif operation == "write_file":
                path = action["path"]
                target = safe_user_path(user_id, "workspace", path)
                if action.get("mode") == "create":
                    if target.exists():
                        raise FileExistsError(path)
                    info = write_text_file(user_id, path, action["content"])
                    results.append({"operation": operation, "path": info.path, "mode": "create"})
                else:
                    applied = apply_workspace_patch(
                        user_id,
                        path,
                        action["content"],
                        action["expected_checksum"],
                    )
                    results.append({"operation": operation, "path": applied.path, "mode": "edit", "snapshot_path": applied.snapshot_path})
            elif operation == "move":
                info = move_path(user_id, action["source"], action["target"])
                results.append({"operation": operation, "source": action["source"], "target": info.path})
            elif operation == "delete":
                deleted = delete_path(user_id, action["path"], recursive=bool(action.get("recursive")))
                results.append({"operation": operation, "path": action["path"], "deleted": deleted})

        plan["status"] = "applied"
        plan["applied_at"] = datetime.now(timezone.utc).isoformat()
        plan["results"] = results
        _write_plan(user_id, plan)
        SkillRunRepo.create(
            user_id,
            "workspace_manager",
            "completed",
            {"plan_id": plan_id, "action_count": len(results), "confirmed": True},
            output_summary=f"Plano aplicado com {len(results)} operacoes.",
        )
        return plan
    except Exception as exc:
        plan["status"] = "failed"
        plan["failed_at"] = datetime.now(timezone.utc).isoformat()
        plan["error"] = str(exc)
        plan["results"] = results
        _write_plan(user_id, plan)
        SkillRunRepo.create(
            user_id,
            "workspace_manager",
            "failed",
            {"plan_id": plan_id, "completed_actions": len(results), "confirmed": True},
            error_message=str(exc),
        )
        raise


def cancel_workspace_plan(user_id: int, plan_id: str) -> dict:
    plan = get_workspace_plan(user_id, plan_id)
    if plan.get("status") != "pending":
        raise ValueError(f"Plano nao esta pendente: {plan.get('status')}")
    plan["status"] = "cancelled"
    plan["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    _write_plan(user_id, plan)
    SkillRunRepo.create(
        user_id,
        "workspace_manager",
        "completed",
        {"plan_id": plan_id, "confirmed": False},
        output_summary="Plano cancelado pelo usuario; nenhuma alteracao aplicada.",
    )
    return plan
