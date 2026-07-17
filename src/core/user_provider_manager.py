"""Per-user provider configuration with global fallback.

This module is intentionally small for the first user-provider phase: it stores
user-owned provider configs, masks keys for API responses, and exposes an
internal active config that can later be wired into the LLM hot path.
"""

import base64
from datetime import datetime, timezone

from src.core.provider_manager import get_active_config, get_provider
from src.core.time_utils import utc_isoformat
from src.db.models import UserProviderConfig, get_session_db


def _encrypt_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    encoded = base64.urlsafe_b64encode(api_key.encode("utf-8")).decode("ascii")
    return f"local:{encoded}"


def _decrypt_api_key(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("local:"):
        return ""
    try:
        raw = value.removeprefix("local:")
        return base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return api_key[:2] + "..."
    return api_key[:6] + "..." + api_key[-4:]


def _public_config(row: UserProviderConfig) -> dict:
    api_key = _decrypt_api_key(row.api_key_encrypted or "")
    return {
        "id": row.id,
        "user_id": row.user_id,
        "provider_id": row.provider_id,
        "display_name": row.display_name or row.provider_id,
        "base_url": row.base_url,
        "model": row.model,
        "api_format": row.api_format,
        "is_enabled": bool(row.is_enabled),
        "is_default": bool(row.is_default),
        "has_key": bool(api_key),
        "key_masked": _mask_api_key(api_key),
        "created_at": utc_isoformat(row.created_at) if row.created_at else None,
        "updated_at": utc_isoformat(row.updated_at) if row.updated_at else None,
    }


def _internal_config(row: UserProviderConfig) -> dict:
    config = {
        "provider_id": row.provider_id,
        "name": row.display_name or row.provider_id,
        "base_url": row.base_url,
        "api_key": _decrypt_api_key(row.api_key_encrypted or ""),
        "api_format": row.api_format or "chat_completions",
        "model_id": row.model,
        "model_name": row.model,
    }
    provider = get_provider(row.provider_id)
    model = {}
    if provider:
        model = next((item for item in provider.get("models", []) if item.get("id") == row.model), {})
    if not model:
        from src.core.model_catalog import enrich_builtin_models
        model = enrich_builtin_models(row.provider_id, [{"id": row.model, "name": row.model}])[0]
    if model:
        config.update({
            "model_name": model.get("name", row.model),
            "supports_images": model.get("supports_images"),
            "supports_thinking": model.get("supports_thinking"),
            "supports_tools": model.get("supports_tools"),
            "image_generation": bool(model.get("image_generation")),
            "reasoning_options": model.get("reasoning_options", []),
            "reasoning_style": provider.get("reasoning_style", "") if provider else "",
        })
    from src.core.model_capabilities import with_reasoning_capabilities
    return with_reasoning_capabilities(config)


def metadata_from_config(config: dict) -> dict:
    return {
        "provider_id": config.get("provider_id", ""),
        "provider_name": config.get("name", config.get("provider_id", "")),
        "model_id": config.get("model_id", ""),
        "model_name": config.get("model_name", config.get("model_id", "")),
    }


def get_active_model_metadata_for_user(user_id: int) -> dict:
    return metadata_from_config(get_active_config_for_user(user_id))


def create_user_provider(user_id: int, data: dict) -> dict:
    provider_id = str(data.get("provider_id", "")).strip()
    model = str(data.get("model", "")).strip()
    if not provider_id:
        raise ValueError("provider_id e obrigatorio")
    if not model:
        raise ValueError("model e obrigatorio")

    db = get_session_db()
    try:
        if bool(data.get("is_default", False)):
            (
                db.query(UserProviderConfig)
                .filter(UserProviderConfig.user_id == user_id)
                .update({"is_default": False})
            )
        row = UserProviderConfig(
            user_id=user_id,
            provider_id=provider_id,
            display_name=str(data.get("display_name", "")).strip() or provider_id,
            base_url=str(data.get("base_url", "")).strip(),
            model=model,
            api_format=str(data.get("api_format", "chat_completions")).strip() or "chat_completions",
            api_key_encrypted=_encrypt_api_key(str(data.get("api_key", ""))),
            is_enabled=bool(data.get("is_enabled", True)),
            is_default=bool(data.get("is_default", False)),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        public = _public_config(row)
        db.expunge(row)
        return public
    finally:
        db.close()


def list_user_providers(user_id: int) -> list[dict]:
    db = get_session_db()
    try:
        rows = (
            db.query(UserProviderConfig)
            .filter(UserProviderConfig.user_id == user_id)
            .order_by(UserProviderConfig.is_default.desc(), UserProviderConfig.created_at.desc())
            .all()
        )
        return [_public_config(row) for row in rows]
    finally:
        db.close()


def export_user_providers(user_id: int, include_api_keys: bool = False) -> list[dict]:
    """Exporta somente as configuracoes pertencentes ao usuario atual."""
    db = get_session_db()
    try:
        rows = (
            db.query(UserProviderConfig)
            .filter(UserProviderConfig.user_id == user_id)
            .order_by(UserProviderConfig.is_default.desc(), UserProviderConfig.created_at.asc())
            .all()
        )
        exported = []
        for row in rows:
            item = {
                "provider_id": row.provider_id,
                "display_name": row.display_name or row.provider_id,
                "base_url": row.base_url,
                "model": row.model,
                "api_format": row.api_format or "chat_completions",
                "is_enabled": bool(row.is_enabled),
                "is_default": bool(row.is_default),
            }
            if include_api_keys:
                item["api_key"] = _decrypt_api_key(row.api_key_encrypted or "")
            exported.append(item)
        return exported
    finally:
        db.close()


def _normalize_user_provider_import(items: list[dict]) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("personal_providers deve ser uma lista")
    if len(items) > 100:
        raise ValueError("O arquivo pode importar no maximo 100 providers pessoais")

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Cada provider pessoal deve ser um objeto JSON")
        provider_id = str(item.get("provider_id", "")).strip()
        model = str(item.get("model", "")).strip()
        if not provider_id or not model:
            raise ValueError("Provider pessoal importado precisa de provider_id e model")
        normalized.append({
            "provider_id": provider_id,
            "display_name": str(item.get("display_name", provider_id)).strip() or provider_id,
            "base_url": str(item.get("base_url", "")).strip(),
            "model": model,
            "api_format": str(item.get("api_format", "chat_completions")).strip() or "chat_completions",
            "is_enabled": bool(item.get("is_enabled", True)),
            "is_default": bool(item.get("is_default", False)),
            "has_api_key_field": "api_key" in item,
            "api_key": str(item.get("api_key", "")),
        })
    return normalized


def import_user_providers(user_id: int, items: list[dict]) -> dict:
    """Restaura providers pessoais do usuario sem tocar em configuracoes de outras contas."""
    normalized = _normalize_user_provider_import(items)
    db = get_session_db()
    created = []
    updated = []
    keys_imported = 0
    default_row = None
    try:
        for item in normalized:
            row = (
                db.query(UserProviderConfig)
                .filter(
                    UserProviderConfig.user_id == user_id,
                    UserProviderConfig.provider_id == item["provider_id"],
                    UserProviderConfig.model == item["model"],
                    UserProviderConfig.base_url == item["base_url"],
                )
                .order_by(UserProviderConfig.id.desc())
                .first()
            )
            if row:
                updated.append(item["provider_id"])
            else:
                row = UserProviderConfig(
                    user_id=user_id,
                    provider_id=item["provider_id"],
                    model=item["model"],
                    base_url=item["base_url"],
                )
                db.add(row)
                created.append(item["provider_id"])

            row.display_name = item["display_name"]
            row.api_format = item["api_format"]
            row.is_enabled = item["is_enabled"]
            row.updated_at = datetime.now(timezone.utc)
            if item["has_api_key_field"]:
                row.api_key_encrypted = _encrypt_api_key(item["api_key"])
                if item["api_key"]:
                    keys_imported += 1
            if item["is_default"] and item["is_enabled"]:
                default_row = row

        if default_row is not None:
            (
                db.query(UserProviderConfig)
                .filter(UserProviderConfig.user_id == user_id)
                .update({"is_default": False})
            )
            default_row.is_default = True
        db.commit()
        return {
            "created": created,
            "updated": updated,
            "keys_imported": keys_imported,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def activate_user_provider(user_id: int, config_id: int) -> bool:
    db = get_session_db()
    try:
        row = (
            db.query(UserProviderConfig)
            .filter(
                UserProviderConfig.id == config_id,
                UserProviderConfig.user_id == user_id,
                UserProviderConfig.is_enabled == True,
            )
            .first()
        )
        if not row:
            return False
        (
            db.query(UserProviderConfig)
            .filter(UserProviderConfig.user_id == user_id)
            .update({"is_default": False})
        )
        row.is_default = True
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        return True
    finally:
        db.close()


def use_global_provider(user_id: int) -> bool:
    """Remove o override pessoal para o chat voltar ao provider global ativo."""
    db = get_session_db()
    try:
        changed = (
            db.query(UserProviderConfig)
            .filter(
                UserProviderConfig.user_id == user_id,
                UserProviderConfig.is_default == True,
            )
            .update({"is_default": False})
        )
        db.commit()
        return bool(changed)
    finally:
        db.close()


def activate_builtin_for_user(user_id: int, provider_id: str, model_id: str = "") -> dict:
    """Create/update a keyless per-user binding for an OAuth built-in provider."""
    provider = get_provider(provider_id)
    if not provider or provider_id not in {"grok-oauth", "antigravity"}:
        raise ValueError("Provider OAuth por usuario nao suportado")
    enabled_models = [model for model in provider.get("models", []) if model.get("enabled", True)]
    selected_model = next((model for model in enabled_models if model.get("id") == model_id), None)
    if not selected_model:
        selected_model = next((model for model in enabled_models if model.get("active")), None) or (enabled_models[0] if enabled_models else None)
    if not selected_model:
        raise ValueError("Nenhum modelo ativo neste provider")

    db = get_session_db()
    try:
        db.query(UserProviderConfig).filter(UserProviderConfig.user_id == user_id).update({"is_default": False})
        row = db.query(UserProviderConfig).filter(
            UserProviderConfig.user_id == user_id,
            UserProviderConfig.provider_id == provider_id,
        ).order_by(UserProviderConfig.id.desc()).first()
        if not row:
            row = UserProviderConfig(user_id=user_id, provider_id=provider_id)
            db.add(row)
        row.display_name = str(provider.get("name") or provider_id)
        row.base_url = str(provider.get("base_url") or "")
        row.model = str(selected_model.get("id") or "")
        row.api_format = str(provider.get("api_format") or "openai_responses")
        row.api_key_encrypted = ""
        row.is_enabled = True
        row.is_default = True
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return _public_config(row)
    finally:
        db.close()


def get_active_config_for_user(user_id: int) -> dict:
    db = get_session_db()
    try:
        row = (
            db.query(UserProviderConfig)
            .filter(
                UserProviderConfig.user_id == user_id,
                UserProviderConfig.is_default == True,
                UserProviderConfig.is_enabled == True,
            )
            .order_by(UserProviderConfig.updated_at.desc(), UserProviderConfig.id.desc())
            .first()
        )
        if row:
            config = _internal_config(row)
            config["user_id"] = user_id
            return config
    finally:
        db.close()
    # Credenciais globais pertencem ao administrador. Uma conta comum sem
    # override pessoal recebe somente o gateway publico OpenCode Free.
    from src.db.repository import UserRepo
    user = UserRepo.get(user_id)
    config = get_active_config() if user and user.is_admin else get_active_config("opencode-zen-free")
    config["user_id"] = user_id
    return config
