"""Per-user xAI OAuth device flow, encrypted token storage and refresh."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from src.core.auth import _secret
from src.db.models import GrokAccount, get_session_db


ISSUER = "https://auth.x.ai"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
PUBLIC_API_BASE = "https://api.x.ai/v1"
OAUTH_API_BASE = "https://cli-chat-proxy.grok.com/v1"
GROK_CLIENT_VERSION = "0.2.102"
SCOPES = "openid profile email offline_access grok-cli:access api:access"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

_device_sessions: dict[str, dict] = {}
_refresh_locks: dict[str, asyncio.Lock] = {}
_discovery_cache: tuple[float, dict] | None = None


def _crypt_key() -> bytes:
    return hashlib.sha256(_secret() + b":grok-oauth:v1").digest()


def _keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < size:
        output.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(output[:size])


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    key = _crypt_key()
    nonce = os.urandom(16)
    raw = value.encode("utf-8")
    ciphertext = bytes(a ^ b for a, b in zip(raw, _keystream(key, nonce, len(raw))))
    signature = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return "v1:" + base64.urlsafe_b64encode(nonce + signature + ciphertext).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value or not value.startswith("v1:"):
        return ""
    try:
        packed = base64.urlsafe_b64decode(value[3:].encode("ascii"))
        nonce, signature, ciphertext = packed[:16], packed[16:48], packed[48:]
        key = _crypt_key()
        expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return ""
        raw = bytes(a ^ b for a, b in zip(ciphertext, _keystream(key, nonce, len(ciphertext))))
        return raw.decode("utf-8")
    except Exception:
        return ""


def _public(row: GrokAccount) -> dict:
    return {
        "id": row.id,
        "subject": row.subject,
        "email": row.email,
        "label": row.label or row.email or "Conta Grok",
        "expires_at": int(row.expires_at or 0),
        "scope": row.scope,
        "access_status": row.access_status or "unknown",
        "last_error": row.last_error or "",
        "selected": bool(row.is_selected),
        "enabled": bool(row.is_enabled),
        "has_refresh_token": bool(row.refresh_token_encrypted),
    }


def _internal(row: GrokAccount) -> dict:
    item = _public(row)
    item.update({
        "access_token": decrypt_secret(row.access_token_encrypted),
        "refresh_token": decrypt_secret(row.refresh_token_encrypted),
        "id_token": decrypt_secret(row.id_token_encrypted),
    })
    return item


def list_accounts(user_id: int, *, internal: bool = False) -> list[dict]:
    db = get_session_db()
    try:
        rows = (
            db.query(GrokAccount)
            .filter(GrokAccount.user_id == user_id)
            .order_by(GrokAccount.is_selected.desc(), GrokAccount.created_at.asc())
            .all()
        )
        return [(_internal(row) if internal else _public(row)) for row in rows]
    finally:
        db.close()


def get_account(user_id: int, account_id: str | None = None) -> dict | None:
    db = get_session_db()
    try:
        query = db.query(GrokAccount).filter(
            GrokAccount.user_id == user_id,
            GrokAccount.is_enabled == True,
        )
        row = (
            query.filter(GrokAccount.id == account_id).first()
            if account_id
            else query.order_by(GrokAccount.is_selected.desc(), GrokAccount.created_at.asc()).first()
        )
        return _internal(row) if row else None
    finally:
        db.close()


def save_account(user_id: int, tokens: dict, identity: dict, *, select: bool = True) -> dict:
    access_token = str(tokens.get("access_token") or "").strip()
    subject = str(identity.get("sub") or identity.get("id") or "").strip()
    if not access_token:
        raise ValueError("access_token ausente na resposta OAuth da xAI")
    if not subject:
        raise ValueError("A xAI nao retornou a identidade da conta")
    email = str(identity.get("email") or "").strip().lower()
    label = str(identity.get("name") or identity.get("preferred_username") or email or f"Grok {subject[-8:]}")
    db = get_session_db()
    try:
        row = db.query(GrokAccount).filter(
            GrokAccount.user_id == user_id,
            GrokAccount.subject == subject,
        ).first()
        if not row:
            row = GrokAccount(id=f"grok_{uuid4().hex}", user_id=user_id, subject=subject)
            db.add(row)
        if select:
            db.query(GrokAccount).filter(GrokAccount.user_id == user_id).update({"is_selected": False})
            row.is_selected = True
        row.email = email
        row.label = label
        row.access_token_encrypted = encrypt_secret(access_token)
        if tokens.get("refresh_token"):
            row.refresh_token_encrypted = encrypt_secret(str(tokens["refresh_token"]))
        if tokens.get("id_token"):
            row.id_token_encrypted = encrypt_secret(str(tokens["id_token"]))
        row.expires_at = int(time.time()) + int(tokens.get("expires_in") or 3600)
        row.scope = str(tokens.get("scope") or SCOPES)
        row.access_status = "unknown"
        row.last_error = ""
        row.is_enabled = True
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return _public(row)
    finally:
        db.close()


def update_account(user_id: int, account_id: str, data: dict) -> dict | None:
    db = get_session_db()
    try:
        row = db.query(GrokAccount).filter(
            GrokAccount.user_id == user_id,
            GrokAccount.id == account_id,
        ).first()
        if not row:
            return None
        if data.get("select"):
            db.query(GrokAccount).filter(GrokAccount.user_id == user_id).update({"is_selected": False})
            row.is_selected = True
        if "access_token" in data:
            row.access_token_encrypted = encrypt_secret(str(data.get("access_token") or ""))
        if data.get("refresh_token"):
            row.refresh_token_encrypted = encrypt_secret(str(data["refresh_token"]))
        if data.get("id_token"):
            row.id_token_encrypted = encrypt_secret(str(data["id_token"]))
        for key in ("expires_at", "scope", "access_status", "last_error", "is_enabled"):
            if key in data:
                setattr(row, key, data[key])
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return _public(row)
    finally:
        db.close()


def remove_account(user_id: int, account_id: str) -> bool:
    db = get_session_db()
    try:
        row = db.query(GrokAccount).filter(
            GrokAccount.user_id == user_id,
            GrokAccount.id == account_id,
        ).first()
        if not row:
            return False
        was_selected = bool(row.is_selected)
        db.delete(row)
        db.flush()
        if was_selected:
            replacement = db.query(GrokAccount).filter(
                GrokAccount.user_id == user_id,
                GrokAccount.is_enabled == True,
            ).order_by(GrokAccount.created_at.asc()).first()
            if replacement:
                replacement.is_selected = True
        db.commit()
        return True
    finally:
        db.close()


def export_accounts(user_id: int) -> dict:
    accounts = list_accounts(user_id, internal=True)
    return {
        "selected_account_id": next((item["id"] for item in accounts if item["selected"]), ""),
        "accounts": accounts,
    }


def import_accounts(user_id: int, payload: dict) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("accounts", []), list):
        raise ValueError("Contas Grok invalidas")
    selected_id = str(payload.get("selected_account_id") or "")
    imported = 0
    for raw in payload.get("accounts", []):
        if not isinstance(raw, dict) or not raw.get("access_token"):
            continue
        subject = str(raw.get("subject") or raw.get("id") or "")
        if not subject:
            continue
        saved = save_account(
            user_id,
            raw,
            {"sub": subject, "email": raw.get("email", ""), "name": raw.get("label", "")},
            select=not selected_id or str(raw.get("id") or "") == selected_id,
        )
        update_account(user_id, saved["id"], {
            "access_status": raw.get("access_status", "unknown"),
            "last_error": raw.get("last_error", ""),
        })
        imported += 1
    return {"accounts": imported}


def _validate_endpoint(value: str, field: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "auth.x.ai":
        raise ValueError(f"Discovery OAuth da xAI retornou {field} inseguro")
    return value


async def discovery(*, force: bool = False) -> dict:
    global _discovery_cache
    if not force and _discovery_cache and time.monotonic() - _discovery_cache[0] < 3600:
        return _discovery_cache[1]
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.get(DISCOVERY_URL)
    if response.status_code != 200:
        raise ValueError(f"Discovery OAuth da xAI falhou: HTTP {response.status_code}")
    data = response.json()
    if data.get("issuer") != ISSUER:
        raise ValueError("Issuer OAuth inesperado na discovery da xAI")
    normalized = {
        "issuer": ISSUER,
        "device_authorization_endpoint": _validate_endpoint(str(data.get("device_authorization_endpoint") or ""), "device endpoint"),
        "token_endpoint": _validate_endpoint(str(data.get("token_endpoint") or ""), "token endpoint"),
        "userinfo_endpoint": _validate_endpoint(str(data.get("userinfo_endpoint") or ""), "userinfo endpoint"),
    }
    _discovery_cache = (time.monotonic(), normalized)
    return normalized


def _jwt_identity(token: str) -> dict:
    try:
        segment = token.split(".")[1]
        segment += "=" * (-len(segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(segment.encode("ascii")))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


async def _identity_for_tokens(tokens: dict, config: dict) -> dict:
    access_token = str(tokens.get("access_token") or "")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            config["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code == 200 and isinstance(response.json(), dict):
        return response.json()
    return _jwt_identity(str(tokens.get("id_token") or ""))


async def start_device_oauth(user_id: int) -> dict:
    config = await discovery()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(config["device_authorization_endpoint"], data={
            "client_id": CLIENT_ID,
            "scope": SCOPES,
        })
    if response.status_code >= 400:
        raise ValueError(f"A xAI recusou o inicio do login: HTTP {response.status_code}: {response.text[:300]}")
    data = response.json()
    device_code = str(data.get("device_code") or "")
    user_code = str(data.get("user_code") or "")
    if not device_code or not user_code:
        raise ValueError("Resposta de device code da xAI incompleta")
    request_id = f"grokoauth_{uuid4().hex}"
    expires_in = max(60, int(data.get("expires_in") or 600))
    interval = max(3, int(data.get("interval") or 5))
    _device_sessions[request_id] = {
        "user_id": user_id,
        "device_code": device_code,
        "token_endpoint": config["token_endpoint"],
        "userinfo_endpoint": config["userinfo_endpoint"],
        "expires_at": time.time() + expires_in,
        "interval": interval,
        "next_poll_at": 0.0,
    }
    return {
        "request_id": request_id,
        "user_code": user_code,
        "verification_uri": str(data.get("verification_uri") or data.get("verification_url") or ""),
        "verification_uri_complete": str(data.get("verification_uri_complete") or ""),
        "expires_in": expires_in,
        "interval": interval,
    }


async def poll_device_oauth(user_id: int, request_id: str) -> dict:
    session = _device_sessions.get(request_id)
    if not session or session.get("user_id") != user_id:
        raise ValueError("Sessao OAuth do Grok inexistente ou expirada")
    if time.time() >= float(session["expires_at"]):
        _device_sessions.pop(request_id, None)
        return {"status": "expired", "message": "O codigo de login do Grok expirou"}
    now = time.time()
    if now < float(session.get("next_poll_at") or 0):
        return {"status": "pending", "retry_after": max(1, int(session["next_poll_at"] - now))}
    session["next_poll_at"] = now + int(session["interval"])
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(session["token_endpoint"], data={
            "grant_type": DEVICE_GRANT,
            "client_id": CLIENT_ID,
            "device_code": session["device_code"],
        })
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code < 400 and data.get("access_token"):
        identity = await _identity_for_tokens(data, session)
        account = save_account(user_id, data, identity)
        _device_sessions.pop(request_id, None)
        return {"status": "saved", "account": account}
    error = str(data.get("error") or "")
    if error == "authorization_pending":
        return {"status": "pending", "retry_after": int(session["interval"])}
    if error == "slow_down":
        session["interval"] = int(session["interval"]) + 5
        return {"status": "pending", "retry_after": int(session["interval"])}
    _device_sessions.pop(request_id, None)
    messages = {
        "access_denied": "Login do Grok cancelado pelo usuario",
        "expired_token": "O codigo de login do Grok expirou",
    }
    return {"status": "error", "message": messages.get(error, str(data.get("error_description") or error or "Falha no OAuth do Grok"))}


async def refresh_access_token(user_id: int, account_id: str, *, force: bool = False) -> dict:
    lock = _refresh_locks.setdefault(account_id, asyncio.Lock())
    async with lock:
        account = get_account(user_id, account_id)
        if not account:
            raise ValueError("Conta Grok nao encontrada")
        if not force and int(account.get("expires_at") or 0) > int(time.time()) + 120:
            return account
        refresh_token = str(account.get("refresh_token") or "")
        if not refresh_token:
            raise ValueError("Conta Grok sem refresh_token; conecte novamente")
        config = await discovery()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(config["token_endpoint"], data={
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "refresh_token": refresh_token,
            })
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.status_code >= 400 or not data.get("access_token"):
            update_account(user_id, account_id, {
                "access_status": "error",
                "last_error": str(data.get("error_description") or data.get("error") or f"HTTP {response.status_code}"),
            })
            raise ValueError("Falha ao renovar a conta Grok; conecte-a novamente")
        update_account(user_id, account_id, {
            "access_token": data["access_token"],
            # A xAI pode rotacionar; se nao vier um novo, preservamos o atual.
            "refresh_token": data.get("refresh_token") or refresh_token,
            "id_token": data.get("id_token") or "",
            "expires_at": int(time.time()) + int(data.get("expires_in") or 3600),
            "scope": data.get("scope") or account.get("scope") or SCOPES,
            "last_error": "",
        })
        return get_account(user_id, account_id) or {}


async def get_valid_account(user_id: int, account_id: str | None = None) -> dict:
    account = get_account(user_id, account_id)
    if not account:
        raise ValueError("Conecte uma conta Grok antes de usar este provider")
    if int(account.get("expires_at") or 0) <= int(time.time()) + 120:
        account = await refresh_access_token(user_id, account["id"])
    return account


async def test_account(user_id: int, account_id: str) -> dict:
    account = await get_valid_account(user_id, account_id)
    for attempt in range(2):
        from src.core.grok_client import request_headers
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{OAUTH_API_BASE}/responses",
                headers=request_headers(account, "grok-4.5", stream=False),
                json={
                    "model": "grok-4.5",
                    "input": "Reply with OK only.",
                    "stream": False,
                    "reasoning": {"effort": "low"},
                    "include": ["reasoning.encrypted_content"],
                },
            )
        if response.status_code == 401 and attempt == 0:
            account = await refresh_access_token(user_id, account_id, force=True)
            continue
        if response.status_code in {402, 403}:
            update_account(user_id, account_id, {"access_status": "blocked", "last_error": response.text[:500]})
            raise ValueError("Conta conectada, mas a assinatura/franquia do Grok Build nao foi liberada pela xAI")
        if response.status_code == 429:
            update_account(user_id, account_id, {"access_status": "rate_limited", "last_error": response.text[:500]})
            return {
                "ok": True,
                "access_status": "rate_limited",
                "message": "OAuth e assinatura aceitos; Grok 4.5 esta temporariamente sem capacidade.",
                "models": [],
            }
        if response.status_code >= 400:
            update_account(user_id, account_id, {"access_status": "error", "last_error": response.text[:500]})
            raise ValueError(f"Teste do Grok falhou: HTTP {response.status_code}")
        update_account(user_id, account_id, {"access_status": "confirmed", "last_error": ""})
        return {
            "ok": True,
            "access_status": "confirmed",
            "message": "Inferencia Grok OAuth confirmada.",
            "models": [],
        }
    raise ValueError("Nao foi possivel validar a conta Grok")
