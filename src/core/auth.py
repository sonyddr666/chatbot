"""Autenticacao simples com stdlib: PBKDF2 para senha e token HMAC."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from src.config import settings


TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
LOCAL_SECRET_PATH = os.path.join("data", "auth_secret.key")


def _secret() -> bytes:
    raw = getattr(settings, "auth_secret_key", "") or os.environ.get("AUTH_SECRET_KEY", "")
    if raw:
        return raw.encode("utf-8")

    os.makedirs(os.path.dirname(LOCAL_SECRET_PATH), exist_ok=True)
    if not os.path.exists(LOCAL_SECRET_PATH):
        with open(LOCAL_SECRET_PATH, "w", encoding="utf-8") as f:
            f.write(_b64(os.urandom(32)))
    with open(LOCAL_SECRET_PATH, "r", encoding="utf-8") as f:
        return f.read().strip().encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return f"pbkdf2_sha256${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, salt_b64, digest_b64 = password_hash.split("$", 2)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    salt = _unb64(salt_b64)
    expected = _unb64(digest_b64)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return hmac.compare_digest(actual, expected)


def create_access_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_unb64(body).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def rag_collection_for_user(user_id: int) -> str:
    return f"user_{user_id}_documents"
