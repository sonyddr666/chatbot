"""Runtime seguro para skills habilitadas por usuario."""

from __future__ import annotations

from collections.abc import Iterable
import re
import unicodedata

from src.db.repository import SkillRepo, SkillRunRepo
from src.core.patcher import preview_workspace_patch
from src.core.skill_permissions import can_execute_skill, executable_skill_names
from src.core.workspace import read_text_file
from src.tools.perplexo_search import perplexo_search
from src.tools.web_search import web_search


SEARCH_SKILLS = {"perplexo_search", "simple_search", "search_and_answer"}
SEARCH_TRIGGERS = (
    "pesquise",
    "pesquisa",
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
SKILL_RESULT_NAME = re.compile(r"Resultado da skill ([a-zA-Z0-9_-]+):")
MARKDOWN_SOURCE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BARE_SOURCE = re.compile(r"https?://[^\s)>]+")


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


def _normalized_message(message: str) -> str:
    normalized = unicodedata.normalize("NFKD", message.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _search_skill_for_message(message: str, skills: Iterable[dict]) -> dict | None:
    """Prefer the richer workflow without ever executing duplicate searches."""
    msg = _normalized_message(message)
    if not any(trigger in msg for trigger in SEARCH_TRIGGERS):
        return None
    return (
        _enabled_skill(skills, "perplexo_search", "network")
        or
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
        "A pesquisa acima JA foi executada pelo backend para esta mensagem. "
        "Nao peca autorizacao para pesquisar novamente e nao diga que a skill precisa ser ativada. "
        "Responda usando o resultado atual e preserve as URLs das fontes em Markdown."
    )


def runtime_skill_activity(runtime_context: str) -> dict | None:
    """Build safe UI evidence only from a successfully returned search context."""
    match = SKILL_RESULT_NAME.search(runtime_context or "")
    if not match:
        return None
    skill_name = match.group(1)
    if skill_name not in SEARCH_SKILLS:
        return None

    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_label, url in MARKDOWN_SOURCE.findall(runtime_context):
        clean_url = url.rstrip(".,;:")
        if clean_url in seen:
            continue
        seen.add(clean_url)
        label = raw_label.strip()
        if label.isdigit():
            label = f"Fonte {label}"
        sources.append({"label": label[:80] or f"Fonte {len(sources) + 1}", "url": clean_url})
    for url in BARE_SOURCE.findall(runtime_context):
        clean_url = url.rstrip(".,;:")
        if clean_url in seen:
            continue
        seen.add(clean_url)
        sources.append({"label": f"Fonte {len(sources) + 1}", "url": clean_url})

    used_fallback = "Fallback de pesquisa simples" in runtime_context
    if skill_name == "perplexo_search" and not used_fallback:
        label = "Pesquisa Perplexo concluida"
    elif used_fallback:
        label = "Pesquisa concluida pelo fallback"
    else:
        label = "Pesquisa web concluida"
    return {
        "name": skill_name,
        "status": "completed",
        "label": label,
        "source_count": len(sources),
        "sources": sources[:8],
    }


def _truncate_for_context(value: str, limit: int = MAX_SKILL_CONTEXT_CHARS) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n\n[conteudo truncado para caber no contexto]"


def _workspace_error_context(skill_name: str, error: Exception) -> str:
    return (
        f"A skill {skill_name} falhou: {error}. "
        "Explique o erro ao usuario e nao tente acessar outro caminho."
    )


def _choice(config: dict, key: str, allowed: set[str], default: str) -> str:
    value = str(config.get(key, default)).strip().lower()
    return value if value in allowed else default


def _perplexo_options(message: str, config: dict) -> dict[str, str]:
    options = {
        "model": _choice(config, "model", {"best", "deep-research"}, "best"),
        "focus": _choice(config, "focus", {"web", "academic"}, "web"),
        "time_range": _choice(
            config,
            "time_range",
            {"day", "week", "month", "year", "all"},
            "week",
        ),
        "citation_mode": _choice(
            config,
            "citation_mode",
            {"markdown", "plain"},
            "markdown",
        ),
    }
    normalized = _normalized_message(message)
    if any(term in normalized for term in ("pesquisa profunda", "pesquisa aprofundada", "deep research")):
        options.update(model="deep-research", focus="academic", time_range="year")
    elif any(term in normalized for term in ("academica", "cientifica", "artigo cientifico")):
        options.update(focus="academic", time_range="year")
    return options


def _fallback_enabled(config: dict) -> bool:
    value = config.get("fallback_enabled", True)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


async def _run_search_skill(user_id: int, skill: dict, message: str) -> str:
    skill_name = str(skill["name"])
    audit_skill_name = skill_name if skill.get("definition") else "web_search"
    config = skill.get("config") or {}
    definition = skill.get("definition") or {}
    executor = str(definition.get("executor") or "web_search")
    try:
        max_results = int(config.get("max_results", 3))
    except (TypeError, ValueError):
        max_results = 3
    max_results = min(max(max_results, 1), 5)
    input_data = {"query": message, "executor": executor}

    try:
        if executor == "perplexo_search" or skill_name == "perplexo_search":
            options = _perplexo_options(message, config)
            input_data.update(options)
            try:
                result = await perplexo_search(message, user_id, **options)
            except Exception as primary_error:
                if not _fallback_enabled(config):
                    raise
                result = await web_search(message, max_results=max_results)
                if not result or result.startswith("Erro na busca"):
                    raise RuntimeError(
                        f"Perplexo falhou ({primary_error}) e o fallback tambem falhou"
                    )
                input_data["fallback"] = "web_search"
                result = (
                    "[Fallback de pesquisa simples usado porque o Perplexo estava indisponivel.]\n\n"
                    + result
                )
        else:
            input_data["max_results"] = max_results
            result = await web_search(message, max_results=max_results)
        if not result or result.startswith("Erro na busca"):
            raise RuntimeError(result or "Busca nao retornou resultados")
        SkillRunRepo.create(
            user_id,
            audit_skill_name,
            "completed",
            input_data,
            output_summary=result,
        )
        return build_runtime_context(skill_name, result)
    except Exception as exc:
        SkillRunRepo.create(
            user_id,
            audit_skill_name,
            "failed",
            input_data,
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
