"""Safe per-user workspace file operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import unicodedata

from src.core.userspace import safe_user_path


MAX_TEXT_FILE_BYTES = 1024 * 1024
MAX_SEARCH_VISITS = 5000
IGNORED_SEARCH_PARTS = frozenset({".git", ".codex", "node_modules", "__pycache__"})
IMAGE_EXTENSIONS = frozenset({".avif", ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".svg", ".webp"})
DOCUMENT_EXTENSIONS = frozenset({".csv", ".doc", ".docx", ".md", ".odt", ".pdf", ".ppt", ".pptx", ".rtf", ".txt", ".xls", ".xlsx"})
SEARCH_STOPWORDS = frozenset({
    "a", "ache", "achar", "arquivo", "arquivos", "busca", "buscar", "busque", "de", "dentro",
    "do", "dos", "encontre", "encontrar", "eu", "imagem", "imagens", "local", "locais", "meu",
    "meus", "minha", "minhas", "no", "nos", "o", "os", "procure", "procurar", "seu", "seus",
    "sistema", "tenta", "tente", "uma", "workspace",
})


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


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def search_files(user_id: int, query: str, limit: int = 25) -> list[WorkspaceNode]:
    """Find user-owned Workspace files by name/path and broad file category."""
    root = _workspace_path(user_id).resolve()
    if not root.exists():
        return []

    normalized = _fold(query)
    wants_images = bool(re.search(r"\b(?:foto|fotos|imagem|imagens|image|images)\b", normalized))
    wants_documents = bool(re.search(r"\b(?:documento|documentos|doc|docs|pdf|planilha|planilhas)\b", normalized))
    terms = [
        word for word in re.findall(r"[a-z0-9_.-]+", normalized)
        if len(word) > 1 and word not in SEARCH_STOPWORDS
    ]

    matches: list[tuple[int, str, WorkspaceNode]] = []
    visited = 0
    for path in root.rglob("*"):
        visited += 1
        if visited > MAX_SEARCH_VISITS:
            break
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        if any(part in IGNORED_SEARCH_PARTS or part.startswith(".") for part in Path(relative).parts):
            continue

        extension = path.suffix.lower()
        if wants_images and extension not in IMAGE_EXTENSIONS:
            continue
        if wants_documents and not wants_images and extension not in DOCUMENT_EXTENSIONS:
            continue

        folded_path = _fold(relative)
        if terms and not all(term in folded_path for term in terms):
            continue
        score = (100 if wants_images or wants_documents else 0) + sum(20 for term in terms if term in folded_path)
        if terms and any(_fold(path.stem) == term for term in terms):
            score += 40
        node = WorkspaceNode(name=path.name, path=relative, kind="file", size=path.stat().st_size)
        matches.append((score, folded_path, node))

    matches.sort(key=lambda item: (-item[0], item[1]))
    return [node for _, _, node in matches[:max(1, min(limit, 100))]]


def grep_workspace(
    user_id: int,
    query: str,
    path: str = "",
    *,
    limit: int = 50,
) -> list[dict]:
    """Search literal text only inside bounded, user-owned Workspace files."""
    needle = (query or "").strip()
    if not needle:
        raise ValueError("Texto de busca nao pode ser vazio")
    if len(needle) > 500:
        raise ValueError("Texto de busca muito grande")
    root = _workspace_path(user_id, path).resolve()
    workspace_root = _workspace_path(user_id).resolve()
    if not root.exists():
        raise FileNotFoundError(path)
    if root != workspace_root and workspace_root not in root.parents:
        raise ValueError("Caminho fora do Workspace")
    candidates = [root] if root.is_file() else root.rglob("*")
    folded_needle = _fold(needle)
    results: list[dict] = []
    visited = 0
    for candidate in candidates:
        visited += 1
        if visited > MAX_SEARCH_VISITS or len(results) >= max(1, min(limit, 200)):
            break
        if not candidate.is_file() or candidate.is_symlink():
            continue
        relative = candidate.resolve().relative_to(workspace_root).as_posix()
        if any(part in IGNORED_SEARCH_PARTS or part.startswith(".") for part in Path(relative).parts):
            continue
        try:
            if candidate.stat().st_size > MAX_TEXT_FILE_BYTES:
                continue
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, 1):
            if folded_needle in _fold(line):
                results.append({"path": relative, "line": number, "text": line.strip()[:500]})
                if len(results) >= max(1, min(limit, 200)):
                    break
    return results


def read_text_file(user_id: int, path: str) -> str:
    _require_relative_path(path, "Caminho do arquivo nao pode ser vazio")
    file_path = _workspace_path(user_id, path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(path)
    if file_path.stat().st_size > MAX_TEXT_FILE_BYTES:
        raise ValueError("Arquivo muito grande para leitura textual")
    return file_path.read_text(encoding="utf-8")


def resolve_workspace_file(user_id: int, path: str) -> Path:
    """Resolve an existing user-owned file for authenticated preview or download."""
    _require_relative_path(path, "Caminho do arquivo nao pode ser vazio")
    file_path = _workspace_path(user_id, path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(path)
    return file_path


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
