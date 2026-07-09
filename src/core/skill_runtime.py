"""Runtime seguro para skills habilitadas por usuario."""

from __future__ import annotations

from collections.abc import Iterable
import re

from src.db.repository import SkillRepo, SkillRunRepo
from src.core.patcher import preview_workspace_patch
from src.core.skill_permissions import can_execute_skill, executable_skill_names
from src.core.workspace import read_text_file
from src.tools.web_search import web_search


SEARCH_SKILLS = {"simple_search", "search_and_answer"}
SEARCH_TRIGGERS = (
    "pesquise",
    "pesquisar",
    "busque",
    "buscar",
    "procure",
    "procurar",
    "google",
    "web",
    "internet",
    "noticias",
    "news",
    "search",
)
MAX_SKILL_CONTEXT_CHARS = 12000
WORKSPACE_READ_COMMAND = re.compile(r"^\s*@workspace:read\s+([^\r\n]+)\s*$", re.IGNORECASE)
WORKSPACE_PREVIEW_COMMAND = re.compile(
    r"^\s*@workspace:preview\s+([^\r\n]+)\r?\n---\r?\n([\s\S]+)$",
    re.IGNORECASE,
)


def _enabled_names(skills: Iterable[dict]) -> set[str]:
    return executable_skill_names(list(skills))


def should_force_rag(skills: Iterable[dict]) -> bool:
    """A skill personal_rag faz o chat sempre consultar o RAG pessoal."""
    return "personal_rag" in _enabled_names(skills)


def _enabled_skill(skills: Iterable[dict], name: str, permission: str | None = None) -> dict | None:
    for skill in skills:
        if skill.get("name") == name and can_execute_skill(skill, permission):
            return skill
    return None


def _search_skill_for_message(message: str, skills: Iterable[dict]) -> dict | None:
    """Prefer the richer workflow without ever executing duplicate searches."""
    msg = message.lower()
    if not any(trigger in msg for trigger in SEARCH_TRIGGERS):
        return None
    return (
        _enabled_skill(skills, "search_and_answer", "network")
        or _enabled_skill(skills, "simple_search", "network")
    )


def should_run_web_search(message: str, skills: Iterable[dict]) -> bool:
    """Compatibility helper for callers that only need the decision."""
    return _search_skill_for_message(message, skills) is not None


def build_runtime_context(skill_name: str, result: str | None) -> str:
    if not result:
        return ""
    return (
        f"Resultado da skill {skill_name}:\n"
        f"{result}\n\n"
        "Use este resultado como contexto auxiliar e cite fontes/titulos quando disponiveis."
    )


def _truncate_for_context(value: str, limit: int = MAX_SKILL_CONTEXT_CHARS) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n\n[conteudo truncado para caber no contexto]"


def _workspace_error_context(skill_name: str, error: Exception) -> str:
    return (
        f"A skill {skill_name} falhou: {error}. "
        "Explique o erro ao usuario e nao tente acessar outro caminho."
    )


async def _run_search_skill(user_id: int, skill: dict, message: str) -> str:
    skill_name = str(skill["name"])
    audit_skill_name = skill_name if skill.get("definition") else "web_search"
    config = skill.get("config") or {}
    try:
        max_results = int(config.get("max_results", 3))
    except (TypeError, ValueError):
        max_results = 3
    max_results = min(max(max_results, 1), 5)

    try:
        result = await web_search(message, max_results=max_results)
        if not result or result.startswith("Erro na busca"):
            raise RuntimeError(result or "Busca nao retornou resultados")
        SkillRunRepo.create(
            user_id,
            audit_skill_name,
            "completed",
            {"query": message, "max_results": max_results, "executor": "web_search"},
            output_summary=result,
        )
        return build_runtime_context(skill_name, result)
    except Exception as exc:
        SkillRunRepo.create(
            user_id,
            audit_skill_name,
            "failed",
            {"query": message, "max_results": max_results, "executor": "web_search"},
            error_message=str(exc),
        )
        return ""


def _run_workspace_read_skill(user_id: int, skill: dict, path: str) -> str:
    skill_name = str(skill["name"])
    try:
        content = read_text_file(user_id, path)
        context = (
            f"Conteudo solicitado do workspace ({path}):\n"
            f"```text\n{_truncate_for_context(content)}\n```"
        )
        SkillRunRepo.create(
            user_id,
            skill_name,
            "completed",
            {"path": path},
            output_summary=f"Leu {path} ({len(content)} caracteres).",
        )
        return build_runtime_context(skill_name, context)
    except Exception as exc:
        SkillRunRepo.create(user_id, skill_name, "failed", {"path": path}, error_message=str(exc))
        return _workspace_error_context(skill_name, exc)


def _run_workspace_preview_skill(user_id: int, skill: dict, path: str, content: str) -> str:
    skill_name = str(skill["name"])
    try:
        preview = preview_workspace_patch(user_id, path, content)
        result = (
            f"Preview de alteracao para {preview.path}. Nenhuma alteracao foi aplicada.\n"
            f"Checksum esperado: {preview.expected_checksum}\n"
            f"Checksum novo: {preview.new_checksum}\n"
            f"```diff\n{_truncate_for_context(preview.diff)}\n```"
        )
        SkillRunRepo.create(
            user_id,
            skill_name,
            "completed",
            {"path": path, "content_length": len(content)},
            output_summary=f"Preview criado para {path}; nenhuma alteracao aplicada.",
        )
        return build_runtime_context(skill_name, result)
    except Exception as exc:
        SkillRunRepo.create(
            user_id,
            skill_name,
            "failed",
            {"path": path, "content_length": len(content)},
            error_message=str(exc),
        )
        return _workspace_error_context(skill_name, exc)


async def run_enabled_skill_context(user_id: int, message: str) -> str:
    """Executa skills seguras habilitadas para o usuario e retorna contexto."""
    skills = SkillRepo.list_for_user(user_id)
    sections: list[str] = []

    search_skill = _search_skill_for_message(message, skills)
    if search_skill:
        sections.append(await _run_search_skill(user_id, search_skill, message))

    read_match = WORKSPACE_READ_COMMAND.match(message)
    read_skill = _enabled_skill(skills, "workspace_read", "workspace_read")
    if read_match and read_skill:
        sections.append(_run_workspace_read_skill(user_id, read_skill, read_match.group(1).strip()))

    preview_match = WORKSPACE_PREVIEW_COMMAND.match(message)
    preview_skill = _enabled_skill(skills, "workspace_write_preview", "workspace_write")
    if preview_match and preview_skill:
        sections.append(
            _run_workspace_preview_skill(
                user_id,
                preview_skill,
                preview_match.group(1).strip(),
                preview_match.group(2),
            )
        )

    return "\n\n".join(sections)


def user_has_personal_rag(user_id: int, message: str = "", log_run: bool = False) -> bool:
    enabled = should_force_rag(SkillRepo.list_for_user(user_id))
    if enabled and log_run:
        SkillRunRepo.create(
            user_id,
            "personal_rag",
            "completed",
            {"message": message},
            output_summary="RAG pessoal habilitado para esta mensagem.",
        )
    return enabled
