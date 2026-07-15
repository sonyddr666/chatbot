"""Dynamic registry of tools that are actually available to one user."""

from __future__ import annotations

from typing import Any

from src.core.agent.schemas import RegisteredTool, ToolDefinition, ToolResult
from src.core.image_actions import execute_image_action, has_antigravity_image_model
from src.core.skill_permissions import can_execute_skill
from src.core.skill_runtime import execute_enabled_skill_tool, runtime_skill_activity
from src.core.workspace_agent import create_workspace_plan, workspace_manager_enabled
from src.db.repository import SkillRepo
from src.tools.get_time import current_time


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


def _object_schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


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
    if "conversation_history" in enabled:
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
    if "workspace_read" in enabled and can_execute_skill(enabled["workspace_read"], "workspace_read"):
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
    if "workspace_manager" in enabled and workspace_manager_enabled(context.user_id):
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
