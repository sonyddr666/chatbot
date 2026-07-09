"""Upload persistence and text extraction for personal RAG ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
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


def write_rag_manifest(
    user_id: int,
    *,
    document_id: int | None,
    filename: str,
    source: str,
    status: str,
    parser: str,
    chunk_count: int,
    file_size: int,
    vector_ids: list[str] | None = None,
    upload_path: str = "",
    checksum: str = "",
    error_message: str = "",
    metadata: dict | None = None,
) -> str:
    safe_name = sanitize_upload_filename(filename)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    manifest_name = f"{stamp}-{uuid4().hex[:10]}-{Path(safe_name).stem}.json"
    relative_path = manifest_name
    manifest_path = safe_user_path(user_id, "rag", f"manifests/{relative_path}")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "document_id": document_id,
        "user_id": user_id,
        "filename": safe_name,
        "source": source,
        "status": status,
        "parser": parser,
        "chunk_count": chunk_count,
        "file_size": file_size,
        "vector_ids": vector_ids or [],
        "upload_path": upload_path,
        "checksum": checksum,
        "error_message": error_message,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return f"manifests/{relative_path}"


def extract_text_for_ingestion(filename: str, content: bytes) -> str:
    safe_name = sanitize_upload_filename(filename)
    ext = upload_extension(safe_name)
    if ext in TEXT_EXTENSIONS:
        return content.decode("utf-8", errors="replace")
    if ext == ".pdf":
        return _extract_pdf_text(content)
    if ext == ".docx":
        return _extract_docx_text(content)
    raise ValueError(f"Extensao nao suportada: {ext}")


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        raise ValueError("Falha ao extrair texto do PDF") from exc

    text = "\n\n".join(page for page in pages if page)
    if not text.strip():
        raise ValueError("PDF nao contem texto extraivel")
    return text


def _extract_docx_text(content: bytes) -> str:
    try:
        from docx import Document

        document = Document(BytesIO(content))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    except Exception as exc:
        raise ValueError("Falha ao extrair texto do DOCX") from exc

    text = "\n".join(paragraphs)
    if not text.strip():
        raise ValueError("DOCX nao contem texto extraivel")
    return text
