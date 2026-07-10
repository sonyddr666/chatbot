"""Explicit ingestion of selected workspace files into personal RAG."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.core.ingestion import save_extracted_text, write_rag_manifest
from src.core.userspace import safe_user_path
from src.core.workspace import read_text_file
from src.db.repository import DocumentRepo
from src.rag.chunker import split_text
from src.rag.personal import add_user_documents, delete_user_documents


def _remove_derived_file(user_id: int, relative_path: str) -> None:
    if not relative_path:
        return
    try:
        target = safe_user_path(user_id, "rag", relative_path)
    except ValueError:
        return
    if target.is_file():
        target.unlink()


def _replace_previous_workspace_versions(user_id: int, path: str, keep_document_id: int) -> None:
    for stale in DocumentRepo.list_by_source(user_id, "workspace"):
        if stale.id == keep_document_id or stale.filename != path:
            continue
        try:
            vector_ids = json.loads(stale.vector_ids_json or "[]")
        except json.JSONDecodeError:
            vector_ids = []
        if vector_ids:
            delete_user_documents(user_id, vector_ids)
        _remove_derived_file(user_id, stale.extracted_path or "")
        _remove_derived_file(user_id, stale.manifest_path or "")
        DocumentRepo.delete(stale.id, user_id)


def ingest_selected_workspace_file(user_id: int, path: str) -> dict:
    """Index one explicitly selected text file, leaving the workspace source untouched."""
    text = read_text_file(user_id, path)
    if not text.strip():
        raise ValueError("Arquivo vazio nao pode ser adicionado ao RAG")

    chunks = split_text(text)
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    metadata = [{"source": "workspace", "workspace_path": path, "checksum": checksum}] * len(chunks)
    vector_ids: list[str] = []
    extracted_path = ""
    doc = None
    try:
        vector_ids = add_user_documents(user_id, chunks, metadatas=metadata)
        extracted_path = save_extracted_text(user_id, Path(path).name, text)
        doc = DocumentRepo.save(
            path,
            "workspace",
            len(chunks),
            len(text.encode("utf-8")),
            user_id=user_id,
            checksum=checksum,
            status="indexed",
            parser=Path(path).suffix.lower().lstrip(".") or "text",
            vector_ids=vector_ids,
            extracted_path=extracted_path,
        )
        manifest_path = write_rag_manifest(
            user_id,
            document_id=doc.id,
            filename=path,
            source="workspace",
            status="indexed",
            parser=doc.parser,
            chunk_count=len(chunks),
            file_size=doc.file_size,
            vector_ids=vector_ids,
            metadata={"workspace_path": path, "checksum": checksum, "selected_by_user": True},
        )
        DocumentRepo.set_manifest_path(doc.id, user_id, manifest_path)
    except Exception:
        if vector_ids:
            delete_user_documents(user_id, vector_ids)
        _remove_derived_file(user_id, extracted_path)
        if doc is not None:
            DocumentRepo.delete(doc.id, user_id)
        raise
    _replace_previous_workspace_versions(user_id, path, doc.id)
    return {
        "document_id": doc.id,
        "path": path,
        "source": "workspace",
        "status": "indexed",
        "chunks": len(chunks),
        "ids": vector_ids,
        "extracted_path": extracted_path,
        "manifest_path": manifest_path,
        "checksum": checksum,
    }
