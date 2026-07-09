"""Rotas da API REST — versão completa com todas as features."""

import os
import json
import hashlib
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Query, Depends, Header
from fastapi.responses import PlainTextResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.schemas import (
    ChatRequest, ChatResponse, ChatStreamRequest,
    IngestRequest, IngestResponse, FeedbackRequest, StatsResponse,
    ConversationResponse, RegisterRequest, LoginRequest, AuthResponse, UserResponse,
    OnboardingRequest, SkillToggleRequest, PreferenceUpdateRequest, PreferenceSuggestionResolveRequest,
)
from src.core.memory import get_session
from src.core.chat import ChatEngine
from src.core.moderation import moderate_text, moderate_with_api
from src.core.multilang import detect_language, build_system_prompt_multilang
from src.core.feedback import FeedbackManager
from src.core.metrics import MESSAGES_TOTAL, ERRORS_TOTAL, DOCUMENTS_INGESTED, ACTIVE_SESSIONS, get_metrics
from src.core.cache import cache_llm_response, get_cached_llm_response
from src.core.llm import get_llm
from src.core.skill_runtime import run_enabled_skill_context, user_has_personal_rag
from src.core.preference_suggestions import create_suggestion_from_message
from src.core.user_provider_manager import (
    activate_user_provider,
    create_user_provider,
    get_active_config_for_user,
    list_user_providers,
    metadata_from_config,
)
from src.rag.chunker import split_text, split_documents
from src.rag.personal import add_user_documents, delete_user_documents, retrieve_user_context, user_rag_collection
from src.db.repository import ConversationRepo, DocumentRepo, MessageRepo, PreferenceSuggestionRepo, UserRepo, SkillRepo, SkillRunRepo, UserPreferenceRepo
from src.db.models import init_db as _init_db
from src.config import settings
from src.core.auth import create_access_token
from src.core.auth_required import resolve_authorized_user
from src.core.ingestion import SUPPORTED_EXTENSIONS, extract_text_for_ingestion, save_upload_original, write_rag_manifest
from src.core.userspace import safe_user_path, write_profile_text

router = APIRouter()
_SLOWAPI_CONFIG = os.path.join(os.path.dirname(__file__), "slowapi.env")
limiter = Limiter(key_func=get_remote_address, config_filename=_SLOWAPI_CONFIG)
feedback_mgr = FeedbackManager()
_db_initialized = False


def ensure_db():
    global _db_initialized
    if not _db_initialized:
        _init_db()
        UserRepo.ensure_default_user()
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


def _scoped_session_id(user_id: int, session_id: str | None) -> str:
    raw = (session_id or "default").strip() or "default"
    if raw.startswith(f"u{user_id}:"):
        return raw
    return f"u{user_id}:{raw}"


def _public_session_id(user_id: int, session_id: str) -> str:
    prefix = f"u{user_id}:"
    return session_id[len(prefix):] if session_id.startswith(prefix) else session_id


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
        )
        DocumentRepo.set_manifest_path(doc.id, user_id, manifest_path)
        return manifest_path
    except Exception:
        return ""


def _ingest_stored_upload(user_id: int, doc) -> dict:
    """Index a user-owned original upload only after it was saved successfully."""
    parser = _parser_name(doc.filename)
    try:
        original_path = safe_user_path(user_id, "uploads", doc.upload_path)
        if not original_path.is_file():
            raise ValueError("Arquivo original nao encontrado")
        text = extract_text_for_ingestion(doc.filename, original_path.read_bytes())
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
        raise ValueError(error_message) from exc

    updated = DocumentRepo.update_ingestion(
        doc.id,
        user_id,
        status="indexed",
        parser=parser,
        chunk_count=len(chunks),
        vector_ids=ids,
    )
    if not updated:
        raise ValueError("Documento nao encontrado")
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

@router.post("/auth/register", response_model=AuthResponse)
async def register(body: RegisterRequest):
    ensure_db()
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Senha precisa ter pelo menos 6 caracteres")
    try:
        user = UserRepo.create_user(body.email, body.username, body.password, body.display_name or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = create_access_token(user.id, user.username)
    return AuthResponse(access_token=token, user=_user_response(user))


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    ensure_db()
    user = UserRepo.authenticate(body.login, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Login ou senha invalidos")
    token = create_access_token(user.id, user.username)
    return AuthResponse(access_token=token, user=_user_response(user))


@router.get("/auth/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    return _user_response(user)


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
)


def _safe_provider_config(cfg: dict) -> dict:
    """Remove segredos antes de devolver config de provider pela API."""
    safe = {k: v for k, v in cfg.items() if k not in {"api_key", "access_token", "refresh_token"}}
    safe["has_key"] = bool(cfg.get("api_key"))
    return safe


@router.get("/providers/manage")
async def providers_list(include_keys: bool = False, user=Depends(get_current_user)):
    """Lista todos os provedores disponiveis sem expor chaves reais."""
    return pm_list(include_keys=False)


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


@router.delete("/providers/manage/{provider_id}")
async def provider_delete(provider_id: str, user=Depends(get_admin_user)):
    """Remove um provedor customizado."""
    ok = pm_delete(provider_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Provider built-in não pode ser excluído. Use o botão de ativar/desativar para esconder da lista.")
    return {"deleted": True}


@router.post("/providers/manage/{provider_id}/activate")
async def provider_activate(provider_id: str, user=Depends(get_admin_user)):
    """Define o provedor ativo."""
    ok = pm_set_active(provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Provider não encontrado")
    return {"active": provider_id}


@router.post("/providers/activate-model")
async def model_activate(body: dict, user=Depends(get_admin_user)):
    """Define o modelo ativo dentro do provider ativo."""
    model_id = body.get("model_id", "")
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
            "api_key": provider.get("api_key", "") or get_provider_api_key(provider_id),
            "api_format": provider.get("api_format", "chat_completions"),
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
        "Authorization": f"Bearer {api_key}",
    }

    # Se for Anthropic, usa /messages
    api_format = cfg.get("api_format", "chat_completions")
    if api_format == "anthropic_messages":
        url = f"{base_url}/messages"
        payload = {
            "model": test_model,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "ping"}],
        }
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        headers.pop("Authorization", None)
    else:
        url = f"{base_url}/chat/completions"
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

    lang = "pt"
    if settings.enable_multilang:
        lang = detect_language(body.message)
        await async_set_language(session_id, lang, user.id)

    use_rag = body.use_rag or user_has_personal_rag(user.id, body.message, log_run=True)
    context = None
    if use_rag and settings.enable_rag:
        context = retrieve_user_context(user.id, body.message)
    runtime_context = await run_enabled_skill_context(user.id, body.message)

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
    engine = ChatEngine(memory, provider_config=provider_config)
    MESSAGES_TOTAL.labels(role="user").inc()

    try:
        response = await engine.chat(body.message)
        MESSAGES_TOTAL.labels(role="assistant").inc()
        user_msg = await async_add_message(session_id, "user", body.message, user_id=user.id)
        observe_preference_suggestion(user.id, user_msg.content)
        ai_msg = await async_add_message(session_id, "assistant", response, user_id=user.id, **model_meta)
        return ChatResponse(
            response=response,
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

    # RAG em background — começa a stream primeiro, carrega contexto depois
    rag_context = None
    use_rag = body.use_rag or user_has_personal_rag(user.id, body.message, log_run=True)
    if use_rag and settings.enable_rag:
        # Dispara RAG em task separada, não bloqueia o primeiro token
        async def fetch_rag():
            nonlocal rag_context
            rag_context = await asyncio.get_event_loop().run_in_executor(
                None, retrieve_user_context, user.id, body.message, 4, None
            )
        rag_task = asyncio.create_task(fetch_rag())
    else:
        rag_task = None

    provider_config = get_active_config_for_user(user.id)
    model_meta = metadata_from_config(provider_config)
    engine = ChatEngine(memory, provider_config=provider_config)

    async def event_generator():
        nonlocal rag_context
        full_response = ""
        MESSAGES_TOTAL.labels(role="user").inc()
        has_reasoning = False

        # Sinaliza início imediato da conexão
        yield {"event": "start", "data": json.dumps({"session_id": body.session_id, **model_meta})}

        # Salva mensagem do usuário em background (não bloqueia o stream)
        save_task = asyncio.create_task(
            async_add_message(session_id, "user", body.message, user_id=user.id)
        )

        # Se tiver RAG, espera o contexto ficar pronto
        if rag_task:
            await rag_task
        runtime_context = await run_enabled_skill_context(user.id, body.message)
        prompt_context = _user_prompt_context(user.id, rag_context, runtime_context)
        memory.update_system_prompt(prompt_context)

        # Inicia o streaming do LLM
        try:
            async for typ, text in engine.chat_stream(body.message):
                if typ == "reasoning":
                    has_reasoning = True
                    yield {"event": "reasoning", "data": text}
                else:
                    full_response += text
                    yield {"event": "token", "data": text}

            MESSAGES_TOTAL.labels(role="assistant").inc()

            # Aguarda salvamento da mensagem do usuário (já deve ter terminado)
            user_msg = await save_task
            observe_preference_suggestion(user.id, user_msg.content)
            ai_msg = await async_add_message(session_id, "assistant", full_response, user_id=user.id, **model_meta)
            yield {"event": "done", "data": json.dumps({
                "message_id": ai_msg.id,
                "has_reasoning": has_reasoning,
                **model_meta,
            })}
        except Exception as e:
            ERRORS_TOTAL.labels(type="llm").inc()
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


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
    response = await engine.chat(user_msg)
    ai_msg = ConversationRepo.add_message(scoped_session_id, "assistant", response, user_id=user.id, **model_meta)
    return ChatResponse(response=response, session_id=raw_session_id, message_id=ai_msg.id, **model_meta)


# ═══════════════════════════════════════════════════════════════
# CONVERSATIONS
# ═══════════════════════════════════════════════════════════════

@router.get("/conversations")
async def list_conversations(user=Depends(get_current_user)):
    """Lista todas as conversas."""
    ensure_db()
    convs = ConversationRepo.list_all(user.id)
    return [
        ConversationResponse(
            id=c.id,
            session_id=_public_session_id(user.id, c.session_id),
            title=c.title or f"Conversa {c.id}",
            language=c.language,
            message_count=c.messages_count,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
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
        "created_at": conv.created_at.isoformat(),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "feedback_score": m.feedback_score,
                "tokens_used": m.tokens_used,
                "created_at": m.created_at.isoformat(),
                "provider_id": m.provider_id,
                "provider_name": m.provider_name,
                "model_id": m.model_id,
                "model_name": m.model_name,
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
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
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
            "checksum": d.checksum or "",
            "status": d.status or "",
            "parser": d.parser or "",
            "error_message": d.error_message or "",
            "manifest_path": d.manifest_path or "",
            "created_at": d.created_at.isoformat(),
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
            "created_at": conv.created_at.isoformat(),
            "messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat(), "provider_id": m.provider_id, "provider_name": m.provider_name, "model_id": m.model_id, "model_name": m.model_name}
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
            lines.append(f"{prefix}\n{m.content}\n")
        text = "\n".join(lines)
        return PlainTextResponse(text,
                                 media_type="text/plain",
                                 headers={"Content-Disposition": f'attachment; filename="chat-{session_id}.txt"'})


# ═══════════════════════════════════════════════════════════════
#  CODEX CHATGPT — Pool de Contas
# ═══════════════════════════════════════════════════════════════

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
async def codex_pool_list(provider_id: str, user=Depends(get_current_user)):
    """Lista contas no pool de um provider."""
    accounts = pool_list_accounts(provider_id)
    return [_public_pool_account(acc, provider_id) for acc in accounts]


@router.get("/codex/pool/{provider_id}/stats")
async def codex_pool_stats(provider_id: str, user=Depends(get_current_user)):
    """Estatísticas do pool (quotas, etc)."""
    return pool_get_stats(provider_id)


@router.post("/codex/pool/{provider_id}/accounts")
async def codex_pool_add(provider_id: str, body: dict, user=Depends(get_current_user)):
    """Adiciona uma conta ao pool (via tokens manualmente)."""
    try:
        acc = pool_add_account(provider_id, body)
        return {"status": "ok", "account": _public_pool_account(acc, provider_id)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/codex/pool/{provider_id}/accounts/{account_id}")
async def codex_pool_remove(provider_id: str, account_id: str, user=Depends(get_current_user)):
    """Remove uma conta do pool."""
    ok = pool_remove_account(provider_id, account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return {"deleted": True}


@router.post("/codex/pool/{provider_id}/accounts/{account_id}/refresh")
async def codex_pool_refresh(provider_id: str, account_id: str, user=Depends(get_current_user)):
    """Renova token de uma conta."""
    tokens = await pool_refresh_token(provider_id, account_id)
    if not tokens:
        raise HTTPException(status_code=400, detail="Falha ao renovar token")
    return {"status": "ok", "refreshed": True}


@router.post("/codex/pool/{provider_id}/refresh-all")
async def codex_pool_refresh_all(provider_id: str, user=Depends(get_current_user)):
    """Renova tokens de todas as contas expiradas."""
    results = await pool_refresh_all(provider_id)
    return {"results": results}


@router.post("/codex/pool/{provider_id}/update-quota")
async def codex_pool_update_quota(provider_id: str, user=Depends(get_current_user)):
    """Atualiza cota de todas as contas."""
    results = await pool_update_quota(provider_id)
    return {"results": results}


@router.get("/codex/pool/{provider_id}/best")
async def codex_pool_best(provider_id: str, user=Depends(get_current_user)):
    """Retorna a melhor conta sem expor access_token/refresh_token."""
    best = await pool_get_best(provider_id)
    if not best:
        raise HTTPException(status_code=404, detail="Nenhuma conta disponivel")
    if provider_id == "codex-chatgpt":
        return _public_codex_account(best)
    return {k: v for k, v in best.items() if k not in {"access_token", "refresh_token"}}


# ─── Device Code ─────────────────────────────────────────────────────

@router.post("/codex/device-code/request")
async def codex_device_request(user=Depends(get_current_user)):
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
async def codex_device_do_poll(request_id: str, user=Depends(get_current_user)):
    """
    Passo 2: Faz UMA tentativa de poll para ver se o usuário autenticou.
    - Se aprovado: faz exchange auth_code → tokens e salva no pool.
    - Se pendente: retorna status "pending".
    - Se erro: retorna status "error" com mensagem.
    O frontend chama isso a cada 5s até receber "saved" ou "error".
    """
    return await device_code_poll(request_id)


@router.get("/codex/device-code/status/{request_id}")
async def codex_device_status(request_id: str, user=Depends(get_current_user)):
    """Consulta o status atual (sem fazer poll)."""
    return get_device_session_status(request_id)


@router.post("/codex/extract-auth")
async def codex_extract_auth(body: dict, user=Depends(get_current_user)):
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
