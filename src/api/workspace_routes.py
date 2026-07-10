"""Authenticated REST routes for per-user workspace files."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from src.api.schemas import (
    WorkspaceFileResponse,
    WorkspaceInfoResponse,
    WorkspacePatchApplyRequest,
    WorkspacePatchApplyResponse,
    WorkspacePatchPreviewRequest,
    WorkspacePatchPreviewResponse,
    WorkspaceAgentPlanRequest,
    WorkspaceMoveRequest,
    WorkspacePathRequest,
    WorkspaceTreeResponse,
    WorkspaceWriteRequest,
)
from src.core.auth_required import resolve_authorized_user
from src.core.workspace import (
    delete_path,
    list_tree,
    mkdir,
    move_path,
    read_text_file,
    write_text_file,
)
from src.core.patcher import apply_workspace_patch, preview_workspace_patch
from src.core.user_provider_manager import get_active_config_for_user
from src.core.workspace_agent import (
    apply_workspace_plan,
    cancel_workspace_plan,
    create_workspace_plan,
    get_workspace_plan,
)
from src.core.workspace_rag import ingest_selected_workspace_file


router = APIRouter(prefix="/workspace", tags=["workspace"])


async def get_current_user(authorization: str | None = Header(default=None)):
    user = resolve_authorized_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Nao autenticado")
    return user


def _workspace_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail="Caminho nao encontrado")
    if isinstance(exc, FileExistsError):
        return HTTPException(status_code=409, detail="Destino ja existe")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Erro no workspace")


@router.post("/ai/plan")
async def workspace_ai_plan(body: WorkspaceAgentPlanRequest, user=Depends(get_current_user)):
    if not body.instruction.strip():
        raise HTTPException(status_code=400, detail="Instrucao nao pode ser vazia")
    try:
        provider_config = get_active_config_for_user(user.id)
        return await create_workspace_plan(user.id, body.instruction.strip(), provider_config)
    except Exception as exc:
        raise _workspace_error(exc)


@router.get("/ai/plans/{plan_id}")
async def workspace_ai_get_plan(plan_id: str, user=Depends(get_current_user)):
    try:
        return get_workspace_plan(user.id, plan_id)
    except Exception as exc:
        raise _workspace_error(exc)


@router.post("/ai/plans/{plan_id}/apply")
async def workspace_ai_apply_plan(plan_id: str, user=Depends(get_current_user)):
    try:
        return apply_workspace_plan(user.id, plan_id)
    except Exception as exc:
        raise _workspace_error(exc)


@router.delete("/ai/plans/{plan_id}")
async def workspace_ai_cancel_plan(plan_id: str, user=Depends(get_current_user)):
    try:
        return cancel_workspace_plan(user.id, plan_id)
    except Exception as exc:
        raise _workspace_error(exc)


@router.post("/rag/ingest")
async def workspace_rag_ingest(body: WorkspacePathRequest, user=Depends(get_current_user)):
    """Add only the explicitly selected workspace file to personal RAG."""
    try:
        return ingest_selected_workspace_file(user.id, body.path)
    except Exception as exc:
        raise _workspace_error(exc)


@router.get("/tree", response_model=WorkspaceTreeResponse)
async def workspace_tree(path: str = "", user=Depends(get_current_user)):
    try:
        nodes = list_tree(user.id, path)
        return {"path": path, "nodes": nodes}
    except Exception as exc:
        raise _workspace_error(exc)


@router.get("/file", response_model=WorkspaceFileResponse)
async def workspace_read_file(path: str, user=Depends(get_current_user)):
    try:
        return {"path": path, "content": read_text_file(user.id, path)}
    except Exception as exc:
        raise _workspace_error(exc)


@router.put("/file", response_model=WorkspaceInfoResponse)
async def workspace_write_file(body: WorkspaceWriteRequest, user=Depends(get_current_user)):
    try:
        return write_text_file(user.id, body.path, body.content)
    except Exception as exc:
        raise _workspace_error(exc)


@router.post("/mkdir", response_model=WorkspaceInfoResponse)
async def workspace_mkdir(body: WorkspacePathRequest, user=Depends(get_current_user)):
    try:
        return mkdir(user.id, body.path)
    except Exception as exc:
        raise _workspace_error(exc)


@router.delete("/path")
async def workspace_delete_path(path: str, recursive: bool = False, user=Depends(get_current_user)):
    try:
        deleted = delete_path(user.id, path, recursive=recursive)
        return {"deleted": deleted, "path": path}
    except Exception as exc:
        raise _workspace_error(exc)


@router.post("/move", response_model=WorkspaceInfoResponse)
async def workspace_move_path(body: WorkspaceMoveRequest, user=Depends(get_current_user)):
    try:
        return move_path(user.id, body.source, body.target)
    except Exception as exc:
        raise _workspace_error(exc)


@router.post("/patch/preview", response_model=WorkspacePatchPreviewResponse)
async def workspace_patch_preview(body: WorkspacePatchPreviewRequest, user=Depends(get_current_user)):
    try:
        return preview_workspace_patch(user.id, body.path, body.content)
    except Exception as exc:
        raise _workspace_error(exc)


@router.post("/patch/apply", response_model=WorkspacePatchApplyResponse)
async def workspace_patch_apply(body: WorkspacePatchApplyRequest, user=Depends(get_current_user)):
    try:
        return apply_workspace_patch(user.id, body.path, body.content, body.expected_checksum)
    except Exception as exc:
        raise _workspace_error(exc)
