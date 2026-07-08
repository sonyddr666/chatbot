"""Central permission checks for user-enabled skills."""

from __future__ import annotations


def can_execute_skill(skill: dict) -> bool:
    """Allow only explicitly enabled skills that do not require shell access."""
    if not skill.get("enabled"):
        return False
    if skill.get("requires_shell"):
        return False
    return True


def executable_skill_names(skills: list[dict] | tuple[dict, ...]) -> set[str]:
    return {str(skill.get("name", "")) for skill in skills if can_execute_skill(skill)}
