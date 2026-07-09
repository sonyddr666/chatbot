"""Central permission checks for user-enabled skills."""

from __future__ import annotations


def skill_permissions(skill: dict) -> dict:
    """Read the declared capability flags while remaining compatible with old rows."""
    definition = skill.get("definition") or {}
    permissions = definition.get("permissions") or {}
    return permissions if isinstance(permissions, dict) else {}


def can_execute_skill(skill: dict, required_permission: str | None = None) -> bool:
    """Allow only enabled skills whose declared capability is safe to execute."""
    if not skill.get("enabled"):
        return False
    permissions = skill_permissions(skill)
    if skill.get("requires_shell") or permissions.get("shell"):
        return False
    if required_permission and not permissions.get(required_permission, False):
        return False
    return True


def executable_skill_names(skills: list[dict] | tuple[dict, ...]) -> set[str]:
    return {str(skill.get("name", "")) for skill in skills if can_execute_skill(skill)}
