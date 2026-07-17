"""Rotas da API REST — versão completa com todas as features."""

import os
import json
import hashlib
import asyncio
import time
import httpx
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, UploadFile, File, Form, Request, Query, Depends, Header
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.schemas import (
    ChatRequest, ChatResponse, ChatStreamRequest,
    IngestRequest, IngestResponse, FeedbackRequest, StatsResponse,
    ConversationResponse, RegisterRequest, LoginRequest, AuthResponse, UserResponse,
    RegistrationResponse, AdminUserResponse,
    OnboardingRequest, SkillToggleRequest, PreferenceUpdateRequest, PreferenceSuggestionResolveRequest,
)
from src.core.memory import get_session
from src.core.chat import ChatEngine
from src.core.moderation import moderate_text, moderate_with_api
from src.core.multilang import detect_language, build_system_prompt_multilang
from src.core.feedback import FeedbackManager
from src.core.metrics import MESSAGES_TOTAL, ERRORS_TOTAL, DOCUMENTS_INGESTED, ACTIVE_SESSIONS, get_metrics
from src.core.cache import cache_llm_response, get_cached_llm_response
from src.core.classifier import classify_route
from src.core.llm import get_llm
from src.core.response_modes import normalize_reasoning_effort, normalize_response_mode, response_mode_status
from src.core.skill_runtime import run_enabled_skill_context, runtime_skill_activity, user_has_personal_rag
from src.core.workspace_agent import create_workspace_plan, model_requests_workspace, workspace_plan_message, workspace_plan_status_context
from src.core.preference_suggestions import create_suggestion_from_message
from src.core.user_provider_manager import (
    activate_builtin_for_user,
    activate_user_provider,
    create_user_provider,
    export_user_providers,
    get_active_config_for_user,
    import_user_providers,
    list_user_providers,
    metadata_from_config,
    use_global_provider,
)
from src.rag.chunker import split_text, split_documents
from src.rag.personal import add_user_documents, delete_user_documents, retrieve_user_context, user_rag_collection
from src.db.repository import ChatAttachmentRepo, ChatJobRepo, ConversationRepo, DocumentRepo, MessageRepo, PreferenceSuggestionRepo, UserRepo, SkillRepo, SkillRunRepo, UserPreferenceRepo
from src.db.models import init_db as _init_db
from src.config import settings
from src.core.auth import create_access_token
from src.core.auth_required import resolve_authorized_user
from src.core.ingestion import SUPPORTED_EXTENSIONS, extract_text_for_ingestion, save_extracted_text, save_upload_original, write_rag_manifest
from src.core.userspace import safe_user_path, write_profile_text
from src.core.time_utils import utc_isoformat
from src.tools.perplexo_search import perplexo_health
from src.core.chat_jobs import cancel_chat_job, start_chat_job
from src.core.chat_attachments import (
    MAX_CHAT_ATTACHMENTS,
    remove_chat_attachment_file,
    save_chat_attachment,
)

router = APIRouter()
_SLOWAPI_CONFIG = os.path.join(os.path.dirname(__file__), "slowapi.env")
limiter = Limiter(key_func=get_remote_address, config_filename=_SLOWAPI_CONFIG)
feedback_mgr = FeedbackManager()
_db_initialized = False


def ensure_db():
    global _db_initialized
    if not _db_initialized:
        _init_db()
        UserRepo.ensure_initial_admin()
        SkillRepo.ensure_defaults()
        _db_initialized = True


def _user_response(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=user.display_name or user.username,
        is_admin=bool(user.is_admin),
    )


def _admin_user_response(user) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=user.display_name or user.username,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        registration_status=user.registration_status or "approved",
        created_at=utc_isoformat(user.created_at),
        approved_at=utc_isoformat(user.approved_at) if user.approved_at else None,
        approved_by=user.approved_by,
    )


def _scoped_session_id(user_id: int, session_id: str | None) -> str:
    raw = (session_id or "default").strip() or "default"
    if raw.startswith(f"u{user_id}:"):
        return raw
    return f"u{user_id}:{raw}"


def _public_session_id(user_id: int, session_id: str) -> str:
    prefix = f"u{user_id}:"
    return session_id[len(prefix):] if session_id.startswith(prefix) else session_id


def _stored_skill_activities(raw: str | None) -> list[dict]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _stored_attachments(raw: str | None) -> list[dict]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _user_prompt_context(
    user_id: int,
    rag_context: str | None = None,
    runtime_context: str | None = None,
) -> str | None:
    sections = []
    if rag_context:
        sections.append("Base de conhecimento pessoal do usuario:\n" + rag_context)
    if runtime_context:
        sections.append(runtime_context)
    workspace_status = workspace_plan_status_context(user_id)
    if workspace_status:
        sections.append(workspace_status)
    preferences_context = UserPreferenceRepo.prompt_context_for_user(user_id)
    if preferences_context:
        sections.append(preferences_context)
    skills_context = SkillRepo.enabled_context_for_user(user_id)
    if skills_context:
        sections.append(skills_context)
    return "\n\n".join(sections) if sections else None


async def get_optional_user(authorization: str | None = Header(default=None)):
    ensure_db()
    return resolve_authorized_user(authorization)


async def get_current_user(user=Depends(get_optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Nao autenticado")
    return user


async def get_admin_user(user=Depends(get_current_user)):
    if not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin necessario")
    return user


def observe_preference_suggestion(user_id: int, message: str) -> None:
    try:
        create_suggestion_from_message(user_id, message)
    except Exception:
        # Preferencias sugeridas nunca devem derrubar o fluxo principal do chat.
        return


def _parser_name(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".txt", ".md", ".csv", ".json"}:
        return "text"
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    return ext.lstrip(".") or "unknown"


def _remove_superseded_onboarding_documents(user_id: int, documents: list) -> int:
    """Remove old onboarding chunks only after the replacement was indexed."""
    removed = 0
    for document in documents:
        try:
            raw_ids = json.loads(document.vector_ids_json or "[]")
            vector_ids = [item for item in raw_ids if isinstance(item, str)] if isinstance(raw_ids, list) else []
            if vector_ids:
                delete_user_documents(user_id, vector_ids)
            if DocumentRepo.delete(document.id, user_id):
                removed += 1
        except Exception:
            continue
    return removed


def _store_document_manifest(
    user_id: int,
    doc,
    *,
    status: str,
    parser: str,
    chunk_count: int,
    vector_ids: list[str] | None = None,
    error_message: str = "",
) -> str:
    """Persist the current ingestion state without making manifests a hard dependency."""
    try:
        # Avoid presenting a stale manifest if writing the replacement fails.
        DocumentRepo.set_manifest_path(doc.id, user_id, "")
        manifest_path = write_rag_manifest(
            user_id,
            document_id=doc.id,
            filename=doc.filename,
            source=doc.source,
            status=status,
            parser=parser,
            chunk_count=chunk_count,
            file_size=doc.file_size,
            vector_ids=vector_ids,
            upload_path=doc.upload_path or "",
            checksum=doc.checksum or "",
            error_message=error_message,
            metadata={"extracted_path": doc.extracted_path or ""},
        )
        DocumentRepo.set_manifest_path(doc.id, user_id, manifest_path)
        return manifest_path
    except Exception:
        return ""


def _delete_extracted_text(user_id: int, relative_path: str) -> None:
    if not relative_path:
        return
    try:
        extracted_path = safe_user_path(user_id, "rag", relative_path)
        if extracted_path.is_file():
            extracted_path.unlink()
    except ValueError:
        return


def _ingest_stored_upload(user_id: int, doc) -> dict:
    """Index a user-owned original upload only after it was saved successfully."""
    parser = _parser_name(doc.filename)
    previous_extracted_path = doc.extracted_path or ""
    try:
        original_path = safe_user_path(user_id, "uploads", doc.upload_path)
        if not original_path.is_file():
            raise ValueError("Arquivo original nao encontrado")
        text = extract_text_for_ingestion(doc.filename, original_path.read_bytes())
        extracted_path = save_extracted_text(user_id, doc.filename, text)
    except (OSError, ValueError) as exc:
        error_message = str(exc) or "Falha ao ler o arquivo original"
        updated = DocumentRepo.update_ingestion(
            doc.id,
            user_id,
            status="error",
            parser=parser,
            chunk_count=0,
            vector_ids=[],
            error_message=error_message,
            extracted_path="",
        ) or doc
        _store_document_manifest(
            user_id,
            updated,
            status="error",
            parser=parser,
            chunk_count=0,
            vector_ids=[],
            error_message=error_message,
        )
        _delete_extracted_text(user_id, previous_extracted_path)
        raise ValueError(error_message) from exc

    chunks = split_text(text)
    metadatas = [{
        "source": "upload",
        "filename": doc.filename,
        "upload_path": doc.upload_path,
        "checksum": doc.checksum,
    }] * len(chunks)
    try:
        ids = add_user_documents(user_id, chunks, metadatas=metadatas)
    except Exception as exc:
        error_message = "Falha ao indexar o documento"
        updated = DocumentRepo.update_ingestion(
            doc.id,
            user_id,
            status="error",
            parser=parser,
            chunk_count=0,
            vector_ids=[],
            error_message=error_message,
            extracted_path=extracted_path,
        ) or doc
        _store_document_manifest(
            user_id,
            updated,
            status="error",
            parser=parser,
            chunk_count=0,
            vector_ids=[],
            error_message=error_message,
        )
        if previous_extracted_path != extracted_path:
            _delete_extracted_text(user_id, previous_extracted_path)
        raise ValueError(error_message) from exc

    updated = DocumentRepo.update_ingestion(
        doc.id,
        user_id,
        status="indexed",
        parser=parser,
        chunk_count=len(chunks),
        vector_ids=ids,
        extracted_path=extracted_path,
    )
    if not updated:
        raise ValueError("Documento nao encontrado")
    if previous_extracted_path != extracted_path:
        _delete_extracted_text(user_id, previous_extracted_path)
    manifest_path = _store_document_manifest(
        user_id,
        updated,
        status="indexed",
        parser=parser,
        chunk_count=len(chunks),
        vector_ids=ids,
    )
    DOCUMENTS_INGESTED.inc()
    return {
        "document_id": updated.id,
        "filename": updated.filename,
        "size": updated.file_size,
        "status": "indexed",
        "chunks": len(chunks),
        "ids": ids,
        "upload_path": updated.upload_path,
        "extracted_path": updated.extracted_path,
        "checksum": updated.checksum,
        "manifest_path": manifest_path,
    }


def _manual_ingest_filename(source: str | None, metadata: dict | None) -> str:
    raw = str((metadata or {}).get("filename") or "").strip()
    if not raw:
        raw = f"{(source or 'manual').strip() or 'manual'}.txt"
    name = os.path.basename(raw.replace("\\", "/")).strip()
    if not name or name in {".", ".."}:
        name = "manual.txt"
    if "." not in name:
        name = f"{name}.txt"
    return name


async def async_add_message(session_id: str, role: str, content: str, user_id: int | None = None, **metadata) -> "Message":
    """Executa add_message em thread separada para nao bloquear o event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: ConversationRepo.add_message(session_id, role, content, user_id=user_id, **metadata),
    )


async def async_set_language(session_id: str, lang: str, user_id: int | None = None) -> None:
    """Executa set_language em thread separada."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, ConversationRepo.set_language, session_id, lang, user_id)


# ═══════════════════════════════════════════════════════════════

# AUTH / ONBOARDING / SKILLS

@router.get("/auth/registration-status")
async def registration_status():
    return {
        "enabled": bool(settings.allow_registration),
        "approval_required": True,
    }


@router.post("/auth/register", response_model=RegistrationResponse, status_code=202)
async def register(body: RegisterRequest):
    ensure_db()
    if not settings.allow_registration:
        raise HTTPException(status_code=403, detail="Cadastro publico desativado")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Senha precisa ter pelo menos 6 caracteres")
    try:
        UserRepo.create_registration_request(body.email, body.username, body.password, body.display_name or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RegistrationResponse(
        status="pending",
        message="Solicitacao enviada. Aguarde a aprovacao de um administrador.",
    )


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    ensure_db()
    user, auth_status = UserRepo.authenticate_with_status(body.login, body.password)
    if not user:
        if auth_status == "pending":
            raise HTTPException(status_code=403, detail="Cadastro aguardando aprovacao do administrador")
        if auth_status == "rejected":
            raise HTTPException(status_code=403, detail="Solicitacao de cadastro rejeitada")
        raise HTTPException(status_code=401, detail="Login ou senha invalidos")
    token = create_access_token(user.id, user.username)
    return AuthResponse(access_token=token, user=_user_response(user))


@router.get("/auth/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    return _user_response(user)


@router.get("/admin/users", response_model=list[AdminUserResponse])
async def admin_list_users(
    status: str = Query(default="all", pattern="^(all|pending|approved|rejected)$"),
    admin=Depends(get_admin_user),
):
    ensure_db()
    return [_admin_user_response(user) for user in UserRepo.list_for_admin(status)]


@router.post("/admin/users/{user_id}/approve", response_model=AdminUserResponse)
async def admin_approve_user(user_id: int, admin=Depends(get_admin_user)):
    ensure_db()
    try:
        user = UserRepo.approve_registration(user_id, admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _admin_user_response(user)


@router.post("/admin/users/{user_id}/reject", response_model=AdminUserResponse)
async def admin_reject_user(user_id: int, admin=Depends(get_admin_user)):
    ensure_db()
    try:
        user = UserRepo.reject_registration(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _admin_user_response(user)


@router.delete("/admin/users/{user_id}")
async def admin_delete_registration(user_id: int, admin=Depends(get_admin_user)):
    ensure_db()
    try:
        deleted = UserRepo.delete_registration(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Solicitacao nao encontrada")
    return {"status": "deleted", "user_id": user_id}


@router.post("/onboarding")
async def save_onboarding(body: OnboardingRequest, user=Depends(get_current_user)):
    ensure_db()
    data = body.model_dump()
    profile = UserRepo.update_profile(user.id, data)
    memory_doc = "\n".join([
        "# Perfil inicial do usuario",
        f"Nome: {body.display_name or user.display_name or user.username}",
        f"Idioma: {body.language}",
        f"Fuso: {body.timezone}",
        f"Papel/area: {body.role}",
        f"Nivel tecnico: {body.technical_level}",
        f"Tom preferido: {body.preferred_tone}",
        "Objetivos: " + "; ".join(body.goals),
        "Evitar: " + "; ".join(body.avoid),
    ])
    write_profile_text(user.id, "onboarding.md", memory_doc)
    old_onboarding_docs = DocumentRepo.list_by_source(user.id, "onboarding")
    chunks = split_text(memory_doc)
    collection = user_rag_collection(user.id)
    metadatas = [{"source": "onboarding", "user_id": user.id, "filename": "perfil-inicial.md"}] * len(chunks)
    ids = add_user_documents(user.id, chunks, metadatas=metadatas)
    DocumentRepo.save(
        "perfil-inicial.md",
        "onboarding",
        len(chunks),
        len(memory_doc.encode("utf-8")),
        user_id=user.id,
        status="indexed",
        parser="text",
        vector_ids=ids,
    )
    replaced_documents = _remove_superseded_onboarding_documents(user.id, old_onboarding_docs)
    return {
        "status": "ok",
        "profile_id": profile.id,
        "profile_file": "profile/onboarding.md",
        "rag_collection": collection,
        "chunks": len(chunks),
        "ids": ids,
        "replaced_documents": replaced_documents,
    }


@router.get("/skills")
async def list_skills(user=Depends(get_current_user)):
    ensure_db()
    return SkillRepo.list_for_user(user.id)


@router.get("/skills/runs")
async def list_skill_runs(limit: int = 50, user=Depends(get_current_user)):
    ensure_db()
    return {"runs": SkillRunRepo.list_for_user(user.id, limit=limit)}


@router.get("/skills/perplexo/status")
async def perplexo_skill_status(user=Depends(get_current_user)):
    return {
        "skill": "perplexo_search",
        "configured": bool(settings.mcp_api_key.strip()),
        "base_url": settings.perplexo_base_url.rstrip("/"),
        "timeout_seconds": settings.perplexo_timeout_seconds,
    }


@router.post("/skills/perplexo/test")
async def test_perplexo_skill(user=Depends(get_current_user)):
    try:
        result = await perplexo_health()
        SkillRunRepo.create(
            user.id,
            "perplexo_search",
            "completed",
            {"action": "health_check"},
            output_summary="Conexao com o Perplexo confirmada.",
        )
        return result
    except Exception as exc:
        SkillRunRepo.create(
            user.id,
            "perplexo_search",
            "failed",
            {"action": "health_check"},
            error_message=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/skills/{skill_name}")
async def toggle_skill(skill_name: str, body: SkillToggleRequest, user=Depends(get_current_user)):
    ensure_db()
    ok = SkillRepo.set_enabled(user.id, skill_name, body.enabled, body.config)
    if not ok:
        raise HTTPException(status_code=404, detail="Skill nao encontrada")
    return {"status": "ok", "skill": skill_name, "enabled": body.enabled}


@router.get("/preferences")
async def list_preferences(user=Depends(get_current_user)):
    ensure_db()
    return {"preferences": UserPreferenceRepo.list_for_user(user.id)}


@router.put("/preferences/{key}")
async def set_preference(key: str, body: PreferenceUpdateRequest, user=Depends(get_current_user)):
    ensure_db()
    try:
        UserPreferenceRepo.set(user.id, key, body.value, source=body.source, confidence=body.confidence)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "key": key, "preferences": UserPreferenceRepo.list_for_user(user.id)}


@router.get("/preference-suggestions")
async def list_preference_suggestions(user=Depends(get_current_user)):
    ensure_db()
    return {"suggestions": PreferenceSuggestionRepo.list_pending(user.id)}


@router.post("/preference-suggestions/{suggestion_id}/resolve")
async def resolve_preference_suggestion(
    suggestion_id: int,
    body: PreferenceSuggestionResolveRequest,
    user=Depends(get_current_user),
):
    ensure_db()
    if not PreferenceSuggestionRepo.resolve(user.id, suggestion_id, accept=body.accept):
        raise HTTPException(status_code=404, detail="Sugestao nao encontrada")
    return {"status": "accepted" if body.accept else "rejected", "suggestion_id": suggestion_id}

# CONFIG / PROFILES
# ═══════════════════════════════════════════════════════════════

@router.get("/profiles")
async def list_profiles(user=Depends(get_current_user)):
    """Lista perfis/modelos a partir do provider manager, a fonte atual de verdade."""
    profiles = []
    for provider in pm_list(include_keys=False):
        models = provider.get("models", [])
        model = next((m for m in models if m.get("active")), None)
        if not model:
            model = next((m for m in models if m.get("enabled", True)), {})
        profiles.append({
            "id": provider.get("id", ""),
            "name": provider.get("name", provider.get("id", "")),
            "model": model.get("id", ""),
            "provider": provider.get("id", ""),
            "active": provider.get("active", False),
        })
    return profiles


@router.get("/config")
async def get_config(user=Depends(get_current_user)):
    """Retorna configuração atual do chatbot, mesclando
    provider manager (ativo) com settings (fallback).
    """
    # Tenta pegar provider por usuario primeiro, com fallback global.
    pm_cfg = get_active_config_for_user(user.id)
    if pm_cfg.get("model_id"):
        return {
            "provider": pm_cfg.get("provider_id", settings.llm_provider),
            "profile": pm_cfg.get("name", settings.custom_profile),
            "model": pm_cfg["model_name"] or pm_cfg["model_id"],
            "model_id": pm_cfg["model_id"],
            "provider_id": pm_cfg.get("provider_id", ""),
            "supports_images": pm_cfg.get("supports_images"),
            "supports_thinking": pm_cfg.get("supports_thinking"),
            "supports_tools": pm_cfg.get("supports_tools"),
            "reasoning_control": pm_cfg.get("reasoning_control", "automatic"),
            "reasoning_efforts": pm_cfg.get("reasoning_efforts", []),
            "moderation": settings.enable_moderation,
            "multilang": settings.enable_multilang,
            "rag": settings.enable_rag,
            "max_upload_mb": settings.max_upload_size_mb,
        }
    # Fallback: settings existentes
    return {
        "provider": settings.llm_provider,
        "profile": settings.custom_profile,
        "model": settings.custom_provider_config["model"],
        "model_id": settings.custom_provider_config["model"],
        "provider_id": settings.llm_provider,
        "supports_images": None,
        "supports_thinking": None,
        "supports_tools": None,
        "reasoning_control": "automatic",
        "reasoning_efforts": [],
        "moderation": settings.enable_moderation,
        "multilang": settings.enable_multilang,
        "rag": settings.enable_rag,
        "max_upload_mb": settings.max_upload_size_mb,
    }


# ═══════════════════════════════════════════════════════════════
# PROVIDER MANAGEMENT
# ═══════════════════════════════════════════════════════════════

from src.core.provider_manager import (
    list_providers as pm_list,
    get_provider as pm_get,
    create_provider as pm_create,
    update_provider as pm_update,
    delete_provider as pm_delete,
    set_active_provider as pm_set_active,
    set_active_model as pm_set_active_model,
    get_active_config as pm_active_config,
    add_model as pm_add_model,
    update_model as pm_update_model,
    delete_model as pm_delete_model,
    set_api_key_for_provider as pm_set_api_key,
    get_provider_api_key as pm_get_api_key,
    get_provider_status as pm_get_status,
    export_custom_providers as pm_export_custom,
    import_custom_providers as pm_import_custom,
    export_complete_state as pm_export_complete_state,
    import_complete_state as pm_import_complete_state,
    set_builtin_dynamic_models as pm_set_dynamic_models,
    sync_models_from_catalog as pm_sync_catalog,
)


def _safe_provider_config(cfg: dict) -> dict:
    """Remove segredos antes de devolver config de provider pela API."""
    safe = {
        k: v for k, v in cfg.items()
        if k not in {"api_key", "access_token", "refresh_token", "user_id"}
    }
    safe["has_key"] = bool(cfg.get("api_key"))
    return safe


@router.get("/providers/manage")
async def providers_list(
    include_keys: bool = False,
    compact: bool = False,
    user=Depends(get_current_user),
):
    """Lista todos os provedores disponiveis sem expor chaves reais."""
    providers = pm_list(include_keys=False, enrich_catalog=not compact)
    from src.core.antigravity_accounts import list_accounts as antigravity_list_accounts
    from src.core.grok_oauth import list_accounts as grok_list_accounts

    antigravity_accounts = antigravity_list_accounts(user.id)
    grok_accounts = grok_list_accounts(user.id)
    is_admin = bool(getattr(user, "is_admin", False))
    user_active_provider = (
        next((str(provider.get("id") or "") for provider in providers if provider.get("active")), "")
        if compact and is_admin
        else str(get_active_config_for_user(user.id).get("provider_id") or "")
    )
    for provider in providers:
        if provider.get("id") == "antigravity":
            provider["has_key"] = bool(antigravity_accounts)
            provider["key_source"] = "oauth_pool" if antigravity_accounts else "none"
        if provider.get("id") == "grok-oauth":
            provider["has_key"] = bool(grok_accounts)
            provider["key_source"] = "oauth_pool" if grok_accounts else "none"
        if user_active_provider in {"antigravity", "grok-oauth"}:
            provider["active"] = provider.get("id") == user_active_provider
        if not is_admin:
            provider["active"] = provider.get("id") == user_active_provider
            if provider.get("id") not in {"opencode-zen-free", "antigravity", "grok-oauth"}:
                provider["has_key"] = False
                provider["key_source"] = "none"
    return providers


@router.get("/providers/catalog")
async def providers_catalog(q: str = "", user=Depends(get_current_user)):
    """Catalogo mundial de providers do snapshot diario do models.dev."""
    from src.core.model_catalog import catalog_updated_at, list_catalog_providers

    providers = list_catalog_providers(q)
    return {
        "source": "models.dev",
        "updated_at": catalog_updated_at(),
        "total": len(providers),
        "providers": providers,
    }


@router.get("/providers/catalog/{catalog_provider_id}/models")
async def providers_catalog_models(
    catalog_provider_id: str,
    q: str = "",
    user=Depends(get_current_user),
):
    """Modelos publicados para um provider no models.dev."""
    from src.core.model_catalog import get_catalog, list_catalog_models

    if catalog_provider_id not in get_catalog():
        raise HTTPException(status_code=404, detail="Provider nao encontrado no catalogo mundial")
    models = list_catalog_models(catalog_provider_id, q)
    return {
        "provider_id": catalog_provider_id,
        "total": len(models),
        "models": models,
    }


@router.post("/providers/catalog/refresh")
async def providers_catalog_refresh(user=Depends(get_admin_user)):
    """Forca uma consulta nova ao models.dev; somente o admin altera o cache."""
    from src.core.model_catalog import catalog_updated_at, list_catalog_providers, refresh_catalog

    try:
        refresh_catalog()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao atualizar models.dev: {exc}") from exc
    providers = list_catalog_providers()
    return {
        "status": "ok",
        "source": "models.dev",
        "updated_at": catalog_updated_at(),
        "providers": len(providers),
        "models": sum(provider["model_count"] for provider in providers),
    }


@router.post("/providers/manage/{provider_id}/sync-catalog")
async def provider_sync_catalog(provider_id: str, body: dict, user=Depends(get_admin_user)):
    """Importa o catalogo escolhido; novos modelos ficam ocultos/desativados."""
    try:
        return pm_sync_catalog(provider_id, str(body.get("catalog_provider_id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/providers/export")
async def providers_export(
    include_api_keys: bool = False,
    user=Depends(get_current_user),
):
    """Exporta custom globais e providers pessoais em um bundle JSON portavel."""
    is_admin = bool(getattr(user, "is_admin", False))
    include_global_keys = include_api_keys and is_admin
    return {
        "format": "chatbot-provider-bundle",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "includes_api_keys": include_api_keys,
        "custom_api_keys_included": include_global_keys,
        "custom_providers": pm_export_custom(include_api_keys=include_global_keys),
        "personal_providers": export_user_providers(
            user.id,
            include_api_keys=include_api_keys,
        ),
    }


@router.get("/providers/admin-backup")
async def providers_admin_backup(user=Depends(get_admin_user)):
    """Backup completo e sensivel, disponivel exclusivamente ao administrador."""
    from src.core.account_pool import export_accounts as export_pool_accounts
    from src.core.antigravity_accounts import export_accounts as export_antigravity_accounts
    from src.core.grok_oauth import export_accounts as export_grok_accounts

    return {
        "format": "chatbot-admin-complete-backup",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "warning": "CONTEM CHAVES DE API E TOKENS OAUTH EM TEXTO LEGIVEL",
        "provider_state": pm_export_complete_state(),
        "personal_providers": export_user_providers(user.id, include_api_keys=True),
        "codex_auth": export_pool_accounts("codex-chatgpt"),
        "antigravity_auth": export_antigravity_accounts(user.id),
        "grok_auth": export_grok_accounts(user.id),
    }


@router.post("/providers/admin-backup")
async def providers_admin_backup_import(
    body: dict = Body(..., media_type="application/json"),
    user=Depends(get_admin_user),
):
    """Restaura o backup completo na conta administrativa atual."""
    if body.get("format") != "chatbot-admin-complete-backup" or body.get("version") != 1:
        raise HTTPException(status_code=400, detail="Backup administrativo invalido ou nao suportado")
    from src.core.account_pool import import_accounts as import_pool_accounts
    from src.core.antigravity_accounts import import_accounts as import_antigravity_accounts
    from src.core.grok_oauth import import_accounts as import_grok_accounts

    try:
        provider_result = pm_import_complete_state(body.get("provider_state"))
        personal_result = import_user_providers(user.id, body.get("personal_providers", []))
        codex_result = import_pool_accounts("codex-chatgpt", body.get("codex_auth", {}))
        antigravity_result = import_antigravity_accounts(user.id, body.get("antigravity_auth", {}))
        grok_result = import_grok_accounts(user.id, body.get("grok_auth", {}))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "ok",
        "providers": provider_result,
        "personal": personal_result,
        "codex": codex_result,
        "antigravity": antigravity_result,
        "grok": grok_result,
    }


def _custom_providers_as_personal(items: list) -> tuple[list[dict], dict]:
    """Converte custom globais portaveis em configs da conta atual."""
    personal_items = []
    converted = []
    skipped = []
    for item in items:
        if not isinstance(item, dict):
            skipped.append({"id": "", "reason": "provider custom invalido"})
            continue
        provider_id = str(item.get("id", "")).strip()
        models = item.get("models", [])
        if not provider_id or not isinstance(models, list) or not models:
            skipped.append({"id": provider_id, "reason": "provider custom sem modelos"})
            continue
        for model in models:
            if not isinstance(model, dict) or not str(model.get("id", "")).strip():
                skipped.append({"id": provider_id, "reason": "modelo custom invalido"})
                continue
            model_id = str(model["id"]).strip()
            personal = {
                "provider_id": provider_id,
                "display_name": str(item.get("name", provider_id)).strip() or provider_id,
                "base_url": str(item.get("base_url", "")).strip(),
                "model": model_id,
                "api_format": str(item.get("api_format", "chat_completions")).strip()
                or "chat_completions",
                "is_enabled": bool(item.get("enabled", True))
                and bool(model.get("enabled", True)),
                "is_default": False,
            }
            if "api_key" in item:
                personal["api_key"] = str(item.get("api_key", ""))
            personal_items.append(personal)
            converted.append({"id": provider_id, "model": model_id})
    return personal_items, {
        "created": [],
        "updated": [],
        "keys_imported": 0,
        "converted_to_personal": converted,
        "skipped": skipped,
    }


@router.post("/providers/import")
async def providers_import(
    body: dict | list = Body(..., media_type="application/json"),
    user=Depends(get_current_user),
):
    """Importa providers pessoais; admins tambem restauram custom globais."""
    if isinstance(body, list):
        custom_items = body
        personal_items = []
    elif isinstance(body, dict):
        export_format = body.get("format")
        if export_format and export_format != "chatbot-provider-bundle":
            raise HTTPException(status_code=400, detail="Formato de exportacao desconhecido")
        try:
            version = int(body.get("version", 1))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Versao de exportacao invalida")
        if version > 1:
            raise HTTPException(status_code=400, detail="Versao de exportacao ainda nao suportada")

        custom_items = body.get("custom_providers", body.get("providers", []))
        personal_items = body.get("personal_providers", [])
        if not custom_items and not personal_items:
            if body.get("provider_id") and body.get("model"):
                personal_items = [body]
            elif body.get("id"):
                custom_items = [body]
    else:
        raise HTTPException(status_code=400, detail="Arquivo JSON invalido")

    if not isinstance(custom_items, list) or not isinstance(personal_items, list):
        raise HTTPException(status_code=400, detail="Listas de providers invalidas")

    is_admin = bool(getattr(user, "is_admin", False))
    custom_result = None
    if not is_admin:
        converted_items, custom_result = _custom_providers_as_personal(custom_items)
        personal_items = [*personal_items, *converted_items]

    try:
        personal_result = import_user_providers(user.id, personal_items)
        if is_admin:
            custom_result = pm_import_custom(custom_items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "status": "ok",
        "custom": custom_result,
        "personal": personal_result,
    }


@router.get("/providers/user")
async def providers_user_list(user=Depends(get_current_user)):
    """Lista providers configurados somente pelo usuario atual."""
    return {"providers": list_user_providers(user.id)}


@router.post("/providers/user")
async def providers_user_create(body: dict, user=Depends(get_current_user)):
    """Cria um provider pessoal sem afetar o provider global."""
    try:
        return create_user_provider(user.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/providers/user/{config_id}/activate")
async def providers_user_activate(config_id: int, user=Depends(get_current_user)):
    """Define o provider pessoal ativo do usuario atual."""
    if not activate_user_provider(user.id, config_id):
        raise HTTPException(status_code=404, detail="Provider pessoal nao encontrado")
    return {"status": "ok", "active_config_id": config_id}


@router.post("/providers/user/use-global")
async def providers_user_use_global(user=Depends(get_current_user)):
    """Remove o provider pessoal padrao e volta ao provider global ativo."""
    use_global_provider(user.id)
    return {"status": "ok", "source": "global"}


@router.get("/providers/manage/{provider_id}")
async def provider_get(provider_id: str, include_keys: bool = False, user=Depends(get_current_user)):
    """Retorna detalhes de um provedor especifico sem expor chaves reais."""
    p = pm_get(provider_id, include_keys=False)
    if not p:
        raise HTTPException(status_code=404, detail="Provider não encontrado")
    return p


@router.post("/providers/manage")
async def provider_create(body: dict, user=Depends(get_admin_user)):
    """Cria um novo provedor customizado."""
    try:
        return pm_create(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/providers/manage/{provider_id}")
async def provider_update(provider_id: str, body: dict, user=Depends(get_admin_user)):
    """Atualiza um provedor."""
    existing = pm_get(provider_id, include_keys=True)
    if not existing:
        raise HTTPException(status_code=404, detail="Provider nao encontrado")

    candidate_base_url = str(body.get("base_url") or existing.get("base_url") or "")
    is_cloudflare = (
        "cloudflare" in provider_id.lower()
        or "api.cloudflare.com" in candidate_base_url.lower()
    )
    placeholder = any(marker in candidate_base_url.lower() for marker in (
        "coloque_seu_account_id",
        "{account_id}",
        "<account_id>",
    ))
    # The generic edit form can also replace API keys. Cloudflare needs the
    # account ID in the URL, so resolve it before persisting either a new key
    # or a still-placeholder URL.
    if is_cloudflare and ("api_key" in body or placeholder):
        from src.core.cloudflare_provider import discover_cloudflare_accounts, workers_ai_base_url

        token = str(body.get("api_key") or pm_get_api_key(provider_id) or "").strip()
        try:
            accounts = await discover_cloudflare_accounts(token)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not accounts:
            raise HTTPException(
                status_code=400,
                detail="O token e valido, mas nao permitiu detectar nenhuma conta Cloudflare.",
            )
        if len(accounts) > 1:
            raise HTTPException(
                status_code=400,
                detail="O token acessa varias contas. Use Detectar contas e escolha a conta correta.",
            )
        body = {**body, "base_url": workers_ai_base_url(accounts[0]["id"])}

    try:
        p = pm_update(provider_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not p:
        raise HTTPException(status_code=404, detail="Provider não encontrado")
    return p


@router.put("/providers/manage/{provider_id}/api-key")
async def provider_set_api_key(provider_id: str, body: dict, user=Depends(get_admin_user)):
    """Salva chave de API para qualquer provider (built-in ou custom)."""
    api_key = body.get("api_key", "")
    pm_set_api_key(provider_id, api_key)
    return {"status": "ok", "provider_id": provider_id}


@router.post("/providers/manage/{provider_id}/cloudflare/accounts")
async def provider_cloudflare_accounts(provider_id: str, body: dict, user=Depends(get_admin_user)):
    """Discover accessible Cloudflare accounts and optionally configure Workers AI."""
    from src.core.cloudflare_provider import discover_cloudflare_accounts, workers_ai_base_url

    provider = pm_get(provider_id, include_keys=True)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider nao encontrado")
    base_url = str(provider.get("base_url") or "").lower()
    if "api.cloudflare.com" not in base_url and "cloudflare" not in provider_id.lower():
        raise HTTPException(status_code=400, detail="Este provider nao e Cloudflare")

    supplied_token = str(body.get("api_token") or "").strip()
    token = supplied_token or pm_get_api_key(provider_id)
    requested_id = str(body.get("account_id") or "").strip()
    if body.get("manual_account_id") is True:
        if not token:
            raise HTTPException(status_code=400, detail="Informe o API Token da Cloudflare")
        try:
            configured_url = workers_ai_base_url(requested_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if supplied_token:
            pm_set_api_key(provider_id, supplied_token)
        updated = pm_update(provider_id, {"base_url": configured_url})
        if not updated:
            raise HTTPException(status_code=400, detail="Nao foi possivel atualizar a Base URL do provider")
        return {
            "status": "configured",
            "configured": True,
            "account": {"id": requested_id, "name": "Conta informada manualmente"},
            "accounts": [],
            "base_url": configured_url,
        }

    try:
        accounts = await discover_cloudflare_accounts(token)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not accounts:
        raise HTTPException(
            status_code=400,
            detail="O token e valido, mas nenhuma conta Cloudflare acessivel foi encontrada.",
        )

    selected_account = None
    if requested_id:
        selected_account = next((item for item in accounts if item["id"] == requested_id), None)
        if not selected_account:
            raise HTTPException(status_code=400, detail="A conta escolhida nao esta acessivel por este token")
    elif len(accounts) == 1:
        selected_account = accounts[0]

    if selected_account:
        if supplied_token:
            pm_set_api_key(provider_id, supplied_token)
        updated = pm_update(provider_id, {"base_url": workers_ai_base_url(selected_account["id"])})
        if not updated:
            raise HTTPException(status_code=400, detail="Nao foi possivel atualizar a Base URL do provider")
        return {
            "status": "configured",
            "configured": True,
            "account": selected_account,
            "accounts": accounts,
            "base_url": workers_ai_base_url(selected_account["id"]),
        }

    return {
        "status": "selection_required",
        "configured": False,
        "accounts": accounts,
    }


@router.delete("/providers/manage/{provider_id}")
async def provider_delete(provider_id: str, user=Depends(get_admin_user)):
    """Remove um provedor customizado."""
    ok = pm_delete(provider_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Provider built-in não pode ser excluído. Use o botão de ativar/desativar para esconder da lista.")
    return {"deleted": True}


@router.post("/providers/manage/{provider_id}/activate")
async def provider_activate(provider_id: str, user=Depends(get_current_user)):
    """Define o provedor ativo."""
    provider = pm_get(provider_id, include_keys=False)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider nao encontrado")
    if not provider.get("enabled", True):
        raise HTTPException(status_code=409, detail="Provider desativado. Habilite-o antes de ativar.")
    if provider_id in {"grok-oauth", "antigravity"}:
        try:
            config = activate_builtin_for_user(user.id, provider_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"active": provider_id, "scope": "user", "config": config}
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Somente o administrador pode alterar o provider global")
    ok = pm_set_active(provider_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Nao foi possivel ativar o provider")
    return {"active": provider_id}


@router.post("/providers/activate-model")
async def model_activate(body: dict, user=Depends(get_current_user)):
    """Define o modelo ativo dentro do provider ativo."""
    model_id = body.get("model_id", "")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id e obrigatorio")
    user_config = get_active_config_for_user(user.id)
    if user_config.get("provider_id") in {"grok-oauth", "antigravity"}:
        try:
            activate_builtin_for_user(user.id, str(user_config["provider_id"]), str(model_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"active_model": model_id, "scope": "user"}
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Somente o administrador pode alterar o modelo global")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id é obrigatório")
    ok = pm_set_active_model(model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Modelo não encontrado no provider ativo")
    return {"active_model": model_id}


@router.get("/providers/active-config")
async def providers_active_config(user=Depends(get_current_user)):
    """Retorna a configuracao ativa (provider + modelo), sem segredos."""
    return _safe_provider_config(get_active_config_for_user(user.id))


@router.get("/providers/status")
async def providers_status(provider_id: str = "", user=Depends(get_current_user)):
    """
    Status detalhado do provider ativo (ou de um específico).
    Retorna has_key, key_source, key_masked, configured.
    """
    return pm_get_status(provider_id)


@router.post("/providers/test")
async def providers_test(body: dict | None = None, user=Depends(get_current_user)):
    """
    Testa o provider ativo com uma chamada real leve.
    Envia "ping" e mede latência.
    """
    body = body or {}
    provider_id = body.get("provider_id", "")
    model_id = body.get("model_id", "")

    from src.core.provider_manager import get_provider_api_key

    if provider_id:
        provider = pm_get(provider_id, include_keys=True)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider nao encontrado")
        if not provider.get("enabled", True):
            raise HTTPException(status_code=409, detail="Provider desativado. Habilite-o antes de testar.")
        models = provider.get("models", [])
        model = next((m for m in models if model_id and m.get("id") == model_id and m.get("enabled", True)), None)
        if not model:
            model = next((m for m in models if m.get("active")), None)
        if not model:
            model = next((m for m in models if m.get("enabled", True)), {})
        cfg = {
            "provider_id": provider.get("id", provider_id),
            "name": provider.get("name", provider_id),
            "base_url": provider.get("base_url", ""),
            "endpoint": provider.get("endpoint", ""),
            "api_key": provider.get("api_key", "") or get_provider_api_key(provider_id),
            "api_format": provider.get("api_format", "chat_completions"),
            "auth_type": provider.get("auth_type", ""),
            "model_id": model.get("id", ""),
            "model_name": model.get("name", model.get("id", "")),
        }
    else:
        cfg = get_active_config_for_user(user.id)
        if model_id:
            provider = pm_get(cfg.get("provider_id", ""), include_keys=True)
            model = next((m for m in provider.get("models", []) if m.get("id") == model_id and m.get("enabled", True)), None) if provider else None
            if not model:
                return {
                    "ok": False,
                    "provider": cfg.get("provider_id", ""),
                    "model": model_id,
                    "error_type": "misconfigured",
                    "message": "Modelo nao encontrado ou desativado neste provider",
                }
            cfg["model_id"] = model_id
            cfg["model_name"] = model.get("name", model_id)

    if cfg.get("provider_id") == "codex-chatgpt":
        status = pm_get_status("codex-chatgpt")
        return {
            "ok": bool(status.get("configured")),
            "provider": "codex-chatgpt",
            "model": cfg.get("model_id", ""),
            "source": status.get("key_source", "oauth_pool"),
            "message": "Codex ChatGPT usa pool OAuth; teste via status do pool.",
        }

    if cfg.get("provider_id") == "antigravity":
        accounts = antigravity_list_accounts(user.id)
        return {
            "ok": bool(accounts),
            "provider": "antigravity",
            "model": cfg.get("model_id", ""),
            "source": "oauth_pool" if accounts else "none",
            "message": (
                "Conta Antigravity conectada. Use Sincronizar para validar projeto, modelos e cota."
                if accounts else "Conecte ou importe uma conta Antigravity."
            ),
        }

    if cfg.get("provider_id") == "grok-oauth":
        from src.core.grok_oauth import list_accounts as grok_list_accounts
        accounts = grok_list_accounts(user.id)
        confirmed = any(account.get("access_status") in {"confirmed", "rate_limited"} for account in accounts)
        return {
            "ok": confirmed,
            "provider": "grok-oauth",
            "model": cfg.get("model_id", ""),
            "source": "oauth_pool" if accounts else "none",
            "message": (
                "Conta Grok conectada e acesso aos modelos confirmado."
                if confirmed else
                "Conta Grok conectada; use Testar acesso para confirmar a inferencia."
                if accounts else
                "Conecte uma conta Grok."
            ),
        }

    if not cfg.get("api_key"):
        cfg["api_key"] = get_provider_api_key(cfg.get("provider_id", ""))

    if not cfg.get("api_key"):
        return {
            "ok": False,
            "provider": cfg.get("provider_id", ""),
            "model": cfg.get("model_id", ""),
            "error_type": "no_key",
            "message": "Nenhuma chave configurada para este provider",
        }

    base_url = cfg.get("base_url", "")
    api_key = cfg.get("api_key", "")
    test_model = cfg.get("model_id", "") or cfg.get("model_name", "")

    if not base_url or not test_model:
        return {
            "ok": False,
            "provider": cfg.get("provider_id", ""),
            "model": test_model,
            "error_type": "misconfigured",
            "message": "Provider ou modelo não configurado completamente",
        }

    import time
    import httpx

    headers = {
        "Content-Type": "application/json",
    }
    from src.core.llm import _provider_auth_headers
    headers.update(_provider_auth_headers(api_key, str(cfg.get("auth_type") or "")))

    # Se for Anthropic, usa /messages
    api_format = cfg.get("api_format", "chat_completions")
    if api_format == "anthropic_messages":
        url = f"{base_url.rstrip('/')}/messages"
        payload = {
            "model": test_model,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "ping"}],
        }
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        headers.pop("Authorization", None)
    else:
        from src.core.llm import _chat_completions_url
        url = _chat_completions_url(cfg)
        payload = {
            "model": test_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            return {
                "ok": True,
                "provider": cfg.get("provider_id", ""),
                "model": test_model,
                "source": _detect_key_source(cfg.get("provider_id", ""), api_key),
                "latency_ms": latency,
                "status_code": resp.status_code,
            }
        else:
            error_body = resp.text[:500]
            error_type = "auth_error" if resp.status_code in (401, 403) else "api_error"
            return {
                "ok": False,
                "provider": cfg.get("provider_id", ""),
                "model": test_model,
                "error_type": error_type,
                "message": f"HTTP {resp.status_code}: {error_body}",
                "latency_ms": latency,
            }
    except httpx.TimeoutException:
        return {
            "ok": False,
            "provider": cfg.get("provider_id", ""),
            "model": test_model,
            "error_type": "timeout",
            "message": "Timeout após 10 segundos",
        }
    except Exception as e:
        return {
            "ok": False,
            "provider": cfg.get("provider_id", ""),
            "model": test_model,
            "error_type": "connection_error",
            "message": str(e),
        }


@router.post("/providers/benchmark")
async def providers_benchmark(body: dict | None = None, user=Depends(get_current_user)):
    """Mede um modelo diretamente, sem agente, skills, RAG ou historico."""
    body = body or {}
    provider_id = str(body.get("provider_id") or "").strip()
    model_id = str(body.get("model_id") or "").strip()
    if not provider_id or not model_id:
        raise HTTPException(status_code=400, detail="provider_id e model_id sao obrigatorios")

    provider = pm_get(provider_id, include_keys=True)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider nao encontrado")
    if not provider.get("enabled", True):
        raise HTTPException(status_code=409, detail="Provider desativado. Habilite-o antes de testar.")
    model = next(
        (item for item in provider.get("models", []) if item.get("id") == model_id),
        None,
    )
    if not model:
        raise HTTPException(status_code=404, detail="Modelo nao encontrado")
    from langchain_core.messages import HumanMessage
    from src.core.llm import generate_stream
    from src.core.model_capabilities import with_reasoning_capabilities
    from src.core.provider_manager import get_provider_api_key

    cfg = {
        "provider_id": provider_id,
        "name": provider.get("name", provider_id),
        "base_url": provider.get("base_url", ""),
        "endpoint": provider.get("endpoint", ""),
        "api_key": provider.get("api_key", "") or get_provider_api_key(provider_id),
        "api_format": provider.get("api_format", "chat_completions"),
        "auth_type": provider.get("auth_type", ""),
        "model_id": model_id,
        "model_name": model.get("name", model_id),
        "supports_images": model.get("supports_images"),
        "supports_thinking": model.get("supports_thinking"),
        "supports_tools": model.get("supports_tools"),
        "reasoning_style": provider.get("reasoning_style", ""),
        "reasoning_options": model.get("reasoning_options", []),
        "user_id": user.id,
    }
    cfg = with_reasoning_capabilities(cfg)

    def finish_benchmark(result: dict) -> dict:
        """Persist validation while leaving catalog imports hidden until the admin enables them."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            pm_update_model(provider_id, model_id, {
                "validation_status": "working" if result.get("ok") else "failed",
                "validation_error": "" if result.get("ok") else str(result.get("message") or "")[:1000],
                "validated_at": now,
                "validation_latency_ms": int(result.get("ttft_ms") or result.get("total_ms") or 0),
            })
        except Exception:
            pass
        return result

    started = time.perf_counter()
    first_chunk_at: float | None = None
    content = ""
    reasoning = ""
    stream_error = ""

    async def consume() -> None:
        nonlocal first_chunk_at, content, reasoning, stream_error
        prompt = (
            "Teste curto de velocidade. Responda em exatamente 30 palavras simples "
            "sobre velocidade, sem lista e sem explicacoes extras."
        )
        async for chunk_type, text in generate_stream(
            [HumanMessage(content=prompt)],
            provider_config=cfg,
            response_mode="normal",
            reasoning_effort=None,
        ):
            if not text:
                continue
            if chunk_type == "error":
                stream_error += text
                continue
            if chunk_type not in {"content", "reasoning"}:
                continue
            if first_chunk_at is None:
                first_chunk_at = time.perf_counter()
            if chunk_type == "content":
                content += text
            else:
                reasoning += text

    try:
        await asyncio.wait_for(consume(), timeout=90.0)
    except asyncio.TimeoutError:
        total_ms = round((time.perf_counter() - started) * 1000)
        return finish_benchmark({
            "ok": False,
            "provider": provider_id,
            "model": model_id,
            "model_name": model.get("name", model_id),
            "total_ms": total_ms,
            "message": "Tempo limite de 90 segundos excedido",
        })
    except Exception as exc:
        total_ms = round((time.perf_counter() - started) * 1000)
        return finish_benchmark({
            "ok": False,
            "provider": provider_id,
            "model": model_id,
            "model_name": model.get("name", model_id),
            "total_ms": total_ms,
            "message": str(exc),
        })

    finished = time.perf_counter()
    total_ms = round((finished - started) * 1000)
    ttft_ms = round(((first_chunk_at or finished) - started) * 1000)
    generated_chars = len(content)
    generation_seconds = max((finished - (first_chunk_at or started)), 0.001)
    chars_per_second = round(generated_chars / generation_seconds, 1)
    if stream_error or not (content or reasoning):
        return finish_benchmark({
            "ok": False,
            "provider": provider_id,
            "model": model_id,
            "model_name": model.get("name", model_id),
            "ttft_ms": ttft_ms,
            "total_ms": total_ms,
            "message": stream_error or "O modelo terminou sem devolver texto",
        })

    return finish_benchmark({
        "ok": True,
        "provider": provider_id,
        "model": model_id,
        "model_name": model.get("name", model_id),
        "ttft_ms": ttft_ms,
        "total_ms": total_ms,
        "output_chars": generated_chars,
        "chars_per_second": chars_per_second,
        "had_reasoning": bool(reasoning),
    })


def _detect_key_source(provider_id: str, key: str) -> str:
    """Detecta a fonte da chave para o endpoint de test."""
    from src.core.provider_manager import get_stored_api_key, PROVIDER_ENV_MAP
    from src.config import settings

    if get_stored_api_key(provider_id):
        return "ui"
    env_attr = PROVIDER_ENV_MAP.get(provider_id, "")
    if env_attr and hasattr(settings, env_attr) and getattr(settings, env_attr, ""):
        return "env"
    # Fallback: só se for o provider ativo
    try:
        if settings.custom_profile == provider_id:
            return "fallback"
    except Exception:
        pass
    return "none"


@router.get("/providers/manage/{provider_id}/models")
async def provider_models(provider_id: str, user=Depends(get_current_user)):
    """Lista modelos de um provedor."""
    p = pm_get(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail="Provider não encontrado")
    return p.get("models", [])


@router.post("/providers/manage/{provider_id}/models")
async def model_add(provider_id: str, body: dict, user=Depends(get_admin_user)):
    """Adiciona um modelo a um provedor custom."""
    m = pm_add_model(provider_id, body)
    if not m:
        raise HTTPException(status_code=400, detail="Não foi possível adicionar o modelo (provider built-in?)")
    return m


@router.put("/providers/manage/{provider_id}/models/{model_id}")
async def model_update(provider_id: str, model_id: str, body: dict, user=Depends(get_admin_user)):
    """Atualiza um modelo."""
    try:
        m = pm_update_model(provider_id, model_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not m:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    return m


@router.delete("/providers/manage/{provider_id}/models/{model_id}")
async def model_delete(provider_id: str, model_id: str, user=Depends(get_admin_user)):
    """Remove um modelo de um provedor custom."""
    ok = pm_delete_model(provider_id, model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════
# HEALTH / STATS / METRICS
# ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def health(user=Depends(get_optional_user)):
    cfg = get_active_config_for_user(user.id) if user else pm_active_config()
    return {
        "status": "ok",
        "provider": cfg.get("provider_id", settings.llm_provider),
        "llm_provider": cfg.get("provider_id", settings.llm_provider),
        "profile": cfg.get("name", settings.custom_profile),
        "model": cfg.get("model_id") or cfg.get("model_name", ""),
        "model_name": cfg.get("model_name", ""),
        "vector_db": settings.vector_db_type,
        "moderation": settings.enable_moderation,
        "multilang": settings.enable_multilang,
        "rag": settings.enable_rag,
    }


@router.get("/metrics")
async def metrics(user=Depends(get_current_user)):
    return PlainTextResponse(get_metrics())


@router.get("/stats")
async def stats(user=Depends(get_current_user)):
    ensure_db()
    fb_stats = ConversationRepo.get_stats(user.id)
    total = fb_stats.get("likes", 0) + fb_stats.get("dislikes", 0)
    fb_stats["satisfaction_rate"] = (fb_stats.get("likes", 0) / total * 100) if total else 0.0
    return StatsResponse(**fb_stats)


# ═══════════════════════════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════════════════════════

@router.post("/chat")
@limiter.limit("30/minute")
async def chat(body: ChatRequest, request: Request, user=Depends(get_current_user)):
    """Envia uma mensagem e obtém resposta completa."""
    ensure_db()
    session_id = _scoped_session_id(user.id, body.session_id)

    if settings.enable_moderation:
        blocked = moderate_text(body.message)
        if blocked:
            ERRORS_TOTAL.labels(type="moderation").inc()
            return ChatResponse(response=blocked, session_id=body.session_id)

    provider_config = get_active_config_for_user(user.id)
    workspace_request = await model_requests_workspace(
        user.id,
        body.message,
        provider_config,
        session_id=session_id,
    )
    if workspace_request:
        model_meta = metadata_from_config(provider_config)
        try:
            plan = await create_workspace_plan(
                user.id,
                body.message,
                provider_config,
                session_id=session_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        response = workspace_plan_message(plan)
        memory = get_session(session_id)
        memory.add_user_message(body.message)
        memory.add_ai_message(response)
        MESSAGES_TOTAL.labels(role="user").inc()
        MESSAGES_TOTAL.labels(role="assistant").inc()
        user_msg = await async_add_message(session_id, "user", body.message, user_id=user.id)
        observe_preference_suggestion(user.id, user_msg.content)
        ai_msg = await async_add_message(session_id, "assistant", response, user_id=user.id, **model_meta)
        return ChatResponse(
            response=response,
            session_id=body.session_id,
            message_id=ai_msg.id,
            workspace_plan=plan,
            **model_meta,
        )

    lang = "pt"
    if settings.enable_multilang:
        lang = detect_language(body.message)
        await async_set_language(session_id, lang, user.id)

    use_rag = body.use_rag or user_has_personal_rag(user.id, body.message, log_run=True)
    context = None
    if use_rag and settings.enable_rag:
        context = retrieve_user_context(user.id, body.message)
    runtime_context = await run_enabled_skill_context(user.id, body.message, session_id=session_id)
    skill_activity = runtime_skill_activity(runtime_context)

    memory = get_session(session_id)
    prompt_context = _user_prompt_context(user.id, context, runtime_context)
    if prompt_context:
        memory.update_system_prompt(prompt_context)
    else:
        from langchain_core.messages import SystemMessage
        from src.core.prompts import build_system_prompt
        sys_prompt = build_system_prompt_multilang(lang) if settings.enable_multilang else build_system_prompt()
        memory.messages[0] = SystemMessage(content=sys_prompt)

    provider_config = get_active_config_for_user(user.id)
    model_meta = metadata_from_config(provider_config)
    response_mode = normalize_response_mode(
        body.response_mode,
        legacy_use_thinking=body.use_thinking,
        default=settings.codex_response_mode_default,
    )
    reasoning_effort = normalize_reasoning_effort(body.reasoning_effort, mode=response_mode)
    engine = ChatEngine(
        memory,
        provider_config=provider_config,
        response_mode=response_mode,
        reasoning_effort=reasoning_effort,
    )
    route = classify_route(body.message)
    MESSAGES_TOTAL.labels(role="user").inc()

    try:
        response_parts: list[str] = []
        reasoning_parts: list[str] = []
        async for typ, text in engine.chat_stream(body.message):
            if typ == "reasoning":
                reasoning_parts.append(text)
            else:
                response_parts.append(text)
        response = "".join(response_parts)
        reasoning = "".join(reasoning_parts)
        MESSAGES_TOTAL.labels(role="assistant").inc()
        user_msg = await async_add_message(session_id, "user", body.message, user_id=user.id)
        observe_preference_suggestion(user.id, user_msg.content)
        ai_msg = await async_add_message(
            session_id,
            "assistant",
            response,
            user_id=user.id,
            reasoning=reasoning,
            skill_activities=[skill_activity] if skill_activity else [],
            **model_meta,
        )
        return ChatResponse(
            response=response,
            reasoning=reasoning,
            skill_activities=[skill_activity] if skill_activity else [],
            session_id=body.session_id,
            message_id=ai_msg.id,
            **model_meta,
        )
    except Exception as e:
        ERRORS_TOTAL.labels(type="llm").inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
@limiter.limit("30/minute")
async def chat_stream(body: ChatStreamRequest, request: Request, user=Depends(get_current_user)):
    """Envia mensagem e obtém resposta em streaming (SSE).
    Otimizado para mínima latência de primeiro token.
    """
    # Verificação rápida de moderação (antes de começar o stream)
    if settings.enable_moderation:
        blocked = moderate_text(body.message)
        if blocked:
            async def error_gen():
                yield {"event": "token", "data": blocked}
                yield {"event": "done", "data": ""}
            return EventSourceResponse(error_gen())

    session_id = _scoped_session_id(user.id, body.session_id)
    memory = get_session(session_id)
    provider_config = get_active_config_for_user(user.id)
    route = classify_route(body.message)
    response_mode = normalize_response_mode(
        body.response_mode,
        legacy_use_thinking=body.use_thinking,
        default=settings.codex_response_mode_default,
    )
    reasoning_effort = normalize_reasoning_effort(body.reasoning_effort, mode=response_mode)
    workspace_request = await model_requests_workspace(
        user.id,
        body.message,
        provider_config,
        session_id=session_id,
    )

    # RAG em background — começa a stream primeiro, carrega contexto depois
    rag_context = None
    use_rag = False if workspace_request else body.use_rag or user_has_personal_rag(user.id, body.message, log_run=True)
    if not workspace_request and use_rag and settings.enable_rag:
        # Dispara RAG em task separada, não bloqueia o primeiro token
        async def fetch_rag():
            nonlocal rag_context
            rag_context = await asyncio.get_event_loop().run_in_executor(
                None, retrieve_user_context, user.id, body.message, 4, None
            )
        rag_task = asyncio.create_task(fetch_rag())
    else:
        rag_task = None

    model_meta = metadata_from_config(provider_config)
    engine = ChatEngine(
        memory,
        provider_config=provider_config,
        response_mode=response_mode,
        reasoning_effort=reasoning_effort,
    )

    async def event_generator():
        nonlocal rag_context
        full_response = ""
        full_reasoning = ""
        MESSAGES_TOTAL.labels(role="user").inc()
        has_reasoning = False
        stream_started = time.perf_counter()
        first_output_at: float | None = None

        # Sinaliza início imediato da conexão
        yield {"event": "start", "data": json.dumps({
            "session_id": body.session_id,
            "route": route,
            "response_mode": response_mode,
            "reasoning_effort": reasoning_effort,
            **model_meta,
        })}

        # Salva mensagem do usuário em background (não bloqueia o stream)
        save_task = asyncio.create_task(
            async_add_message(session_id, "user", body.message, user_id=user.id)
        )

        if workspace_request:
            yield {"event": "status", "data": "Planejando alteracoes no Workspace..."}
            try:
                plan = await create_workspace_plan(
                    user.id,
                    body.message,
                    provider_config,
                    session_id=session_id,
                )
                full_response = workspace_plan_message(plan)
                yield {"event": "token", "data": full_response}
                yield {"event": "workspace_plan", "data": json.dumps(plan, ensure_ascii=False)}
            except Exception as exc:
                full_response = f"Nao consegui preparar o plano do Workspace: {exc}"
                yield {"event": "token", "data": full_response}

            memory.add_user_message(body.message)
            memory.add_ai_message(full_response)
            MESSAGES_TOTAL.labels(role="assistant").inc()
            user_msg = await save_task
            observe_preference_suggestion(user.id, user_msg.content)
            ai_msg = await async_add_message(session_id, "assistant", full_response, user_id=user.id, **model_meta)
            yield {"event": "done", "data": json.dumps({
                "message_id": ai_msg.id,
                "has_reasoning": False,
                **model_meta,
            })}
            return

        # Se tiver RAG, espera o contexto ficar pronto
        if rag_task:
            yield {"event": "status", "data": "Consultando base de conhecimento..."}
            await rag_task
        yield {"event": "status", "data": "Verificando skills e contexto..."}
        runtime_context = await run_enabled_skill_context(user.id, body.message, session_id=session_id)
        skill_activity = runtime_skill_activity(runtime_context)
        if skill_activity:
            yield {
                "event": "skill_activity",
                "data": json.dumps(skill_activity, ensure_ascii=False),
            }
        prompt_context = _user_prompt_context(user.id, rag_context, runtime_context)
        memory.update_system_prompt(prompt_context)
        yield {
            "event": "status",
            "data": response_mode_status(response_mode),
        }

        # Inicia o streaming do LLM
        try:
            async for typ, text in engine.chat_stream(body.message):
                if first_output_at is None:
                    first_output_at = time.perf_counter()
                if typ == "reasoning":
                    has_reasoning = True
                    full_reasoning += text
                    yield {"event": "reasoning", "data": text}
                else:
                    full_response += text
                    yield {"event": "token", "data": text}

            MESSAGES_TOTAL.labels(role="assistant").inc()

            # Aguarda salvamento da mensagem do usuário (já deve ter terminado)
            user_msg = await save_task
            observe_preference_suggestion(user.id, user_msg.content)
            ai_msg = await async_add_message(
                session_id,
                "assistant",
                full_response,
                user_id=user.id,
                reasoning=full_reasoning,
                skill_activities=[skill_activity] if skill_activity else [],
                **model_meta,
            )
            yield {"event": "done", "data": json.dumps({
                "message_id": ai_msg.id,
                "has_reasoning": has_reasoning,
                "response_mode": response_mode,
                "reasoning_effort": reasoning_effort,
                **model_meta,
                "metrics": {
                    "ttft_s": round((first_output_at or time.perf_counter()) - stream_started, 3),
                    "total_s": round(time.perf_counter() - stream_started, 3),
                    "route": route,
                },
            })}
        except Exception as e:
            ERRORS_TOTAL.labels(type="llm").inc()
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@router.post("/chat/attachments")
@limiter.limit("30/minute")
async def upload_chat_attachments(
    request: Request,
    files: list[UploadFile] = File(...),
    session_id: str = Form("default"),
    user=Depends(get_current_user),
):
    """Save chat files in the real workspace; never index them in RAG automatically."""
    ensure_db()
    if not files or len(files) > MAX_CHAT_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Envie entre 1 e {MAX_CHAT_ATTACHMENTS} arquivos por mensagem",
        )

    artifacts = []
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    try:
        for file in files:
            if not file.filename:
                raise ValueError("Nome de arquivo invalido")
            content = await file.read()
            if not content:
                raise ValueError(f"Arquivo vazio: {file.filename}")
            if len(content) > max_bytes:
                raise ValueError(
                    f"Arquivo muito grande: {file.filename} (max {settings.max_upload_size_mb}MB)"
                )
            artifact = await asyncio.to_thread(
                save_chat_attachment,
                user.id,
                file.filename,
                content,
                file.content_type or "",
            )
            artifacts.append(artifact)

        scoped_session_id = _scoped_session_id(user.id, session_id)
        stored = await asyncio.to_thread(
            ChatAttachmentRepo.create_many,
            user.id,
            scoped_session_id,
            artifacts,
        )
        return {"attachments": stored, "rag_indexed": False}
    except ValueError as exc:
        for artifact in artifacts:
            remove_chat_attachment_file(user.id, artifact.relative_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        for artifact in artifacts:
            remove_chat_attachment_file(user.id, artifact.relative_path)
        raise HTTPException(status_code=500, detail="Falha ao salvar anexos do chat") from exc


@router.get("/chat/attachments/{attachment_id}/download")
async def download_chat_attachment(attachment_id: str, user=Depends(get_current_user)):
    attachment = await asyncio.to_thread(ChatAttachmentRepo.get_owned, attachment_id, user.id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo nao encontrado")
    path = safe_user_path(user.id, "workspace", attachment["relative_path"])
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do anexo nao encontrado no Workspace")
    return FileResponse(
        path,
        media_type=attachment["content_type"],
        filename=attachment["filename"],
    )


@router.delete("/chat/attachments/{attachment_id}")
async def delete_pending_chat_attachment(attachment_id: str, user=Depends(get_current_user)):
    existing = await asyncio.to_thread(ChatAttachmentRepo.get_owned, attachment_id, user.id)
    if not existing:
        raise HTTPException(status_code=404, detail="Anexo nao encontrado")
    deleted = await asyncio.to_thread(ChatAttachmentRepo.delete_pending, attachment_id, user.id)
    if not deleted:
        raise HTTPException(status_code=409, detail="Anexo ja pertence a uma mensagem")
    remove_chat_attachment_file(user.id, deleted["relative_path"])
    return {"deleted": True, "attachment_id": attachment_id}


@router.post("/chat/jobs", status_code=202)
@limiter.limit("30/minute")
async def create_chat_job(body: ChatStreamRequest, request: Request, user=Depends(get_current_user)):
    """Persist both messages first, then start execution outside the request."""
    if not body.message.strip() and not body.attachment_ids:
        raise HTTPException(status_code=400, detail="Mensagem ou anexo obrigatorio")
    if settings.enable_moderation and body.message.strip():
        blocked = moderate_text(body.message)
        if blocked:
            raise HTTPException(status_code=400, detail=blocked)

    response_mode = normalize_response_mode(
        body.response_mode,
        legacy_use_thinking=body.use_thinking,
        default=settings.codex_response_mode_default,
    )
    reasoning_effort = normalize_reasoning_effort(body.reasoning_effort, mode=response_mode)
    provider_config = get_active_config_for_user(user.id)
    model_meta = metadata_from_config(provider_config)
    try:
        job = await asyncio.to_thread(
            ChatJobRepo.create_with_messages,
            user_id=user.id,
            session_id=_scoped_session_id(user.id, body.session_id),
            message=body.message.strip(),
            provider=model_meta,
            response_mode=response_mode,
            reasoning_effort=reasoning_effort,
            use_rag=body.use_rag,
            client_request_id=body.client_request_id,
            attachment_ids=body.attachment_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    start_chat_job(job["id"])
    job["session_id"] = _public_session_id(user.id, job["session_id"])
    return job


@router.get("/chat/jobs/{job_id}")
async def get_chat_job(job_id: str, user=Depends(get_current_user)):
    job = await asyncio.to_thread(ChatJobRepo.get, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    job["session_id"] = _public_session_id(user.id, job["session_id"])
    return job


@router.post("/chat/jobs/{job_id}/retry", status_code=202)
async def retry_chat_job(
    job_id: str,
    client_request_id: str = Body(embed=True),
    user=Depends(get_current_user),
):
    try:
        job = await asyncio.to_thread(
            ChatJobRepo.retry_failed_as_new, job_id, user.id, client_request_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    start_chat_job(job["id"])
    job["session_id"] = _public_session_id(user.id, job["session_id"])
    return job


@router.delete("/chat/jobs/{job_id}")
async def stop_chat_job(job_id: str, user=Depends(get_current_user)):
    job = await asyncio.to_thread(ChatJobRepo.get, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    cancelled = await cancel_chat_job(job_id)
    return {"status": "cancelled" if cancelled else job["status"], "job_id": job_id}


@router.post("/messages/{message_id}/read")
async def mark_message_read(message_id: int, user=Depends(get_current_user)):
    marked = await asyncio.to_thread(MessageRepo.mark_read, message_id, user.id)
    if not marked:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")
    return {"status": "read", "message_id": message_id}


@router.get("/chat/jobs/{job_id}/stream")
async def stream_chat_job(
    job_id: str,
    request: Request,
    after_id: int = Query(default=0, ge=0),
    user=Depends(get_current_user),
):
    job = await asyncio.to_thread(ChatJobRepo.get, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")

    async def job_events():
        cursor = after_id
        yield {
            "event": "start",
            "data": json.dumps({
                "job_id": job_id,
                "message_id": job["assistant_message_id"],
                "response_mode": job["response_mode"],
                "reasoning_effort": job["reasoning_effort"],
                "provider_id": job["provider_id"],
                "provider_name": job["provider_name"],
                "model_id": job["model_id"],
                "model_name": job["model_name"],
            }, ensure_ascii=False),
        }
        while True:
            events = await asyncio.to_thread(ChatJobRepo.list_events, job_id, user.id, cursor, 200)
            for event in events:
                cursor = int(event["id"])
                event_type = event["type"]
                payload = event["payload"]
                if event_type == "text_delta":
                    name = "token"
                elif event_type == "skill":
                    name = "skill_activity"
                else:
                    name = event_type

                if event_type == "done":
                    snapshot = await asyncio.to_thread(ChatJobRepo.get, job_id, user.id)
                    payload = json.dumps({
                        "job_id": job_id,
                        "message_id": snapshot["assistant_message_id"],
                        "has_reasoning": bool(snapshot["reasoning"]),
                        "response_mode": snapshot["response_mode"],
                        "reasoning_effort": snapshot["reasoning_effort"],
                        "provider_id": snapshot["provider_id"],
                        "provider_name": snapshot["provider_name"],
                        "model_id": snapshot["model_id"],
                        "model_name": snapshot["model_name"],
                    }, ensure_ascii=False)
                elif event_type == "error":
                    name = "job_state"

                yield {"id": str(cursor), "event": name, "data": payload}

            snapshot = await asyncio.to_thread(ChatJobRepo.get, job_id, user.id)
            if snapshot["status"] in ChatJobRepo.TERMINAL_STATUSES and cursor >= snapshot["last_event_id"]:
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.1)

    return EventSourceResponse(job_events(), ping=15)


@router.post("/chat/regenerate")
async def regenerate(session_id: str = "default", user=Depends(get_current_user)):
    """Regera a ultima resposta do assistente."""
    raw_session_id = session_id
    scoped_session_id = _scoped_session_id(user.id, session_id)
    memory = get_session(scoped_session_id)
    if len(memory.messages) < 2:
        raise HTTPException(status_code=400, detail="Nao ha mensagens para regenerar")
    if memory.messages[-1].type == "ai":
        memory.messages.pop()
    user_msg = memory.messages[-1].content if memory.messages[-1].type == "human" else ""
    if not user_msg:
        raise HTTPException(status_code=400, detail="Nao ha pergunta para regenerar")

    provider_config = get_active_config_for_user(user.id)
    model_meta = metadata_from_config(provider_config)
    engine = ChatEngine(memory, provider_config=provider_config)
    response_parts: list[str] = []
    reasoning_parts: list[str] = []
    async for typ, text in engine.chat_stream(user_msg):
        if typ == "reasoning":
            reasoning_parts.append(text)
        else:
            response_parts.append(text)
    response = "".join(response_parts)
    reasoning = "".join(reasoning_parts)
    ai_msg = ConversationRepo.add_message(
        scoped_session_id,
        "assistant",
        response,
        user_id=user.id,
        reasoning=reasoning,
        **model_meta,
    )
    return ChatResponse(
        response=response,
        reasoning=reasoning,
        session_id=raw_session_id,
        message_id=ai_msg.id,
        **model_meta,
    )


# ═══════════════════════════════════════════════════════════════
# CONVERSATIONS
# ═══════════════════════════════════════════════════════════════

@router.get("/conversations")
async def list_conversations(user=Depends(get_current_user)):
    """Lista todas as conversas."""
    ensure_db()
    convs = ConversationRepo.list_all(user.id)
    activity = ConversationRepo.activity_for_user(user.id, [conversation.id for conversation in convs])
    return [
        ConversationResponse(
            id=c.id,
            session_id=_public_session_id(user.id, c.session_id),
            title=c.title or f"Conversa {c.id}",
            language=c.language,
            message_count=c.messages_count,
            created_at=utc_isoformat(c.created_at),
            updated_at=utc_isoformat(c.updated_at),
            job_status=(activity.get(c.id) or {}).get("job_status"),
            has_unread_response=bool((activity.get(c.id) or {}).get("has_unread_response")),
        )
        for c in convs
    ]


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, user=Depends(get_current_user)):
    """Obtém uma conversa com suas mensagens."""
    ensure_db()
    scoped_session_id = _scoped_session_id(user.id, session_id)
    conv = ConversationRepo.get_by_session(scoped_session_id, user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    msgs = ConversationRepo.get_history(scoped_session_id, limit=200, user_id=user.id)
    return {
        "id": conv.id,
        "session_id": _public_session_id(user.id, conv.session_id),
        "title": conv.title or f"Conversa {conv.id}",
        "language": conv.language,
        "created_at": utc_isoformat(conv.created_at),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "reasoning": m.reasoning or "",
                "skill_activities": _stored_skill_activities(m.skill_activities_json),
                "attachments": _stored_attachments(m.attachments_json),
                "feedback_score": m.feedback_score,
                "tokens_used": m.tokens_used,
                "created_at": utc_isoformat(m.created_at),
                "provider_id": m.provider_id,
                "provider_name": m.provider_name,
                "model_id": m.model_id,
                "model_name": m.model_name,
                "job_id": m.job_id,
                "status": m.status or "completed",
                "read_at": utc_isoformat(m.read_at) if m.read_at else None,
            }
            for m in msgs
        ],
    }


@router.put("/conversations/{session_id}/title")
async def rename_conversation(session_id: str, title: str = Query(...), user=Depends(get_current_user)):
    """Renomeia uma conversa."""
    ensure_db()
    ConversationRepo.rename(_scoped_session_id(user.id, session_id), title, user.id)
    return {"status": "ok", "session_id": session_id, "title": title}


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str, user=Depends(get_current_user)):
    """Deleta uma conversa."""
    ensure_db()
    ConversationRepo.delete(_scoped_session_id(user.id, session_id), user.id)
    # Limpa memória também
    from src.core.memory import _sessions
    _sessions.pop(_scoped_session_id(user.id, session_id), None)
    return {"status": "ok", "deleted": session_id}


# ═══════════════════════════════════════════════════════════════
# MESSAGES / FEEDBACK
# ═══════════════════════════════════════════════════════════════

@router.post("/feedback")
async def feedback(request: FeedbackRequest, user=Depends(get_current_user)):
    """Registra feedback para uma mensagem."""
    ensure_db()
    success = ConversationRepo.set_feedback(request.message_id, request.score, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")
    return {"status": "ok"}


@router.put("/messages/{message_id}")
async def edit_message(message_id: int, content: str = Query(...), user=Depends(get_current_user)):
    """Edita uma mensagem do usuário."""
    ensure_db()
    msg = MessageRepo.update_content(message_id, content, user.id)
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")
    return {"status": "ok", "message_id": msg.id, "content": msg.content}


# ═══════════════════════════════════════════════════════════════
# SESSIONS
# ═══════════════════════════════════════════════════════════════

@router.post("/session/{session_id}/clear")
async def clear_session(session_id: str, user=Depends(get_current_user)):
    memory = get_session(_scoped_session_id(user.id, session_id))
    memory.clear()
    return {"status": "ok", "session_id": session_id}


# ═══════════════════════════════════════════════════════════════
# RAG / DOCUMENTS
# ═══════════════════════════════════════════════════════════════

@router.post("/ingest")
async def ingest(body: IngestRequest, user=Depends(get_current_user)):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto vazio")
    chunks = split_text(body.text)
    metadatas = [{"source": body.source, **(body.metadata or {})}] * len(chunks)
    ids = add_user_documents(user.id, chunks, metadatas=metadatas)
    filename = _manual_ingest_filename(body.source, body.metadata)
    doc = DocumentRepo.save(
        filename,
        body.source or "manual",
        len(chunks),
        len(body.text.encode("utf-8")),
        user_id=user.id,
        status="indexed",
        parser="text",
        vector_ids=ids,
    )
    try:
        manifest_path = write_rag_manifest(
            user.id,
            document_id=doc.id,
            filename=filename,
            source=body.source or "manual",
            status="indexed",
            parser="text",
            chunk_count=len(chunks),
            file_size=len(body.text.encode("utf-8")),
            vector_ids=ids,
            metadata=body.metadata or {},
        )
        DocumentRepo.set_manifest_path(doc.id, user.id, manifest_path)
    except Exception:
        pass
    DOCUMENTS_INGESTED.inc()
    return IngestResponse(chunks_count=len(chunks), ids=ids)


@router.post("/documents/upload")
async def upload_original_document(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Store the original upload without automatically adding it to personal RAG."""
    ensure_db()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo invalido")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Extensao nao suportada: {ext}")
    content = await file.read()
    file_size = len(content)
    if file_size > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande (max {settings.max_upload_size_mb}MB)")
    try:
        artifact = save_upload_original(user.id, file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    doc = DocumentRepo.save(
        artifact.original_filename,
        "upload",
        0,
        file_size,
        user_id=user.id,
        upload_path=artifact.relative_path,
        checksum=artifact.checksum,
        status="uploaded",
        parser=_parser_name(artifact.original_filename),
        vector_ids=[],
    )
    manifest_path = _store_document_manifest(
        user.id,
        doc,
        status="uploaded",
        parser=doc.parser,
        chunk_count=0,
        vector_ids=[],
    )
    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "size": doc.file_size,
        "status": "uploaded",
        "chunks": 0,
        "ids": [],
        "upload_path": doc.upload_path,
        "checksum": doc.checksum,
        "manifest_path": manifest_path,
    }


@router.post("/upload")
async def upload_file_compat(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Compatibility alias that also preserves the upload-before-RAG boundary."""
    return await upload_original_document(file, user)


async def _ingest_upload_immediately(file: UploadFile, user):
    """Internal migration helper; no public route calls automatic ingestion."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Extensão não suportada: {ext}")
    content = await file.read()
    file_size = len(content)
    if file_size > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande (máx {settings.max_upload_size_mb}MB)")
    try:
        artifact = save_upload_original(user.id, file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        text = extract_text_for_ingestion(artifact.original_filename, content)
    except ValueError as exc:
        doc = DocumentRepo.save(
            artifact.original_filename,
            "upload",
            0,
            file_size,
            user_id=user.id,
            upload_path=artifact.relative_path,
            checksum=artifact.checksum,
            status="error",
            parser=_parser_name(artifact.original_filename),
            error_message=str(exc),
            vector_ids=[],
        )
        try:
            manifest_path = write_rag_manifest(
                user.id,
                document_id=doc.id,
                filename=artifact.original_filename,
                source="upload",
                status="error",
                parser=_parser_name(artifact.original_filename),
                chunk_count=0,
                file_size=file_size,
                vector_ids=[],
                upload_path=artifact.relative_path,
                checksum=artifact.checksum,
                error_message=str(exc),
            )
            DocumentRepo.set_manifest_path(doc.id, user.id, manifest_path)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(exc))
    chunks = split_text(text)
    metadatas = [{
        "source": "upload",
        "filename": artifact.original_filename,
        "upload_path": artifact.relative_path,
        "checksum": artifact.checksum,
    }] * len(chunks)
    ids = add_user_documents(user.id, chunks, metadatas=metadatas)
    doc = DocumentRepo.save(
        artifact.original_filename,
        "upload",
        len(chunks),
        file_size,
        user_id=user.id,
        upload_path=artifact.relative_path,
        checksum=artifact.checksum,
        status="indexed",
        parser=_parser_name(artifact.original_filename),
        vector_ids=ids,
    )
    manifest_path = ""
    try:
        manifest_path = write_rag_manifest(
            user.id,
            document_id=doc.id,
            filename=artifact.original_filename,
            source="upload",
            status="indexed",
            parser=_parser_name(artifact.original_filename),
            chunk_count=len(chunks),
            file_size=file_size,
            vector_ids=ids,
            upload_path=artifact.relative_path,
            checksum=artifact.checksum,
        )
        DocumentRepo.set_manifest_path(doc.id, user.id, manifest_path)
    except Exception:
        manifest_path = ""
    DOCUMENTS_INGESTED.inc()
    return {
        "filename": artifact.original_filename,
        "size": file_size,
        "chunks": len(chunks),
        "ids": ids,
        "upload_path": artifact.relative_path,
        "checksum": artifact.checksum,
        "manifest_path": manifest_path,
    }


@router.post("/documents/{doc_id}/ingest")
async def ingest_document(doc_id: int, user=Depends(get_current_user)):
    """Index a previously stored original upload into this user's personal RAG."""
    ensure_db()
    doc = DocumentRepo.get(doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    if doc.source != "upload" or not doc.upload_path:
        raise HTTPException(status_code=400, detail="Documento nao possui upload original para ingerir")
    if doc.status == "indexed":
        return {
            "document_id": doc.id,
            "filename": doc.filename,
            "size": doc.file_size,
            "status": "indexed",
            "chunks": doc.chunk_count,
            "ids": json.loads(doc.vector_ids_json or "[]"),
            "upload_path": doc.upload_path,
            "extracted_path": doc.extracted_path,
            "checksum": doc.checksum,
            "manifest_path": doc.manifest_path,
            "already_indexed": True,
        }
    try:
        return _ingest_stored_upload(user.id, doc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/documents")
async def list_documents(user=Depends(get_current_user)):
    ensure_db()
    docs = DocumentRepo.list_all(user.id)
    return [
        {
            "id": d.id, "filename": d.filename, "source": d.source,
            "chunks": d.chunk_count, "size": d.file_size,
            "upload_path": d.upload_path or "",
            "extracted_path": d.extracted_path or "",
            "checksum": d.checksum or "",
            "status": d.status or "",
            "parser": d.parser or "",
            "error_message": d.error_message or "",
            "manifest_path": d.manifest_path or "",
            "created_at": utc_isoformat(d.created_at),
        }
        for d in docs
    ]


@router.get("/documents/{doc_id}/manifest")
async def get_document_manifest(doc_id: int, user=Depends(get_current_user)):
    ensure_db()
    doc = DocumentRepo.get(doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    if not doc.manifest_path:
        raise HTTPException(status_code=404, detail="Manifesto nao encontrado")
    try:
        manifest_path = safe_user_path(user.id, "rag", doc.manifest_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Manifesto invalido")
    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Manifesto nao encontrado")
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Manifesto corrompido")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, user=Depends(get_current_user)):
    """Deleta um documento da base."""
    ensure_db()
    doc = DocumentRepo.get(doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")

    vector_ids = json.loads(doc.vector_ids_json or "[]")
    delete_user_documents(user.id, vector_ids)

    upload_deleted = False
    if doc.upload_path:
        try:
            original_path = safe_user_path(user.id, "uploads", doc.upload_path)
            if original_path.is_file():
                original_path.unlink()
                upload_deleted = True
                upload_root = safe_user_path(user.id, "uploads")
                upload_folder = original_path.parent
                if upload_folder != upload_root and upload_root in upload_folder.parents:
                    try:
                        upload_folder.rmdir()
                    except OSError:
                        pass
        except ValueError:
            upload_deleted = False

    extracted_deleted = False
    if doc.extracted_path:
        try:
            extracted_path = safe_user_path(user.id, "rag", doc.extracted_path)
            if extracted_path.is_file():
                extracted_path.unlink()
                extracted_deleted = True
        except ValueError:
            extracted_deleted = False

    manifest_deleted = False
    if doc.manifest_path:
        try:
            manifest_path = safe_user_path(user.id, "rag", doc.manifest_path)
            if manifest_path.is_file():
                manifest_path.unlink()
                manifest_deleted = True
        except ValueError:
            manifest_deleted = False

    DocumentRepo.delete(doc_id, user.id)
    return {
        "status": "ok",
        "deleted": doc_id,
        "rag_ids_deleted": len(vector_ids),
        "upload_deleted": upload_deleted,
        "extracted_deleted": extracted_deleted,
        "manifest_deleted": manifest_deleted,
    }


# ═══════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════

@router.get("/export/{session_id}")
async def export_conversation(session_id: str, format: str = "txt", user=Depends(get_current_user)):
    """Exporta uma conversa em TXT ou JSON."""
    ensure_db()
    scoped_session_id = _scoped_session_id(user.id, session_id)
    conv = ConversationRepo.get_by_session(scoped_session_id, user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    msgs = ConversationRepo.get_history(scoped_session_id, limit=500, user_id=user.id)

    if format == "json":
        data = {
            "title": conv.title or f"Conversa {conv.id}",
            "created_at": utc_isoformat(conv.created_at),
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "reasoning": m.reasoning or "",
                    "skill_activities": _stored_skill_activities(m.skill_activities_json),
                    "attachments": _stored_attachments(m.attachments_json),
                    "created_at": utc_isoformat(m.created_at),
                    "provider_id": m.provider_id,
                    "provider_name": m.provider_name,
                    "model_id": m.model_id,
                    "model_name": m.model_name,
                }
                for m in msgs
            ],
        }
        return PlainTextResponse(json.dumps(data, ensure_ascii=False, indent=2),
                                 media_type="application/json",
                                 headers={"Content-Disposition": f'attachment; filename="chat-{session_id}.json"'})
    else:
        lines = [f"Conversa: {conv.title or session_id}", "=" * 50, ""]
        for m in msgs:
            if m.role == "user":
                prefix = "🧑 Você:"
            else:
                model_label = m.model_name or m.model_id or ""
                prefix = f"🤖 Bot ({model_label}):" if model_label else "🤖 Bot:"
            if m.reasoning:
                lines.append(f"[Raciocinio]\n{m.reasoning}\n")
            activities = _stored_skill_activities(m.skill_activities_json)
            if activities:
                lines.append(
                    "[Ferramentas e Skills]\n"
                    + json.dumps(activities, ensure_ascii=False, indent=2)
                    + "\n"
                )
            attachments = _stored_attachments(m.attachments_json)
            if attachments:
                lines.append("[Anexos do chat]")
                for attachment in attachments:
                    lines.append(
                        f"- {attachment.get('filename') or 'arquivo'}: "
                        f"{attachment.get('relative_path') or attachment.get('path') or ''}"
                    )
                lines.append("")
            lines.append(f"{prefix}\n{m.content}\n")
        text = "\n".join(lines)
        return PlainTextResponse(text,
                                 media_type="text/plain",
                                 headers={"Content-Disposition": f'attachment; filename="chat-{session_id}.txt"'})


# ═══════════════════════════════════════════════════════════════
#  CODEX CHATGPT — Pool de Contas
# ═══════════════════════════════════════════════════════════════

from src.core.antigravity_accounts import (
    finish_oauth as antigravity_finish_oauth,
    import_auth as antigravity_import_auth,
    list_accounts as antigravity_list_accounts,
    remove_account as antigravity_remove_account,
    start_oauth as antigravity_start_oauth,
    update_account as antigravity_update_account,
)
from src.core.antigravity_client import (
    provider_models_from_account as antigravity_provider_models,
    sync_account as antigravity_sync_account,
)


@router.get("/antigravity/accounts")
async def antigravity_accounts_list(user=Depends(get_current_user)):
    return antigravity_list_accounts(user.id)


@router.post("/antigravity/oauth/start")
async def antigravity_oauth_start(user=Depends(get_current_user)):
    return antigravity_start_oauth(user.id)


@router.post("/antigravity/oauth/finish")
async def antigravity_oauth_finish(body: dict, user=Depends(get_current_user)):
    try:
        account = await antigravity_finish_oauth(
            user.id,
            str(body.get("request_id") or ""),
            str(body.get("callback_url") or ""),
        )
        return {"status": "ok", "account": account}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/antigravity/import-auth")
async def antigravity_auth_import(body: dict, user=Depends(get_current_user)):
    try:
        accounts = await antigravity_import_auth(user.id, body)
        return {"status": "ok", "accounts": accounts}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/antigravity/accounts/{account_id}/select")
async def antigravity_account_select(account_id: str, user=Depends(get_current_user)):
    account = antigravity_update_account(user.id, account_id, {"select": True})
    if not account:
        raise HTTPException(status_code=404, detail="Conta Antigravity nao encontrada")
    return {"status": "ok", "account": account}


@router.delete("/antigravity/accounts/{account_id}")
async def antigravity_account_remove(account_id: str, user=Depends(get_current_user)):
    if not antigravity_remove_account(user.id, account_id):
        raise HTTPException(status_code=404, detail="Conta Antigravity nao encontrada")
    return {"deleted": True}


@router.post("/antigravity/accounts/{account_id}/sync")
async def antigravity_account_sync(account_id: str, user=Depends(get_current_user)):
    try:
        account = await antigravity_sync_account(user.id, account_id)
        models = antigravity_provider_models(account)
        if models:
            pm_set_dynamic_models("antigravity", models)
        return {"status": "ok", "account": account, "models": models}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


from src.core.grok_oauth import (
    list_accounts as grok_list_accounts,
    poll_device_oauth as grok_poll_device_oauth,
    refresh_access_token as grok_refresh_access_token,
    remove_account as grok_remove_account,
    start_device_oauth as grok_start_device_oauth,
    test_account as grok_test_account,
    update_account as grok_update_account,
)


@router.get("/grok/accounts")
async def grok_accounts_list(user=Depends(get_current_user)):
    return grok_list_accounts(user.id)


@router.post("/grok/oauth/device/start")
async def grok_oauth_device_start(user=Depends(get_current_user)):
    try:
        return await grok_start_device_oauth(user.id)
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/grok/oauth/device/poll/{request_id}")
async def grok_oauth_device_poll(request_id: str, user=Depends(get_current_user)):
    try:
        return await grok_poll_device_oauth(user.id, request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/grok/accounts/{account_id}/select")
async def grok_account_select(account_id: str, user=Depends(get_current_user)):
    account = grok_update_account(user.id, account_id, {"select": True})
    if not account:
        raise HTTPException(status_code=404, detail="Conta Grok nao encontrada")
    return {"status": "ok", "account": account}


@router.delete("/grok/accounts/{account_id}")
async def grok_account_remove(account_id: str, user=Depends(get_current_user)):
    if not grok_remove_account(user.id, account_id):
        raise HTTPException(status_code=404, detail="Conta Grok nao encontrada")
    return {"deleted": True}


@router.post("/grok/accounts/{account_id}/refresh")
async def grok_account_refresh(account_id: str, user=Depends(get_current_user)):
    try:
        account = await grok_refresh_access_token(user.id, account_id, force=True)
        safe = {key: value for key, value in account.items() if key not in {"access_token", "refresh_token", "id_token"}}
        return {"status": "ok", "account": safe}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/grok/accounts/{account_id}/test")
async def grok_account_test(account_id: str, user=Depends(get_current_user)):
    try:
        result = await grok_test_account(user.id, account_id)
        model_ids = result.get("models", [])
        if model_ids:
            current = pm_get("grok-oauth") or {}
            existing = {str(model.get("id")): model for model in current.get("models", [])}
            models = []
            for model_id in model_ids:
                previous = existing.get(model_id, {})
                models.append({
                    **previous,
                    "id": model_id,
                    "name": previous.get("name") or model_id,
                    "context_length": int(previous.get("context_length") or 128000),
                    "enabled": bool(previous.get("enabled", False)),
                })
            pm_set_dynamic_models("grok-oauth", models)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


from src.core.account_pool import (
    list_accounts as pool_list_accounts,
    add_account as pool_add_account,
    remove_account as pool_remove_account,
    get_account as pool_get_account,
    refresh_account_token as pool_refresh_token,
    refresh_all_expired as pool_refresh_all,
    update_quota_all as pool_update_quota,
    get_best_account as pool_get_best,
    get_pool_stats as pool_get_stats,
)
from src.core.codex_client import device_code_start, device_code_poll, extract_tokens_from_json, get_device_session_status


def _public_codex_account(acc: dict) -> dict:
    """Formato seguro para o frontend: nunca retorna access_token/refresh_token."""
    quota = acc.get("quota_cache", {}) if isinstance(acc.get("quota_cache", {}), dict) else {}
    q5h = quota.get("5h", {}) if isinstance(quota.get("5h", {}), dict) else {}
    qwk = quota.get("weekly", {}) if isinstance(quota.get("weekly", {}), dict) else {}
    return {
        "id": acc.get("account_id", ""),
        "account_id": acc.get("account_id", ""),
        "label": acc.get("label", ""),
        "email": acc.get("email", acc.get("label", "")),
        "enabled": acc.get("enabled", True),
        "auth_type": acc.get("auth_type", "oauth"),
        "quota_5h_pct": q5h.get("percent_left"),
        "quota_weekly_pct": qwk.get("percent_left"),
        "quota_5h_reset": q5h.get("reset_time_ms"),
        "quota_weekly_reset": qwk.get("reset_time_ms"),
        "quota_error": quota.get("error"),
        "last_quota_fetch": acc.get("last_quota_fetch", 0),
    }


def _public_pool_account(acc: dict, provider_id: str) -> dict:
    if provider_id == "codex-chatgpt":
        return _public_codex_account(acc)
    return {k: v for k, v in acc.items() if k not in {"access_token", "refresh_token"}}


@router.get("/codex/pool/{provider_id}")
async def codex_pool_list(provider_id: str, user=Depends(get_admin_user)):
    """Lista contas no pool de um provider."""
    accounts = pool_list_accounts(provider_id)
    return [_public_pool_account(acc, provider_id) for acc in accounts]


@router.get("/codex/pool/{provider_id}/stats")
async def codex_pool_stats(provider_id: str, user=Depends(get_admin_user)):
    """Estatísticas do pool (quotas, etc)."""
    return pool_get_stats(provider_id)


@router.post("/codex/pool/{provider_id}/accounts")
async def codex_pool_add(provider_id: str, body: dict, user=Depends(get_admin_user)):
    """Adiciona uma conta ao pool (via tokens manualmente)."""
    try:
        acc = pool_add_account(provider_id, body)
        return {"status": "ok", "account": _public_pool_account(acc, provider_id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/codex/pool/{provider_id}/accounts/{account_id}")
async def codex_pool_remove(provider_id: str, account_id: str, user=Depends(get_admin_user)):
    """Remove uma conta do pool."""
    ok = pool_remove_account(provider_id, account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return {"deleted": True}


@router.post("/codex/pool/{provider_id}/accounts/{account_id}/refresh")
async def codex_pool_refresh(provider_id: str, account_id: str, user=Depends(get_admin_user)):
    """Renova token de uma conta."""
    tokens = await pool_refresh_token(provider_id, account_id)
    if not tokens:
        raise HTTPException(status_code=400, detail="Falha ao renovar token")
    return {"status": "ok", "refreshed": True}


@router.post("/codex/pool/{provider_id}/refresh-all")
async def codex_pool_refresh_all(provider_id: str, user=Depends(get_admin_user)):
    """Renova tokens de todas as contas expiradas."""
    results = await pool_refresh_all(provider_id)
    return {"results": results}


@router.post("/codex/pool/{provider_id}/update-quota")
async def codex_pool_update_quota(provider_id: str, user=Depends(get_admin_user)):
    """Atualiza cota de todas as contas."""
    results = await pool_update_quota(provider_id)
    return {"results": results}


@router.get("/codex/pool/{provider_id}/best")
async def codex_pool_best(provider_id: str, user=Depends(get_admin_user)):
    """Retorna a melhor conta sem expor access_token/refresh_token."""
    best = await pool_get_best(provider_id)
    if not best:
        raise HTTPException(status_code=404, detail="Nenhuma conta disponivel")
    if provider_id == "codex-chatgpt":
        return _public_codex_account(best)
    return {k: v for k, v in best.items() if k not in {"access_token", "refresh_token"}}


# ─── Device Code ─────────────────────────────────────────────────────

@router.post("/codex/device-code/request")
async def codex_device_request(user=Depends(get_admin_user)):
    """Passo 1: Inicia Device Code OAuth.
    Retorna user_code, verification_uri e request_id.
    O frontend deve chamar /codex/device-code/poll/{request_id} a cada ~5s.
    """
    result = await device_code_start()
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return {
        "status": result["status"],
        "user_code": result["user_code"],
        "verification_uri": result["verification_uri"],
        "request_id": result.get("request_id", ""),
        "interval": result.get("interval", 5),
    }


@router.post("/codex/device-code/poll/{request_id}")
async def codex_device_do_poll(request_id: str, user=Depends(get_admin_user)):
    """
    Passo 2: Faz UMA tentativa de poll para ver se o usuário autenticou.
    - Se aprovado: faz exchange auth_code → tokens e salva no pool.
    - Se pendente: retorna status "pending".
    - Se erro: retorna status "error" com mensagem.
    O frontend chama isso a cada 5s até receber "saved" ou "error".
    """
    return await device_code_poll(request_id)


@router.get("/codex/device-code/status/{request_id}")
async def codex_device_status(request_id: str, user=Depends(get_admin_user)):
    """Consulta o status atual (sem fazer poll)."""
    return get_device_session_status(request_id)


@router.post("/codex/extract-auth")
async def codex_extract_auth(body: dict, user=Depends(get_admin_user)):
    """Extrai tokens de um auth.json enviado pelo usuário."""
    tokens = extract_tokens_from_json(body)
    if not tokens:
        raise HTTPException(status_code=400, detail="Formato de auth.json não reconhecido")
    
    # Já adiciona automaticamente no pool
    acc = pool_add_account("codex-chatgpt", tokens)
    return {
        "status": "ok",
        "account": _public_codex_account(acc),
        "email": acc.get("label", ""),
    }
