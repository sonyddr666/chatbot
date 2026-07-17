"""Gerenciador de Pool de Contas (Codex ChatGPT, OpenCode Zen, etc.).

Mantém múltiplas contas/API keys, faz refresh automático de tokens,
monitora cota (5h/semanal) e rotaciona entre contas quando uma esgota.
"""

import json
import os
import time
import base64
from datetime import datetime, timezone
from typing import Optional
import httpx

DATA_DIR = "./data"
POOL_FILE = os.path.join(DATA_DIR, "account_pool.json")

# ─── Estrutura ───────────────────────────────────────────────────────

DEFAULT_POOL = {
    "codex-chatgpt": {
        "accounts": [],
        "strategy": "round-robin",  # round-robin | lowest-usage | manual
    },
    "opencode-zen": {
        "accounts": [],
        "strategy": "round-robin",
    },
}

# ─── Helpers ─────────────────────────────────────────────────────────

def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if not os.path.exists(POOL_FILE):
        _save(DEFAULT_POOL)
        return dict(DEFAULT_POOL)
    try:
        with open(POOL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return dict(DEFAULT_POOL)


def _save(data: dict):
    _ensure_dir()
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─── JWT Helpers ────────────────────────────────────────────────────

def decode_jwt(token: str) -> Optional[dict]:
    """Decodifica um JWT (access_token) sem validar assinatura."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Padding para base64
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return None


def jwt_email(token: str) -> str:
    """Extrai email do JWT (igual ao exemplo Tkinter)."""
    claims = decode_jwt(token)
    if claims:
        profile = claims.get("https://api.openai.com/profile", {})
        if isinstance(profile, dict):
            email = profile.get("email")
            if email:
                return email
        return claims.get("email", "unknown@email")
    return "unknown@email"


def jwt_exp(token: str) -> int:
    """Extrai timestamp de expiração do JWT."""
    claims = decode_jwt(token)
    if claims:
        return claims.get("exp", 0)
    return 0


# ─── Quota / Uso ──────────────────────────────────────────────────

QUOTA_CACHE = {}  # account_id -> { "5h": {...}, "weekly": {...}, "cached_at": timestamp }


async def fetch_codex_quota(access_token: str, account_id: str) -> Optional[dict]:
    """Consulta wham/usage do Codex ChatGPT."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://chatgpt.com/backend-api/wham/usage",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0",
                    "ChatGPT-Account-Id": account_id,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return parse_quota(data)
            elif resp.status_code == 429:
                return {"error": "rate_limited", "status": 429}
            elif resp.status_code == 401:
                return {"error": "unauthorized", "status": 401}
            return {"error": f"HTTP {resp.status_code}", "status": resp.status_code}
    except Exception as e:
        return {"error": str(e), "status": 0}


def _normalize_percent(value) -> Optional[float]:
    """Normaliza valor de percentual.
    - Se for 0-1, assume que é fração (0.72 → 72%)
    - Se for 0-100, usa direto
    - Se for None, retorna None
    """
    if value is None:
        return None
    try:
        v = float(value)
        if 0 <= v <= 1:
            v *= 100
        return max(0.0, min(100.0, v))
    except (TypeError, ValueError):
        return None


def parse_quota(data: dict) -> dict:
    """Extrai percent_left e reset_time de qualquer estrutura do wham/usage.
    Normaliza escala 0-1 → 0-100.
    Procura por nome da janela (cap_5h, cap_weekly, etc.) em vez de assumir ordem.
    """
    result = {}
    raw_limits = []

    def _get_reset(obj):
        rst = (
            obj.get("reset_time_ms")
            or obj.get("reset_at")
            or obj.get("resets_at")
            or obj.get("resetAt")
        )
        if rst is None and obj.get("reset_after_seconds") is not None:
            return time.time() + float(obj["reset_after_seconds"])
        if rst is None and isinstance(obj.get("primary_window"), dict):
            rst = obj["primary_window"].get("reset_time_ms")
        return rst

    def _hunt(obj, path=""):
        if isinstance(obj, dict):
            # Tenta extrair percentual deste nó
            pct = None
            for k in ("percent_left", "remaining_percent", "used_percent"):
                if k in obj:
                    pct = _normalize_percent(obj[k])
                    if k == "used_percent" and pct is not None:
                        pct = 100.0 - pct
                    break

            if pct is not None:
                label = " ".join([
                    path,
                    str(obj.get("name", "")),
                    str(obj.get("type", "")),
                    str(obj.get("bucket", "")),
                    str(obj.get("window", "")),
                    str(obj.get("period", "")),
                    str(obj.get("label", "")),
                ]).lower()

                item = {
                    "path": path,
                    "label": label,
                    "pct": pct,
                    "reset": _get_reset(obj),
                    "used": obj.get("used"),
                    "max": obj.get("max"),
                }
                raw_limits.append(item)

                # Identifica por nome da janela
                if any(x in label for x in ["5h", "5_hour", "five_hour", "five hour", "primary", "local"]):
                    if "5h" not in result:
                        result["5h"] = {
                            "percent_left": pct,
                            "reset_time_ms": item["reset"],
                            "used": obj.get("used"),
                            "max": obj.get("max"),
                        }

                if any(x in label for x in ["weekly", "week", "secondary", "7d", "7_day"]):
                    if "weekly" not in result:
                        result["weekly"] = {
                            "percent_left": pct,
                            "reset_time_ms": item["reset"],
                            "used": obj.get("used"),
                            "max": obj.get("max"),
                        }

            for k, v in obj.items():
                _hunt(v, f"{path}.{k}" if path else str(k))

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _hunt(item, f"{path}[{i}]")

    _hunt(data)

    # Fallback: se não achou por nome, usa o primeiro como 5h e segundo como weekly
    if "5h" not in result and raw_limits:
        result["5h"] = {
            "percent_left": raw_limits[0]["pct"],
            "reset_time_ms": raw_limits[0]["reset"],
        }
    if "weekly" not in result and len(raw_limits) > 1:
        result["weekly"] = {
            "percent_left": raw_limits[1]["pct"],
            "reset_time_ms": raw_limits[1]["reset"],
        }

    return result if result else {"error": "unknown_format"}


# ─── Refresh Token ──────────────────────────────────────────────────

async def do_renew(refresh_token: str) -> Optional[dict]:
    """Renova access_token usando refresh_token (OAuth)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://auth.openai.com/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                tokens = resp.json()
                return {
                    "access_token": tokens.get("access_token"),
                    "refresh_token": tokens.get("refresh_token", refresh_token),
                    "id_token": tokens.get("id_token", ""),
                    "expires_in": tokens.get("expires_in", 3600),
                }
            return None
    except Exception:
        return None


# ─── API do Pool ──────────────────────────────────────────────────

def _repair_account_ids(pool: dict, provider_id: str) -> bool:
    """Corrige contas antigas que foram salvas com sub/google-oauth no lugar do chatgpt_account_id."""
    changed = False
    provider = pool.get(provider_id, {})
    for acc in provider.get("accounts", []):
        token = acc.get("access_token", "")
        claims = decode_jwt(token) or {}
        real_account_id = _extract_account_id(claims)
        old_account_id = acc.get("account_id", "")
        if real_account_id and real_account_id != old_account_id:
            acc["account_id"] = real_account_id
            changed = True
    return changed


def list_accounts(provider_id: str) -> list[dict]:
    """Lista contas de um provider no pool."""
    pool = _load()
    if provider_id == "codex-chatgpt" and _repair_account_ids(pool, provider_id):
        _save(pool)
    provider = pool.get(provider_id, {})
    return provider.get("accounts", [])


def export_accounts(provider_id: str) -> dict:
    """Exporta o pool com tokens; usar apenas em rota administrativa protegida."""
    provider = _load().get(provider_id, {})
    return {
        "strategy": provider.get("strategy", "round-robin"),
        "accounts": json.loads(json.dumps(provider.get("accounts", []))),
    }


def import_accounts(provider_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("accounts", []), list):
        raise ValueError("Pool de contas invalido")
    imported = 0
    for account in payload.get("accounts", []):
        if not isinstance(account, dict) or not account.get("access_token"):
            continue
        add_account(provider_id, account)
        imported += 1
    pool = _load()
    pool.setdefault(provider_id, {"accounts": [], "strategy": "round-robin"})["strategy"] = str(
        payload.get("strategy") or "round-robin"
    )
    _save(pool)
    return {"accounts": imported}


def get_account(provider_id: str, account_id: str) -> Optional[dict]:
    """Retorna uma conta específica pelo account_id."""
    for acc in list_accounts(provider_id):
        if acc.get("account_id") == account_id:
            return acc
    return None


def _extract_account_id(claims: dict) -> str:
    """Extrai account_id do JWT, igual ao exemplo Tkinter faz.
    Procura em:
    1. claims['https://api.openai.com/auth']['chatgpt_account_id']
    2. claims['account_id'] (top-level)
    3. claims['sub'] (fallback)
    """
    if not claims:
        return ""
    auth = claims.get("https://api.openai.com/auth", {})
    if isinstance(auth, dict):
        cid = auth.get("chatgpt_account_id") or auth.get("account_id", "")
        if cid:
            return cid
    return claims.get("account_id", "") or claims.get("sub", "")


def add_account(provider_id: str, account_data: dict) -> dict:
    """Adiciona uma conta ao pool."""
    pool = _load()
    if provider_id not in pool:
        pool[provider_id] = {"accounts": [], "strategy": "round-robin"}

    # Para Codex, o account_id correto vem do JWT em:
    # claims['https://api.openai.com/auth']['chatgpt_account_id'].
    # Preferimos ele ao account_id recebido no JSON, porque imports antigos podem trazer `sub`/google-oauth.
    claims = decode_jwt(account_data.get("access_token", "")) or {}
    jwt_account_id = _extract_account_id(claims)
    account_id = jwt_account_id or account_data.get("account_id", "")
    if not account_id:
        account_id = f"acc_{int(time.time())}"

    # Verifica se já existe
    for acc in pool[provider_id]["accounts"]:
        if acc.get("account_id") == account_id:
            # Atualiza tokens
            acc.update({
                "access_token": account_data.get("access_token", acc.get("access_token")),
                "refresh_token": account_data.get("refresh_token", acc.get("refresh_token")),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            _save(pool)
            return acc

    # Nova conta
    new_account = {
        "account_id": account_id,
        "label": account_data.get("label", jwt_email(account_data.get("access_token", ""))),
        "access_token": account_data.get("access_token", ""),
        "refresh_token": account_data.get("refresh_token", ""),
        "auth_type": account_data.get("auth_type", "oauth"),
        "enabled": True,
        "quota_cache": {},
        "last_quota_fetch": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    pool[provider_id]["accounts"].append(new_account)
    _save(pool)
    return new_account


def remove_account(provider_id: str, account_id: str) -> bool:
    """Remove uma conta do pool."""
    pool = _load()
    provider = pool.get(provider_id, {})
    before = len(provider.get("accounts", []))
    provider["accounts"] = [a for a in provider.get("accounts", []) if a.get("account_id") != account_id]
    if len(provider["accounts"]) < before:
        pool[provider_id] = provider
        _save(pool)
        return True
    return False


def update_account(provider_id: str, account_id: str, data: dict) -> Optional[dict]:
    """Atualiza dados de uma conta."""
    pool = _load()
    provider = pool.get(provider_id, {})
    for acc in provider.get("accounts", []):
        if acc.get("account_id") == account_id:
            acc.update(data)
            acc["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save(pool)
            return acc
    return None


async def refresh_account_token(provider_id: str, account_id: str) -> Optional[dict]:
    """Faz refresh do token de uma conta."""
    acc = get_account(provider_id, account_id)
    if not acc or not acc.get("refresh_token"):
        return None

    tokens = await do_renew(acc["refresh_token"])
    if tokens:
        update_account(provider_id, account_id, {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
        })
        return tokens
    return None


async def refresh_all_expired(provider_id: str) -> list[dict]:
    """Renova todas as contas com token expirado."""
    renewed = []
    for acc in list_accounts(provider_id):
        exp = jwt_exp(acc.get("access_token", ""))
        if time.time() > exp - 60:  # 1 minuto de margem
            tokens = await refresh_account_token(provider_id, acc["account_id"])
            if tokens:
                renewed.append({"account_id": acc["account_id"], "status": "renewed"})
            else:
                renewed.append({"account_id": acc["account_id"], "status": "failed"})
    return renewed


async def update_quota_all(provider_id: str) -> list[dict]:
    """Atualiza cota de todas as contas do pool."""
    results = []
    for acc in list_accounts(provider_id):
        if not acc.get("enabled", True):
            continue
        if provider_id == "codex-chatgpt":
            quota = await fetch_codex_quota(acc["access_token"], acc["account_id"])
        else:
            quota = {"error": "monitor_nao_implementado"}

        update_account(provider_id, acc["account_id"], {
            "quota_cache": quota,
            "last_quota_fetch": time.time(),
        })
        results.append({"account_id": acc["account_id"], "quota": quota})
    return results


async def get_best_account(provider_id: str) -> Optional[dict]:
    """Retorna a conta com mais cota disponível."""
    accounts = list_accounts(provider_id)
    if not accounts:
        return None

    # Primeiro tenta renovar expiradas
    for acc in accounts:
        exp = jwt_exp(acc.get("access_token", ""))
        if time.time() > exp - 60:
            await refresh_account_token(provider_id, acc["account_id"])

    # Filtra habilitadas
    enabled = [a for a in accounts if a.get("enabled", True)]

    if not enabled:
        return None

    # Estratégia lowest-usage: pega a que tem MAIS folga no gargalo
    # O gargalo real é o MENOR dos limites (5h ou weekly)
    best = None
    best_score = -1

    for acc in enabled:
        quota = acc.get("quota_cache", {})
        score = -1
        if isinstance(quota, dict):
            pct_5h = quota.get("5h", {}).get("percent_left")
            pct_wk = quota.get("weekly", {}).get("percent_left")
            if pct_5h is not None and pct_wk is not None:
                score = min(pct_5h, pct_wk)  # gargalo real
            elif pct_5h is not None:
                score = pct_5h
            elif pct_wk is not None:
                score = pct_wk

        if score > best_score:
            best_score = score
            best = acc
        elif best is None:
            best = acc

    if best:
        # Atualiza quota em background (não bloqueante)
        return {
            "account_id": best["account_id"],
            "label": best.get("label", ""),
            "access_token": best["access_token"],
            "refresh_token": best["refresh_token"],
            "quota": best.get("quota_cache", {}),
        }

    return enabled[0] if enabled else None


def get_pool_stats(provider_id: str) -> dict:
    """Estatísticas do pool para exibição no frontend."""
    accounts = list_accounts(provider_id)
    total = len(accounts)
    enabled = sum(1 for a in accounts if a.get("enabled", True))
    expired = sum(1 for a in accounts if time.time() > jwt_exp(a.get("access_token", "")) - 60)

    quotas_5h = []
    for acc in accounts:
        q = acc.get("quota_cache", {})
        if isinstance(q, dict) and "5h" in q:
            quotas_5h.append({
                "label": acc.get("label", "unknown"),
                "account_id": acc["account_id"],
                "percent_left": q["5h"].get("percent_left", 0),
                "enabled": acc.get("enabled", True),
            })

    return {
        "total_accounts": total,
        "enabled_accounts": enabled,
        "expired_tokens": expired,
        "quotas_5h": sorted(quotas_5h, key=lambda x: x.get("percent_left", 0), reverse=True),
        "strategy": "lowest-usage",
    }
