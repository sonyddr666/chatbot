"""Safe per-user workspace file operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from src.core.userspace import safe_user_path


MAX_TEXT_FILE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class WorkspaceNode:
    name: str
    path: str
    kind: str
    size: int


@dataclass(frozen=True)
class WorkspaceFileInfo:
    name: str
    path: str
    kind: str
    size: int


def _workspace_path(user_id: int, relative_path: str = "") -> Path:
    return safe_user_path(user_id, "workspace", relative_path)


def _require_relative_path(path: str, message: str) -> None:
    if not (path or "").strip():
        raise ValueError(message)


def _relative_workspace_path(user_id: int, path: Path) -> str:
    root = _workspace_path(user_id).resolve()
    return path.resolve().relative_to(root).as_posix()


def _info(user_id: int, path: Path) -> WorkspaceFileInfo:
    kind = "folder" if path.is_dir() else "file"
    size = 0 if path.is_dir() else path.stat().st_size
    return WorkspaceFileInfo(
        name=path.name,
        path=_relative_workspace_path(user_id, path),
        kind=kind,
        size=size,
    )


def list_tree(user_id: int, path: str = "") -> list[WorkspaceNode]:
    folder = _workspace_path(user_id, path)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ValueError("Caminho nao e uma pasta")

    nodes = []
    for child in sorted(folder.iterdir(), key=lambda item: (not item.is_file(), item.name.lower())):
        kind = "folder" if child.is_dir() else "file"
        nodes.append(
            WorkspaceNode(
                name=child.name,
                path=_relative_workspace_path(user_id, child),
                kind=kind,
                size=0 if child.is_dir() else child.stat().st_size,
            )
        )
    return nodes


def read_text_file(user_id: int, path: str) -> str:
    _require_relative_path(path, "Caminho do arquivo nao pode ser vazio")
    file_path = _workspace_path(user_id, path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(path)
    if file_path.stat().st_size > MAX_TEXT_FILE_BYTES:
        raise ValueError("Arquivo muito grande para leitura textual")
    return file_path.read_text(encoding="utf-8")


def write_text_file(user_id: int, path: str, content: str) -> WorkspaceFileInfo:
    _require_relative_path(path, "Caminho do arquivo nao pode ser vazio")
    data = content.encode("utf-8")
    if len(data) > MAX_TEXT_FILE_BYTES:
        raise ValueError("Arquivo muito grande para escrita textual")

    file_path = _workspace_path(user_id, path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return _info(user_id, file_path)


def mkdir(user_id: int, path: str) -> WorkspaceFileInfo:
    _require_relative_path(path, "Caminho da pasta nao pode ser vazio")
    folder = _workspace_path(user_id, path)
    folder.mkdir(parents=True, exist_ok=True)
    return _info(user_id, folder)


def delete_path(user_id: int, path: str, recursive: bool = False) -> bool:
    _require_relative_path(path, "Nao e permitido deletar a raiz do workspace")
    target = _workspace_path(user_id, path)
    if not target.exists():
        return False
    if target.is_dir():
        if recursive:
            shutil.rmtree(target)
            return True
        try:
            target.rmdir()
        except OSError as exc:
            raise ValueError("Pasta nao esta vazia") from exc
        return True
    target.unlink()
    return True


def move_path(user_id: int, source: str, target: str) -> WorkspaceFileInfo:
    _require_relative_path(source, "Nao e permitido mover a raiz do workspace")
    _require_relative_path(target, "Destino do workspace nao pode ser vazio")
    source_path = _workspace_path(user_id, source)
    target_path = _workspace_path(user_id, target)
    if not source_path.exists():
        raise FileNotFoundError(source)
    if source_path == target_path or source_path in target_path.parents:
        raise ValueError("Nao e permitido mover uma pasta para dentro dela mesma")
    if target_path.exists():
        raise FileExistsError(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_path), str(target_path))
    return _info(user_id, target_path)
