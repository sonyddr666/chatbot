"""Approved workspace patch previews and guarded applies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import difflib
import hashlib
from pathlib import PurePosixPath

from src.core.userspace import safe_user_path
from src.core.workspace import read_text_file, write_text_file


@dataclass(frozen=True)
class WorkspacePatchPreview:
    path: str
    expected_checksum: str
    new_checksum: str
    diff: str


@dataclass(frozen=True)
class WorkspacePatchResult:
    path: str
    applied: bool
    checksum: str
    snapshot_path: str


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _diff(path: str, current: str, proposed: str) -> str:
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _snapshot_relative_path(path: str) -> str:
    clean_name = PurePosixPath(path).name or "file.txt"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]
    return f".snapshots/{stamp}-{digest}-{clean_name}"


def preview_workspace_patch(user_id: int, path: str, new_content: str) -> WorkspacePatchPreview:
    current = read_text_file(user_id, path)
    return WorkspacePatchPreview(
        path=path,
        expected_checksum=_checksum(current),
        new_checksum=_checksum(new_content),
        diff=_diff(path, current, new_content),
    )


def apply_workspace_patch(
    user_id: int,
    path: str,
    new_content: str,
    expected_checksum: str,
) -> WorkspacePatchResult:
    current = read_text_file(user_id, path)
    current_checksum = _checksum(current)
    if current_checksum != expected_checksum:
        raise ValueError("Arquivo mudou depois do preview; gere um novo patch")

    snapshot_path = _snapshot_relative_path(path)
    snapshot_file = safe_user_path(user_id, "workspace", snapshot_path)
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    snapshot_file.write_text(current, encoding="utf-8")

    info = write_text_file(user_id, path, new_content)
    return WorkspacePatchResult(
        path=info.path,
        applied=True,
        checksum=_checksum(new_content),
        snapshot_path=snapshot_path,
    )
