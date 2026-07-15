"""Central authorization policy for provider-neutral agent tools."""

from __future__ import annotations

from src.core.agent.schemas import ToolDefinition
from src.db.repository import UserRepo


def is_active_admin(user_id: int) -> bool:
    user = UserRepo.get(user_id)
    return bool(user and user.is_active and user.registration_status == "approved" and user.is_admin)


def authorize_tool(user_id: int, definition: ToolDefinition) -> None:
    """Reject forged or stale admin-only calls at execution time."""
    if definition.permission.startswith("admin:") and not is_active_admin(user_id):
        raise PermissionError("Ferramenta disponivel somente para administrador")
