"""Upload persistence and text extraction for personal RAG ingestion."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from src.core.userspace import safe_user_path


TEXT_EXTENSIONS = frozenset({".txt", ".md", ".csv", ".json"})
PARSER_REQUIRED_EXTENSIONS = frozenset({".pdf", ".docx"})
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PARSER_REQUIRED_EXTENSIONS


@dataclass(frozen=True)
class UploadArtifact:
    user_id: int
    original_filename: str
    extension: str
    size: int
    checksum: str
    storage_path: Path
    relative_path: str


def sanitize_upload_filename(filename: str) -> str:
    raw = (filename or "").strip()
    if not raw:
        raise ValueError("Nome de arquivo invalido")

    # Treat both POSIX and Windows separators as untrusted path components.
    name = PureWindowsPath(raw.replace("\\", "/")).name
    name = Path(name).name
    if not name or name in {".", ".."}:
        raise ValueError("Nome de arquivo invalido")
    return name


def upload_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def save_upload_original(user_id: int, filename: str, content: bytes) -> UploadArtifact:
    safe_name = sanitize_upload_filename(filename)
    ext = upload_extension(safe_name)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Extensao nao suportada: {ext}")

    upload_id = uuid4().hex
    relative_path = f"original/{upload_id}/{safe_name}"
    storage_path = safe_user_path(user_id, "uploads", relative_path)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)

    return UploadArtifact(
        user_id=user_id,
        original_filename=safe_name,
        extension=ext,
        size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        storage_path=storage_path,
        relative_path=relative_path,
    )


def extract_text_for_ingestion(filename: str, content: bytes) -> str:
    safe_name = sanitize_upload_filename(filename)
    ext = upload_extension(safe_name)
    if ext in TEXT_EXTENSIONS:
        return content.decode("utf-8", errors="replace")
    if ext in PARSER_REQUIRED_EXTENSIONS:
        raise ValueError(f"Parser para {ext} ainda nao disponivel nesta instalacao")
    raise ValueError(f"Extensao nao suportada: {ext}")
