"""Per-user filesystem roots with strict path safety."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from src.config import settings


ALLOWED_AREAS = frozenset({"profile", "workspace", "uploads", "rag", "skills"})


@dataclass(frozen=True)
class UserSpacePaths:
    user_id: int
    root: Path
    profile: Path
    workspace: Path
    uploads: Path
    rag: Path
    skills: Path


def _base_dir() -> Path:
    return Path(settings.user_data_dir).expanduser().resolve()


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id invalido")
    return user_id


def get_user_root(user_id: int) -> Path:
    """Return the canonical root directory for one user."""
    return _base_dir() / str(_validate_user_id(user_id))


def ensure_user_space(user_id: int) -> UserSpacePaths:
    """Create and return the standard per-user directory layout."""
    root = get_user_root(user_id)
    paths = UserSpacePaths(
        user_id=user_id,
        root=root,
        profile=root / "profile",
        workspace=root / "workspace",
        uploads=root / "uploads",
        rag=root / "rag",
        skills=root / "skills",
    )

    for path in (
        paths.profile,
        paths.workspace,
        paths.uploads / "original",
        paths.rag / "documents",
        paths.rag / "extracted",
        paths.rag / "manifests",
        paths.skills / "user",
        paths.skills / "audit",
    ):
        path.mkdir(parents=True, exist_ok=True)

    return paths


def _reject_unsafe_relative_path(relative_path: str) -> Path:
    raw = (relative_path or "").strip()
    if not raw:
        return Path()

    candidate = Path(raw)
    windows_candidate = PureWindowsPath(raw)
    if candidate.is_absolute() or windows_candidate.is_absolute():
        raise ValueError("Caminho absoluto nao permitido")

    if any(part in {"..", ""} for part in candidate.parts):
        raise ValueError("Caminho relativo inseguro")

    return candidate


def safe_user_path(user_id: int, area: str, relative_path: str = "") -> Path:
    """Resolve a user path and guarantee it stays inside the requested area."""
    if area not in ALLOWED_AREAS:
        raise ValueError("Area de usuario desconhecida")

    paths = ensure_user_space(user_id)
    area_root = getattr(paths, area).resolve()
    relative = _reject_unsafe_relative_path(relative_path)
    resolved = (area_root / relative).resolve()

    if resolved != area_root and area_root not in resolved.parents:
        raise ValueError("Caminho fora da area permitida")

    return resolved


def write_profile_text(user_id: int, filename: str, content: str) -> Path:
    """Write a UTF-8 profile file inside the user's profile area."""
    path = safe_user_path(user_id, "profile", filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
