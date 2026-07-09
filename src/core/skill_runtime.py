"""Runtime seguro para skills habilitadas por usuario."""

from __future__ import annotations

from collections.abc import Iterable

from src.db.repository import SkillRepo, SkillRunRepo
from src.core.skill_permissions import executable_skill_names
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


def _enabled_names(skills: Iterable[dict]) -> set[str]:
    return executable_skill_names(list(skills))


def should_force_rag(skills: Iterable[dict]) -> bool:
    """A skill personal_rag faz o chat sempre consultar o RAG pessoal."""
    return "personal_rag" in _enabled_names(skills)


def should_run_web_search(message: str, skills: Iterable[dict]) -> bool:
    """Executa busca web somente quando skill e intencao de busca existem."""
    enabled = _enabled_names(skills)
    if not (enabled & SEARCH_SKILLS):
        return False
    msg = message.lower()
    return any(trigger in msg for trigger in SEARCH_TRIGGERS)


def build_runtime_context(skill_name: str, result: str | None) -> str:
    if not result:
        return ""
    return (
        f"Resultado da skill {skill_name}:\n"
        f"{result}\n\n"
        "Use este resultado como contexto auxiliar e cite fontes/titulos quando disponiveis."
    )


async def run_enabled_skill_context(user_id: int, message: str) -> str:
    """Executa skills seguras habilitadas para o usuario e retorna contexto."""
    skills = SkillRepo.list_for_user(user_id)
    sections: list[str] = []

    if should_run_web_search(message, skills):
        try:
            result = await web_search(message, max_results=3)
            SkillRunRepo.create(
                user_id,
                "web_search",
                "completed",
                {"message": message, "max_results": 3},
                output_summary=result or "",
            )
            context = build_runtime_context("web_search", result)
            if context:
                sections.append(context)
        except Exception as exc:
            SkillRunRepo.create(
                user_id,
                "web_search",
                "failed",
                {"message": message, "max_results": 3},
                error_message=str(exc),
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
