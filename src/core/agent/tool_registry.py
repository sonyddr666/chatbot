"""Dynamic registry of tools that are actually available to one user."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from src.core.agent.schemas import RegisteredTool, ToolDefinition, ToolResult
from src.core.agent.policy import is_active_admin
from src.core.file_delivery import resolve_file_delivery
from src.core.image_actions import execute_image_action, has_antigravity_image_model
from src.core.skill_permissions import can_execute_skill, skill_permissions
from src.core.skill_runtime import execute_enabled_skill_tool, runtime_skill_activity
from src.core.workspace import grep_workspace, list_tree, read_text_file
from src.core.workspace_agent import create_workspace_plan, workspace_manager_enabled
from src.db.repository import ChatJobRepo, ScheduledTaskRepo, SkillRepo
from src.rag.personal import retrieve_user_context
from src.tools.calculator import calculate
from src.tools.conversation_history import search_conversation_history
from src.tools.get_time import current_time
from src.tools.url_reader import read_url_content
from src.tools.weather import get_weather
from src.tools.web_search import web_search


_ASPECT_RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
_IMAGE_SIZES = {"0.5K", "1K", "2K", "4K"}


def _string(arguments: dict, name: str, *, required: bool = True, maximum: int = 8000) -> str:
    value = str(arguments.get(name) or "").strip()
    if required and not value:
        raise ValueError(f"Argumento obrigatorio ausente: {name}")
    if len(value) > maximum:
        raise ValueError(f"Argumento excede o limite: {name}")
    return value


def _image_options(arguments: dict) -> tuple[str, str, int]:
    aspect = str(arguments.get("aspect_ratio") or "1:1")
    if aspect not in _ASPECT_RATIOS:
        raise ValueError("aspect_ratio invalido")
    size = str(arguments.get("image_size") or "1K").upper()
    if size not in _IMAGE_SIZES:
        raise ValueError("image_size invalido")
    try:
        count = int(arguments.get("count") or 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("count invalido") from exc
    if not 1 <= count <= 4:
        raise ValueError("count deve estar entre 1 e 4")
    return aspect, size, count


async def _generate_image(context: Any, arguments: dict) -> ToolResult:
    prompt = _string(arguments, "prompt")
    aspect, size, count = _image_options(arguments)
    artifacts = await execute_image_action(context.user_id, {
        "operation": "generate",
        "reference": None,
        "prompt": prompt,
        "aspect_ratio": aspect,
        "image_size": size,
        "count": count,
    })
    return ToolResult(
        call_id=context.current_call_id,
        name="image_generate",
        status="completed",
        content=f"{len(artifacts)} imagem(ns) gerada(s) com Antigravity.",
        attachments=artifacts,
        activity={
            "name": "image_generate",
            "status": "completed",
            "label": f"{len(artifacts)} imagem(ns) gerada(s)",
            "source_count": 0,
            "sources": [],
        },
    )


async def _edit_image(context: Any, arguments: dict) -> ToolResult:
    prompt = _string(arguments, "prompt")
    aspect, size, count = _image_options(arguments)
    reference = context.latest_image
    if not reference:
        raise ValueError("Nenhuma imagem de referencia esta disponivel nesta conversa")
    artifacts = await execute_image_action(context.user_id, {
        "operation": "edit",
        "reference": reference,
        "prompt": prompt,
        "aspect_ratio": aspect,
        "image_size": size,
        "count": count,
    })
    return ToolResult(
        call_id=context.current_call_id,
        name="image_edit",
        status="completed",
        content=f"{len(artifacts)} imagem(ns) editada(s) com Antigravity.",
        attachments=artifacts,
        activity={
            "name": "image_edit",
            "status": "completed",
            "label": f"{len(artifacts)} imagem(ns) editada(s)",
            "source_count": 0,
            "sources": [],
        },
    )


def _generic_activity(name: str, label: str, status: str = "completed") -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "label": label,
        "source_count": 0,
        "sources": [],
    }


def _skill_handler(name: str):
    async def handler(context: Any, arguments: dict) -> ToolResult:
        content = await execute_enabled_skill_tool(
            context.user_id,
            name,
            arguments,
            session_id=context.session_id,
        )
        activity = runtime_skill_activity(content) or _generic_activity(
            name,
            f"Ferramenta concluida: {name}",
        )
        return ToolResult(
            call_id=context.current_call_id,
            name=name,
            status="completed",
            content=content,
            activity=activity,
            audit_recorded=True,
        )

    return handler


async def _workspace_plan(context: Any, arguments: dict) -> ToolResult:
    instruction = _string(arguments, "instruction")
    plan = await create_workspace_plan(
        context.user_id,
        instruction,
        context.provider_config,
        session_id=context.session_id,
    )
    return ToolResult(
        call_id=context.current_call_id,
        name="workspace_plan",
        status="completed",
        content=(
            f"Plano {plan['id']} preparado com {len(plan.get('actions') or [])} acao(oes). "
            "Nenhuma alteracao foi aplicada; o usuario precisa confirmar o plano."
        ),
        activity=_generic_activity("workspace_plan", "Plano do Workspace preparado"),
        data={"workspace_plan": plan},
        audit_recorded=True,
    )


async def _get_time(context: Any, arguments: dict) -> ToolResult:
    requested_timezone = str(arguments.get("timezone") or "").strip()
    payload = current_time(context.user_id, requested_timezone)
    return ToolResult(
        call_id=context.current_call_id,
        name="get_time",
        status="completed",
        content=(
            f"Data e hora atuais: {payload['weekday']}, {payload['date']} "
            f"as {payload['time']} ({payload['timezone']}, UTC{payload['utc_offset']})."
        ),
        activity=_generic_activity("get_time", "Data e hora consultadas"),
        data=payload,
    )


async def _calculate(context: Any, arguments: dict) -> ToolResult:
    expression = _string(arguments, "expression", maximum=200)
    content = calculate(expression)
    return ToolResult(
        call_id=context.current_call_id,
        name="calculate",
        status="completed",
        content=content,
        activity=_generic_activity("calculate", "Calculo concluido"),
        data={"expression": expression},
    )


async def _get_weather(context: Any, arguments: dict) -> ToolResult:
    city = _string(arguments, "city", maximum=120)
    content = await get_weather(city)
    return ToolResult(
        call_id=context.current_call_id,
        name="get_weather",
        status="completed",
        content=content,
        activity=_generic_activity("get_weather", "Clima consultado"),
        data={"city": city},
    )


async def _read_url(context: Any, arguments: dict) -> ToolResult:
    url = _string(arguments, "url", maximum=2048)
    payload = await read_url_content(url)
    return ToolResult(
        call_id=context.current_call_id,
        name="read_url_content",
        status="completed",
        content=payload["text"],
        activity=_generic_activity("read_url_content", "Conteudo da URL lido"),
        data={
            "url": payload["url"],
            "content_type": payload["content_type"],
            "truncated": payload["truncated"],
        },
    )


async def _workspace_list(context: Any, arguments: dict) -> ToolResult:
    path = _string(arguments, "path", required=False, maximum=500)
    nodes = await asyncio.to_thread(list_tree, context.user_id, path)
    items = [asdict(node) for node in nodes[:200]]
    return ToolResult(
        call_id=context.current_call_id,
        name="workspace_list",
        status="completed",
        content=json.dumps(items, ensure_ascii=False),
        activity=_generic_activity("workspace_list", f"{len(items)} item(ns) listado(s) no Workspace"),
        data={"path": path, "count": len(items)},
    )


async def _workspace_grep(context: Any, arguments: dict) -> ToolResult:
    query = _string(arguments, "query", maximum=500)
    path = _string(arguments, "path", required=False, maximum=500)
    try:
        limit = max(1, min(int(arguments.get("limit") or 50), 200))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit invalido") from exc
    matches = await asyncio.to_thread(
        grep_workspace,
        context.user_id,
        query,
        path,
        limit=limit,
    )
    return ToolResult(
        call_id=context.current_call_id,
        name="workspace_grep",
        status="completed",
        content=json.dumps(matches, ensure_ascii=False),
        activity=_generic_activity("workspace_grep", f"{len(matches)} ocorrencia(s) no Workspace"),
        data={"query": query, "path": path, "count": len(matches)},
    )


async def _rag_search(context: Any, arguments: dict) -> ToolResult:
    query = _string(arguments, "query", maximum=2000)
    try:
        top_k = max(1, min(int(arguments.get("top_k") or 4), 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("top_k invalido") from exc
    content = await asyncio.to_thread(retrieve_user_context, context.user_id, query, top_k, None)
    return ToolResult(
        call_id=context.current_call_id,
        name="rag_search",
        status="completed",
        content=content or "Nenhum contexto relevante encontrado no RAG pessoal.",
        activity=_generic_activity("rag_search", "RAG pessoal consultado"),
        data={"query": query, "top_k": top_k, "found": bool(content)},
    )


async def _list_permissions(context: Any, arguments: dict) -> ToolResult:
    skills = SkillRepo.list_for_user(context.user_id)
    rows = [
        {
            "name": skill.get("name"),
            "enabled": bool(skill.get("enabled")),
            "executable": can_execute_skill(skill),
            "permissions": skill_permissions(skill),
            "risk_level": int(skill.get("risk_level") or 1),
        }
        for skill in skills
    ]
    payload = {
        "is_admin": True,
        "scope": "current_user_only",
        "admin_tools": [
            "calculate",
            "get_weather",
            "read_url_content",
            "workspace_list",
            "workspace_grep",
            "rag_search",
            "list_permissions",
            "web_search",
            "conversation_history",
            "workspace_read",
            "workspace_plan",
            "file_delivery",
            "background_tasks",
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
        ],
        "skills": rows,
    }
    return ToolResult(
        call_id=context.current_call_id,
        name="list_permissions",
        status="completed",
        content=json.dumps(payload, ensure_ascii=False),
        activity=_generic_activity("list_permissions", "Permissoes consultadas"),
        data={"skill_count": len(rows), "is_admin": True},
    )


async def _web_search(context: Any, arguments: dict) -> ToolResult:
    query = _string(arguments, "query", maximum=1000)
    try:
        max_results = max(1, min(int(arguments.get("max_results") or 5), 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("max_results invalido") from exc
    content = await web_search(query, max_results=max_results)
    if not content or content.startswith("Erro na busca"):
        raise RuntimeError(content or "Busca web nao retornou resultado")
    return ToolResult(
        call_id=context.current_call_id,
        name="web_search",
        status="completed",
        content=content,
        activity=_generic_activity("web_search", "Pesquisa web concluida"),
        data={"query": query, "max_results": max_results},
    )


async def _conversation_history_admin(context: Any, arguments: dict) -> ToolResult:
    query = _string(arguments, "query", maximum=1000)
    payload = await asyncio.to_thread(
        search_conversation_history,
        context.user_id,
        query,
        context.session_id,
    )
    return ToolResult(
        call_id=context.current_call_id,
        name="conversation_history",
        status="completed",
        content=str(payload.get("context") or "Nenhuma conversa relevante encontrada."),
        activity=_generic_activity("conversation_history", "Historico privado consultado"),
        data={
            "conversation_count": int(payload.get("conversation_count") or 0),
            "message_count": int(payload.get("message_count") or 0),
        },
    )


async def _workspace_read_admin(context: Any, arguments: dict) -> ToolResult:
    path = _string(arguments, "path", maximum=500)
    content = await asyncio.to_thread(read_text_file, context.user_id, path)
    return ToolResult(
        call_id=context.current_call_id,
        name="workspace_read",
        status="completed",
        content=content,
        activity=_generic_activity("workspace_read", f"Arquivo lido: {path}"),
        data={"path": path, "characters": len(content)},
    )


async def _file_delivery_admin(context: Any, arguments: dict) -> ToolResult:
    path = _string(arguments, "path", required=False, maximum=500)
    selection = await asyncio.to_thread(
        resolve_file_delivery,
        context.user_id,
        context.session_id,
        path or context.request,
        require_intent=False,
        require_skill=False,
    )
    if not selection:
        raise FileNotFoundError("Nenhum arquivo correspondente foi encontrado")
    return ToolResult(
        call_id=context.current_call_id,
        name="file_delivery",
        status="completed",
        content=f"Arquivo preparado para envio: {selection.filename}",
        activity=_generic_activity("file_delivery", f"Arquivo localizado: {selection.filename}"),
        data={"file_delivery": asdict(selection)},
    )


async def _background_tasks(context: Any, arguments: dict) -> ToolResult:
    try:
        limit = max(1, min(int(arguments.get("limit") or 20), 100))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit invalido") from exc
    jobs = await asyncio.to_thread(ChatJobRepo.list_for_user, context.user_id, limit)
    items = [
        {
            "id": job.get("id"),
            "session_id": job.get("session_id"),
            "status": job.get("status"),
            "provider": job.get("provider_name"),
            "model": job.get("model_name"),
            "created_at": job.get("created_at"),
            "completed_at": job.get("completed_at"),
            "error": job.get("error"),
        }
        for job in jobs
    ]
    return ToolResult(
        call_id=context.current_call_id,
        name="background_tasks",
        status="completed",
        content=json.dumps(items, ensure_ascii=False),
        activity=_generic_activity("background_tasks", f"{len(items)} job(s) consultado(s)"),
        data={"count": len(items)},
    )


def _scheduled_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("run_at deve estar em ISO 8601, incluindo o fuso horario") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("run_at precisa incluir o fuso horario, por exemplo -03:00")
    now = datetime.now(timezone.utc)
    normalized = parsed.astimezone(timezone.utc)
    if normalized <= now:
        raise ValueError("run_at precisa estar no futuro")
    if normalized > now + timedelta(days=365):
        raise ValueError("O agendamento nao pode exceder 365 dias")
    return normalized


async def _schedule_task(context: Any, arguments: dict) -> ToolResult:
    prompt = _string(arguments, "prompt", maximum=8000)
    run_at = _scheduled_datetime(_string(arguments, "run_at", maximum=80))
    session_id = _string(arguments, "session_id", required=False, maximum=255) or context.session_id
    task = await asyncio.to_thread(
        ScheduledTaskRepo.create,
        context.user_id,
        session_id,
        prompt,
        run_at,
    )
    return ToolResult(
        call_id=context.current_call_id,
        name="schedule_task",
        status="completed",
        content=f"Tarefa agendada para {task['run_at']} com id {task['id']}.",
        activity=_generic_activity("schedule_task", "Tarefa agendada"),
        data={"schedule": task},
    )


async def _list_schedules(context: Any, arguments: dict) -> ToolResult:
    try:
        limit = max(1, min(int(arguments.get("limit") or 50), 100))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit invalido") from exc
    tasks = await asyncio.to_thread(ScheduledTaskRepo.list_for_user, context.user_id, limit)
    return ToolResult(
        call_id=context.current_call_id,
        name="list_schedules",
        status="completed",
        content=json.dumps(tasks, ensure_ascii=False),
        activity=_generic_activity("list_schedules", f"{len(tasks)} agendamento(s) consultado(s)"),
        data={"count": len(tasks)},
    )


async def _cancel_schedule(context: Any, arguments: dict) -> ToolResult:
    schedule_id = _string(arguments, "schedule_id", maximum=64)
    cancelled = await asyncio.to_thread(ScheduledTaskRepo.cancel, schedule_id, context.user_id)
    if not cancelled:
        raise ValueError("Agendamento nao encontrado, ja executado ou ja cancelado")
    return ToolResult(
        call_id=context.current_call_id,
        name="cancel_schedule",
        status="completed",
        content=f"Agendamento {schedule_id} cancelado.",
        activity=_generic_activity("cancel_schedule", "Agendamento cancelado"),
        data={"schedule_id": schedule_id},
    )


def _object_schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _admin_tools() -> list[RegisteredTool]:
    """Privileged, bounded tools exposed only to an approved active administrator."""
    return [
        RegisteredTool(
            definition=ToolDefinition(
                name="calculate",
                description="Calcula expressoes aritmeticas de modo local e seguro.",
                input_schema=_object_schema({
                    "expression": {"type": "string", "description": "Expressao, como (18 * 4) / 3."},
                }, ["expression"]),
                permission="admin:calculator",
            ),
            handler=_calculate,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="get_weather",
                description="Consulta o clima atual de uma cidade pela internet.",
                input_schema=_object_schema({
                    "city": {"type": "string", "description": "Cidade e, se necessario, estado ou pais."},
                }, ["city"]),
                permission="admin:network",
            ),
            handler=_get_weather,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="read_url_content",
                description=(
                    "Le o conteudo textual de uma URL HTTP ou HTTPS publica. "
                    "Nao acessa localhost, rede privada, credenciais ou arquivos locais."
                ),
                input_schema=_object_schema({
                    "url": {"type": "string", "description": "URL publica completa para ler."},
                }, ["url"]),
                permission="admin:network",
            ),
            handler=_read_url,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="workspace_list",
                description="Lista arquivos e pastas do Workspace privado do administrador atual.",
                input_schema=_object_schema({
                    "path": {"type": "string", "description": "Pasta relativa opcional; vazio lista a raiz."},
                }, []),
                permission="admin:workspace_read",
            ),
            handler=_workspace_list,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="workspace_grep",
                description="Procura texto literal dentro de arquivos do Workspace privado do administrador atual.",
                input_schema=_object_schema({
                    "query": {"type": "string", "description": "Texto literal a localizar."},
                    "path": {"type": "string", "description": "Arquivo ou pasta relativa opcional."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                }, ["query"]),
                permission="admin:workspace_read",
            ),
            handler=_workspace_grep,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="rag_search",
                description="Consulta documentos indexados somente no RAG pessoal do administrador atual.",
                input_schema=_object_schema({
                    "query": {"type": "string", "description": "Assunto a buscar nos documentos pessoais."},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 4},
                }, ["query"]),
                permission="admin:rag_read",
            ),
            handler=_rag_search,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="list_permissions",
                description="Lista as ferramentas, skills e permissoes efetivas do administrador atual.",
                input_schema=_object_schema({}, []),
                permission="admin:permissions_read",
            ),
            handler=_list_permissions,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="web_search",
                description="Pesquisa informacoes atuais na web e devolve fontes publicas.",
                input_schema=_object_schema({
                    "query": {"type": "string", "description": "Consulta objetiva."},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                }, ["query"]),
                permission="admin:network",
            ),
            handler=_web_search,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="conversation_history",
                description="Pesquisa as outras conversas privadas do administrador atual.",
                input_schema=_object_schema({
                    "query": {"type": "string", "description": "Assunto a localizar no historico."},
                }, ["query"]),
                permission="admin:history_read",
            ),
            handler=_conversation_history_admin,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="workspace_read",
                description="Le um arquivo textual do Workspace privado do administrador atual.",
                input_schema=_object_schema({
                    "path": {"type": "string", "description": "Caminho relativo do arquivo."},
                }, ["path"]),
                permission="admin:workspace_read",
            ),
            handler=_workspace_read_admin,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="workspace_plan",
                description=(
                    "Prepara um plano de criacao, edicao, movimento ou exclusao no Workspace. "
                    "Nada e alterado ate o administrador confirmar o plano na interface."
                ),
                input_schema=_object_schema({
                    "instruction": {"type": "string", "description": "Alteracoes solicitadas."},
                }, ["instruction"]),
                permission="admin:workspace_write",
                confirmation_required=True,
                risk_level=2,
            ),
            handler=_workspace_plan,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="file_delivery",
                description="Localiza e envia ao chat um arquivo privado do administrador.",
                input_schema=_object_schema({
                    "path": {"type": "string", "description": "Nome ou caminho relativo opcional."},
                }, []),
                permission="admin:file_delivery",
            ),
            handler=_file_delivery_admin,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="background_tasks",
                description="Lista o estado dos jobs de chat em segundo plano do administrador atual.",
                input_schema=_object_schema({
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                }, []),
                permission="admin:tasks_read",
            ),
            handler=_background_tasks,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="schedule_task",
                description=(
                    "Agenda uma tarefa unica para o futuro. No horario, cria um job persistente "
                    "e o modelo responde mesmo sem o navegador aberto."
                ),
                input_schema=_object_schema({
                    "prompt": {"type": "string", "description": "Instrucao que sera executada no horario."},
                    "run_at": {"type": "string", "description": "ISO 8601 futuro com fuso, como 2026-07-16T09:00:00-03:00."},
                    "session_id": {"type": "string", "description": "Conversa opcional; usa a atual por padrao."},
                }, ["prompt", "run_at"]),
                permission="admin:schedule_write",
                risk_level=2,
            ),
            handler=_schedule_task,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="list_schedules",
                description="Lista tarefas agendadas, executadas, falhas ou canceladas do administrador.",
                input_schema=_object_schema({
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                }, []),
                permission="admin:schedule_read",
            ),
            handler=_list_schedules,
        ),
        RegisteredTool(
            definition=ToolDefinition(
                name="cancel_schedule",
                description="Cancela uma tarefa futura do administrador que ainda nao iniciou.",
                input_schema=_object_schema({
                    "schedule_id": {"type": "string", "description": "ID retornado por schedule_task."},
                }, ["schedule_id"]),
                permission="admin:schedule_write",
                risk_level=2,
            ),
            handler=_cancel_schedule,
        ),
    ]


def available_tools(context: Any) -> list[RegisteredTool]:
    tools: list[RegisteredTool] = [RegisteredTool(
        definition=ToolDefinition(
            name="get_time",
            description=(
                "Retorna a data, o dia da semana e a hora atuais com fuso horario confiavel. "
                "Use para perguntas como hoje, agora, que dia e, que horas sao ou datas relativas."
            ),
            input_schema=_object_schema({
                "timezone": {
                    "type": "string",
                    "description": "Fuso IANA opcional, por exemplo America/Sao_Paulo ou Europe/Lisbon.",
                },
            }, []),
        ),
        handler=_get_time,
    )]
    if is_active_admin(context.user_id):
        tools.extend(_admin_tools())
    if has_antigravity_image_model(context.user_id):
        common_properties = {
            "prompt": {"type": "string", "description": "Descricao fiel da imagem desejada."},
            "aspect_ratio": {"type": "string", "enum": sorted(_ASPECT_RATIOS), "default": "1:1"},
            "image_size": {"type": "string", "enum": sorted(_IMAGE_SIZES), "default": "1K"},
            "count": {"type": "integer", "minimum": 1, "maximum": 4, "default": 1},
        }
        tools.append(RegisteredTool(
            definition=ToolDefinition(
                name="image_generate",
                description=(
                    "Gera uma ou mais imagens novas quando o usuario pede para criar, mostrar ou visualizar "
                    "uma cena, arte, foto, ilustracao, capa, poster, logo ou outro resultado visual."
                ),
                input_schema={
                    "type": "object",
                    "properties": common_properties,
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
                permission="image_generate",
            ),
            handler=_generate_image,
        ))
        if context.latest_image:
            tools.append(RegisteredTool(
                definition=ToolDefinition(
                    name="image_edit",
                    description=(
                        "Edita a imagem anexada ou a imagem mais recente da conversa conforme o pedido do usuario."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": common_properties,
                        "required": ["prompt"],
                        "additionalProperties": False,
                    },
                    permission="image_edit",
                ),
                handler=_edit_image,
            ))
    skills = SkillRepo.list_for_user(context.user_id)
    enabled = {
        str(skill.get("name")): skill
        for skill in skills
        if skill.get("enabled") and can_execute_skill(skill)
    }
    selected_search = next(
        (name for name in ("perplexo_search", "search_and_answer", "simple_search") if name in enabled),
        None,
    )
    if selected_search:
        tools.append(RegisteredTool(
            definition=ToolDefinition(
                name=selected_search,
                description=str(enabled[selected_search].get("description") or "Pesquisa informacoes atuais na web."),
                input_schema=_object_schema({
                    "query": {"type": "string", "description": "Consulta objetiva a pesquisar."},
                }, ["query"]),
                permission="network",
                risk_level=int(enabled[selected_search].get("risk_level") or 1),
            ),
            handler=_skill_handler(selected_search),
        ))
    if "conversation_history" in enabled and not any(
        tool.definition.name == "conversation_history" for tool in tools
    ):
        tools.append(RegisteredTool(
            definition=ToolDefinition(
                name="conversation_history",
                description=str(enabled["conversation_history"].get("description")),
                input_schema=_object_schema({
                    "query": {"type": "string", "description": "Assunto a localizar nas outras conversas."},
                }, ["query"]),
                permission="history_read",
            ),
            handler=_skill_handler("conversation_history"),
        ))
    workspace_reader = next(
        (enabled[name] for name in ("workspace_manager", "workspace_read", "file_delivery") if name in enabled),
        None,
    )
    if workspace_reader and can_execute_skill(workspace_reader, "workspace_read"):
        tools.append(RegisteredTool(
            definition=ToolDefinition(
                name="workspace_search",
                description="Busca arquivos e pastas somente no Workspace privado do usuario; nunca pesquisa a internet.",
                input_schema=_object_schema({
                    "query": {"type": "string", "description": "Nome, trecho ou assunto do arquivo procurado."},
                }, ["query"]),
                permission="workspace_read",
            ),
            handler=_skill_handler("workspace_search"),
        ))
    if (
        "workspace_read" in enabled
        and not any(tool.definition.name == "workspace_read" for tool in tools)
        and can_execute_skill(enabled["workspace_read"], "workspace_read")
    ):
        tools.append(RegisteredTool(
            definition=ToolDefinition(
                name="workspace_read",
                description="Le um arquivo de texto dentro do Workspace privado do usuario.",
                input_schema=_object_schema({
                    "path": {"type": "string", "description": "Caminho relativo dentro do Workspace."},
                }, ["path"]),
                permission="workspace_read",
            ),
            handler=_skill_handler("workspace_read"),
        ))
    if "workspace_write_preview" in enabled and can_execute_skill(
        enabled["workspace_write_preview"], "workspace_write"
    ):
        tools.append(RegisteredTool(
            definition=ToolDefinition(
                name="workspace_write_preview",
                description="Prepara um diff de alteracao em arquivo sem aplicar a escrita.",
                input_schema=_object_schema({
                    "path": {"type": "string", "description": "Caminho relativo do arquivo."},
                    "content": {"type": "string", "description": "Novo conteudo proposto."},
                }, ["path", "content"]),
                permission="workspace_write",
                confirmation_required=True,
                risk_level=2,
            ),
            handler=_skill_handler("workspace_write_preview"),
        ))
    if (
        "workspace_manager" in enabled
        and not any(tool.definition.name == "workspace_plan" for tool in tools)
        and workspace_manager_enabled(context.user_id)
    ):
        tools.append(RegisteredTool(
            definition=ToolDefinition(
                name="workspace_plan",
                description=(
                    "Cria um plano de alteracoes no Workspace. Nao aplica nenhuma escrita, movimento ou exclusao; "
                    "o usuario precisa revisar e confirmar depois."
                ),
                input_schema=_object_schema({
                    "instruction": {"type": "string", "description": "Alteracoes que o usuario pediu."},
                }, ["instruction"]),
                permission="workspace_write",
                confirmation_required=True,
                risk_level=2,
            ),
            handler=_workspace_plan,
        ))
    return tools
