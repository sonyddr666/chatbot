"""Per-user OAuth account storage and PKCE flow for Google Antigravity."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

import httpx

from src.core.auth import _secret
from src.db.models import AntigravityAccount, get_session_db


AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
PUBLIC_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
PUBLIC_CLIENT_SECRET = "GOCSPX-" + "K58FWR486LdLJ1mLB8sXC4z6qDAf"
DEFAULT_REDIRECT_URI = "http://localhost:51121/oauth-callback"
SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
)

_oauth_sessions: dict[str, dict] = {}


def _crypt_key() -> bytes:
    return hashlib.sha256(_secret() + b":antigravity-oauth:v1").digest()


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
    if not value:
        return ""
    if not value.startswith("v1:"):
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


def _json(value: str, fallback):
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, ValueError):
        return fallback


def _public(row: AntigravityAccount) -> dict:
    models = _json(row.models_json, {})
    return {
        "id": row.id,
        "email": row.email,
        "label": row.label or row.email,
        "expires_at": int(row.expires_at or 0),
        "project_id": row.project_id,
        "endpoint": row.endpoint,
        "account_type": row.account_type,
        "selected": bool(row.is_selected),
        "enabled": bool(row.is_enabled),
        "model_count": len(models) if isinstance(models, dict) else 0,
        "models": models if isinstance(models, dict) else {},
        "quotas": _json(row.quota_json, []),
        "has_refresh_token": bool(row.refresh_token_encrypted),
    }


def _internal(row: AntigravityAccount) -> dict:
    result = _public(row)
    result.update({
        "access_token": decrypt_secret(row.access_token_encrypted),
        "refresh_token": decrypt_secret(row.refresh_token_encrypted),
        "client_id": row.client_id or PUBLIC_CLIENT_ID,
        "client_secret": decrypt_secret(row.client_secret_encrypted),
    })
    return result


def list_accounts(user_id: int) -> list[dict]:
    db = get_session_db()
    try:
        rows = (
            db.query(AntigravityAccount)
            .filter(AntigravityAccount.user_id == user_id)
            .order_by(AntigravityAccount.is_selected.desc(), AntigravityAccount.created_at.asc())
            .all()
        )
        return [_public(row) for row in rows]
    finally:
        db.close()


def export_accounts(user_id: int) -> dict:
    """Exporta auth portavel descriptografado para backup administrativo."""
    db = get_session_db()
    try:
        rows = db.query(AntigravityAccount).filter(AntigravityAccount.user_id == user_id).all()
        accounts = []
        selected_id = ""
        for row in rows:
            item = _internal(row)
            item["models"] = _json(row.models_json, {})
            item["quotas"] = _json(row.quota_json, [])
            item["account_id"] = row.id
            accounts.append(item)
            if row.is_selected:
                selected_id = row.id
        return {"selected_account_id": selected_id, "accounts": accounts}
    finally:
        db.close()


def import_accounts(user_id: int, payload: dict) -> dict:
    """Restaura contas sem depender de chamadas externas ao Google."""
    if not isinstance(payload, dict) or not isinstance(payload.get("accounts", []), list):
        raise ValueError("Contas Antigravity invalidas")
    selected_id = str(payload.get("selected_account_id") or "")
    imported = 0
    for raw in payload.get("accounts", []):
        if not isinstance(raw, dict) or not raw.get("access_token") or not raw.get("email"):
            continue
        original_id = str(raw.get("account_id") or raw.get("id") or "")
        saved = save_account(user_id, raw, select=not selected_id or original_id == selected_id)
        update_account(user_id, saved["id"], {
            "models": raw.get("models", {}),
            "quotas": raw.get("quotas", []),
            "project_id": raw.get("project_id", ""),
            "endpoint": raw.get("endpoint", ""),
            "account_type": raw.get("account_type", ""),
        })
        imported += 1
    return {"accounts": imported}


def get_account(user_id: int, account_id: str | None = None) -> dict | None:
    db = get_session_db()
    try:
        query = db.query(AntigravityAccount).filter(
            AntigravityAccount.user_id == user_id,
            AntigravityAccount.is_enabled == True,
        )
        if account_id:
            row = query.filter(AntigravityAccount.id == account_id).first()
        else:
            row = query.order_by(AntigravityAccount.is_selected.desc(), AntigravityAccount.created_at.asc()).first()
        return _internal(row) if row else None
    finally:
        db.close()


def save_account(user_id: int, data: dict, *, select: bool = True) -> dict:
    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("access_token ausente")
    email = str(data.get("email") or "").strip().lower()
    if not email:
        raise ValueError("email ausente na conta Antigravity")

    db = get_session_db()
    try:
        row = db.query(AntigravityAccount).filter(
            AntigravityAccount.user_id == user_id,
            AntigravityAccount.email == email,
        ).first()
        if not row:
            row = AntigravityAccount(id=f"ag_{uuid4().hex}", user_id=user_id, email=email)
            db.add(row)
        if select:
            db.query(AntigravityAccount).filter(AntigravityAccount.user_id == user_id).update(
                {"is_selected": False}
            )
            row.is_selected = True
        row.label = str(data.get("label") or email)
        row.access_token_encrypted = encrypt_secret(access_token)
        refresh = str(data.get("refresh_token") or "")
        if refresh:
            row.refresh_token_encrypted = encrypt_secret(refresh)
        row.client_id = str(data.get("client_id") or PUBLIC_CLIENT_ID)
        secret = str(data.get("client_secret") or "")
        if secret:
            row.client_secret_encrypted = encrypt_secret(secret)
        row.expires_at = int(data.get("expires_at") or (time.time() + 3600))
        row.project_id = str(data.get("project_id") or row.project_id or "")
        row.endpoint = str(data.get("endpoint") or row.endpoint or "")
        row.account_type = str(data.get("account_type") or row.account_type or "")
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
        row = db.query(AntigravityAccount).filter(
            AntigravityAccount.user_id == user_id,
            AntigravityAccount.id == account_id,
        ).first()
        if not row:
            return None
        if data.get("select"):
            db.query(AntigravityAccount).filter(AntigravityAccount.user_id == user_id).update(
                {"is_selected": False}
            )
            row.is_selected = True
        if "access_token" in data:
            row.access_token_encrypted = encrypt_secret(str(data["access_token"]))
        if data.get("refresh_token"):
            row.refresh_token_encrypted = encrypt_secret(str(data["refresh_token"]))
        for source, target in (
            ("expires_at", "expires_at"), ("project_id", "project_id"),
            ("endpoint", "endpoint"), ("account_type", "account_type"),
        ):
            if source in data:
                setattr(row, target, data[source])
        if "models" in data:
            row.models_json = json.dumps(data["models"], ensure_ascii=False)
        if "quotas" in data:
            row.quota_json = json.dumps(data["quotas"], ensure_ascii=False)
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return _public(row)
    finally:
        db.close()


def remove_account(user_id: int, account_id: str) -> bool:
    db = get_session_db()
    try:
        row = db.query(AntigravityAccount).filter(
            AntigravityAccount.user_id == user_id,
            AntigravityAccount.id == account_id,
        ).first()
        if not row:
            return False
        was_selected = bool(row.is_selected)
        db.delete(row)
        db.flush()
        if was_selected:
            replacement = db.query(AntigravityAccount).filter(
                AntigravityAccount.user_id == user_id,
                AntigravityAccount.is_enabled == True,
            ).order_by(AntigravityAccount.created_at.asc()).first()
            if replacement:
                replacement.is_selected = True
        db.commit()
        return True
    finally:
        db.close()


def start_oauth(user_id: int) -> dict:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(24)
    request_id = f"agoauth_{uuid4().hex}"
    _oauth_sessions[request_id] = {
        "user_id": user_id,
        "verifier": verifier,
        "state": state,
        "created_at": time.time(),
        "redirect_uri": DEFAULT_REDIRECT_URI,
    }
    params = {
        "client_id": PUBLIC_CLIENT_ID,
        "redirect_uri": DEFAULT_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return {"request_id": request_id, "auth_url": f"{AUTHORIZE_URL}?{urlencode(params)}"}


async def finish_oauth(user_id: int, request_id: str, callback_url: str) -> dict:
    session = _oauth_sessions.pop(request_id, None)
    if not session or session.get("user_id") != user_id:
        raise ValueError("Sessao OAuth inexistente ou expirada")
    if time.time() - float(session["created_at"]) > 600:
        raise ValueError("Sessao OAuth expirada")
    query = parse_qs(urlparse(callback_url.strip()).query)
    code = str((query.get("code") or [""])[0])
    state = str((query.get("state") or [""])[0])
    if not code:
        raise ValueError("Cole a URL completa que contem o parametro code")
    if not secrets.compare_digest(state, str(session["state"])):
        raise ValueError("State OAuth invalido")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": PUBLIC_CLIENT_ID,
            "client_secret": PUBLIC_CLIENT_SECRET,
            "code_verifier": session["verifier"],
            "redirect_uri": session["redirect_uri"],
        })
        if response.status_code >= 400:
            raise ValueError(f"Troca OAuth falhou: HTTP {response.status_code}: {response.text[:400]}")
        tokens = response.json()
        info_response = await client.get(USERINFO_URL, headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        info = info_response.json() if info_response.status_code == 200 else {}
    return save_account(user_id, {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(tokens.get("expires_in", 3600)),
        "email": info.get("email", ""),
        "label": info.get("name") or info.get("email", ""),
        "client_id": PUBLIC_CLIENT_ID,
        "client_secret": PUBLIC_CLIENT_SECRET,
    })


async def import_auth(user_id: int, body: dict) -> dict:
    accounts = body.get("accounts") if isinstance(body, dict) else None
    selected_id = str(body.get("selected_account_id") or "") if isinstance(body, dict) else ""
    candidates = accounts if isinstance(accounts, list) else [body]
    imported = []
    async with httpx.AsyncClient(timeout=20) as client:
        for raw in candidates:
            if not isinstance(raw, dict):
                continue
            access_token = str(raw.get("access_token") or "")
            if not access_token:
                continue
            email = str(raw.get("email") or "")
            if not email:
                response = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
                if response.status_code == 200:
                    email = str(response.json().get("email") or "")
            data = dict(raw)
            data["email"] = email
            imported.append(save_account(
                user_id,
                data,
                select=not selected_id or str(raw.get("account_id") or raw.get("id") or "") == selected_id,
            ))
    if not imported:
        raise ValueError("Formato de auth.json do Antigravity nao reconhecido")
    return imported


async def refresh_access_token(user_id: int, account_id: str) -> dict:
    account = get_account(user_id, account_id)
    if not account or not account.get("refresh_token"):
        raise ValueError("Conta sem refresh_token")
    form = {
        "grant_type": "refresh_token",
        "refresh_token": account["refresh_token"],
        "client_id": account.get("client_id") or PUBLIC_CLIENT_ID,
    }
    if account.get("client_secret"):
        form["client_secret"] = account["client_secret"]
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(TOKEN_URL, data=form)
    if response.status_code >= 400:
        raise ValueError(f"Falha ao renovar OAuth: HTTP {response.status_code}: {response.text[:400]}")
    tokens = response.json()
    update_account(user_id, account_id, {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(tokens.get("expires_in", 3600)),
    })
    return get_account(user_id, account_id) or {}
