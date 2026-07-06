"""Helpers for endpoints that require an authenticated user."""

from src.core.auth import decode_access_token
from src.db.repository import UserRepo


def resolve_authorized_user(authorization: str | None):
    """Return the active user from a Bearer token, or None when auth is missing/invalid."""
    if not authorization:
        return None
    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    payload = decode_access_token(token.strip())
    if not payload:
        return None

    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        return None
    return UserRepo.get(user_id)
