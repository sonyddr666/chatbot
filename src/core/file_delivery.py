"""Resolve explicit requests to return a user-owned file in the chat."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

from src.core.skill_permissions import can_execute_skill
from src.core.userspace import safe_user_path
from src.db.repository import ChatAttachmentRepo, SkillRepo


DELIVERY_ACTIONS = (
    "anexa",
    "anexar",
    "anexe",
    "devolve",
    "devolver",
    "devolva",
    "entrega",
    "entregar",
    "entregue",
    "envia",
    "enviar",
    "envie",
    "manda",
    "mandar",
    "mande",
    "passa",
    "passar",
    "passe",
    "receber",
    "reenvia",
    "reenviar",
    "reenvie",
)
FILE_TARGETS = (
    "arquivo",
    "anexo",
    "documento",
    "foto",
    "imagem",
    "planilha",
    "pdf",
)
UPLOAD_HINTS = ("anexei", "de volta", "enviei", "mandei", "reenv", "upload", "upei")
WORKSPACE_HINTS = ("criado", "criou", "gerado", "gerou", "workspace", "work")
CREATE_ACTIONS = ("cria", "criar", "crie", "gera", "gerar", "gere")
EXPLICIT_FILE_COMMAND = re.compile(r"^\s*@(arquivo|file)(?::send)?(?:\s+(.+))?\s*$", re.IGNORECASE)
FILE_EXTENSION = re.compile(r"\b[^\s/\\]+\.[a-z0-9]{1,12}\b", re.IGNORECASE)
RESEARCH_WORD = re.compile(
    r"\b(?:pesquisa|pesquise|pesquisar|busca|busque|buscar|procure|procurar|google|internet|web)\b",
    re.IGNORECASE,
)
IGNORED_WORKSPACE_PARTS = frozenset({".git", ".codex", "node_modules", "__pycache__"})


@dataclass(frozen=True)
class FileDeliverySelection:
    source: str
    filename: str
    relative_path: str
    attachment_id: str | None = None


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def requests_file_delivery(message: str) -> bool:
    """Require explicit send intent so ordinary file discussion never triggers delivery."""
    normalized = _normalize(message)
    if EXPLICIT_FILE_COMMAND.match(message or ""):
        return True
    if RESEARCH_WORD.search(normalized):
        return False

    action_matches = [
        match
        for action in DELIVERY_ACTIONS
        for match in re.finditer(rf"\b{re.escape(action)}\b", normalized)
    ]
    target_matches = [
        match
        for target in FILE_TARGETS
        for match in re.finditer(rf"\b{re.escape(target)}s?\b", normalized)
    ]
    target_matches.extend(FILE_EXTENSION.finditer(normalized))
    explicit_pair = any(
        abs(action.start() - target.start()) <= 80
        for action in action_matches
        for target in target_matches
    )
    if not explicit_pair:
        return False

    # "Crie/Gere e envie" still belongs to the confirmed Workspace creation flow.
    has_create_action = any(re.search(rf"\b{re.escape(action)}\b", normalized) for action in CREATE_ACTIONS)
    return not has_create_action


def _skill_enabled(user_id: int) -> bool:
    return any(
        skill.get("name") == "file_delivery"
        and can_execute_skill(skill, "workspace_read")
        for skill in SkillRepo.list_for_user(user_id)
    )


def _workspace_candidates(user_id: int, limit: int = 300) -> list[FileDeliverySelection]:
    root = safe_user_path(user_id, "workspace").resolve()
    candidates: list[tuple[float, FileDeliverySelection]] = []
    visited = 0
    for path in root.rglob("*"):
        visited += 1
        if visited > 5000:
            break
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        parts = Path(relative).parts
        if any(part in IGNORED_WORKSPACE_PARTS or part.startswith(".") for part in parts):
            continue
        if len(parts) >= 2 and parts[0] == "chat" and parts[1] == "uploads":
            continue
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((modified, FileDeliverySelection("workspace", path.name, relative)))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [selection for _, selection in candidates[:limit]]


def _attachment_candidates(user_id: int, session_id: str) -> list[FileDeliverySelection]:
    candidates: list[FileDeliverySelection] = []
    for item in ChatAttachmentRepo.list_owned_for_delivery(user_id, session_id):
        try:
            path = safe_user_path(user_id, "workspace", str(item["relative_path"]))
            if not path.exists() or not path.is_file():
                continue
        except (OSError, ValueError):
            continue
        candidates.append(FileDeliverySelection(
            source="upload",
            filename=str(item["filename"]),
            relative_path=str(item["relative_path"]),
            attachment_id=str(item["id"]),
        ))
    return candidates


def _candidate_score(message: str, candidate: FileDeliverySelection) -> int:
    normalized_message = _normalize(message)
    normalized_name = _normalize(candidate.filename)
    normalized_path = _normalize(candidate.relative_path)
    stem = _normalize(Path(candidate.filename).stem)
    score = 0
    if normalized_name and normalized_name in normalized_message:
        score += 200
    if normalized_path and normalized_path in normalized_message:
        score += 240
    if len(stem) >= 3 and stem in normalized_message:
        score += 120
    if candidate.source == "upload" and any(hint in normalized_message for hint in UPLOAD_HINTS):
        score += 35
    if candidate.source == "workspace" and any(hint in normalized_message for hint in WORKSPACE_HINTS):
        score += 35
    return score


def resolve_file_delivery(
    user_id: int,
    session_id: str,
    message: str,
    *,
    require_intent: bool = True,
    require_skill: bool = True,
) -> FileDeliverySelection | None:
    """Choose one safe file, preferring an explicitly named path and current-chat uploads."""
    if require_intent and not requests_file_delivery(message):
        return None
    if require_skill and not _skill_enabled(user_id):
        return None

    uploads = _attachment_candidates(user_id, session_id)
    workspace = _workspace_candidates(user_id)
    candidates = uploads + workspace
    if not candidates:
        return None

    scored = [(_candidate_score(message, candidate), index, candidate) for index, candidate in enumerate(candidates)]
    best_score, _, best = max(scored, key=lambda item: (item[0], -item[1]))
    if best_score > 0:
        return best

    normalized = _normalize(message)
    if any(hint in normalized for hint in WORKSPACE_HINTS) and workspace:
        return workspace[0]
    if uploads:
        return uploads[0]
    return workspace[0] if workspace else None
