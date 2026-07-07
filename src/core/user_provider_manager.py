"""Per-user provider configuration with global fallback.

This module is intentionally small for the first user-provider phase: it stores
user-owned provider configs, masks keys for API responses, and exposes an
internal active config that can later be wired into the LLM hot path.
"""

import base64
from datetime import datetime, timezone

from src.core.provider_manager import get_active_config
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
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _internal_config(row: UserProviderConfig) -> dict:
    return {
        "provider_id": row.provider_id,
        "name": row.display_name or row.provider_id,
        "base_url": row.base_url,
        "api_key": _decrypt_api_key(row.api_key_encrypted or ""),
        "api_format": row.api_format or "chat_completions",
        "model_id": row.model,
        "model_name": row.model,
    }


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
            return _internal_config(row)
    finally:
        db.close()
    return get_active_config()
