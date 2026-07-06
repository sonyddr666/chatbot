"""Cliente para API do Codex ChatGPT.
Implementa Device Code OAuth flow e chamadas à API do ChatGPT.
"""

import json
import time
import asyncio
import base64
from typing import Optional, AsyncGenerator
import httpx

from src.core.account_pool import do_renew, decode_jwt

# ─── Constantes ──────────────────────────────────────────────────────

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"
AUTH_BASE = "https://auth.openai.com"
API_BASE = "https://chatgpt.com/backend-api"

# ─── Device Code Flow ───────────────────────────────────────────────

class DeviceCodeSession:
    """Gerencia uma sessão de Device Code OAuth."""

    def __init__(self):
        self.user_code: str = ""
        self.device_auth_id: str = ""
        self.verification_uri: str = ""
        self.interval: int = 5
        self.status: str = "pending"  # pending | authorized | expired | error
        self.error_message: str = ""
        self.tokens: Optional[dict] = None

    async def request_code(self) -> dict:
        """Passo 1: Pede um código de dispositivo."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{AUTH_BASE}/api/accounts/deviceauth/usercode",
                    json={"client_id": CLIENT_ID},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.user_code = data.get("user_code", "")
                    self.device_auth_id = data.get("device_auth_id", "")
                    self.verification_uri = data.get("verification_uri", "https://auth.openai.com/codex/device")
                    self.interval = data.get("interval", 5)
                    return {
                        "user_code": self.user_code,
                        "verification_uri": self.verification_uri,
                        "device_auth_id": self.device_auth_id,
                        "interval": self.interval,
                    }
                else:
                    self.status = "error"
                    self.error_message = f"HTTP {resp.status_code}: {resp.text}"
                    return {"error": self.error_message}
        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
            return {"error": str(e)}

    async def poll_for_token(self, max_attempts: int = 120) -> Optional[dict]:
        """Passo 3: Polling até o usuário aprovar (máx 120 tentativas = ~10 min)."""
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        f"{AUTH_BASE}/api/accounts/deviceauth/token",
                        json={
                            "client_id": CLIENT_ID,
                            "device_auth_id": self.device_auth_id,
                            "user_code": self.user_code,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        auth_code = data.get("authorization_code", "")
                        code_verifier = data.get("code_verifier", "")
                        # Passo 4: Troca pelo token final
                        self.tokens = await self._exchange_code(auth_code, code_verifier)
                        if self.tokens:
                            self.status = "authorized"
                            return self.tokens
                        else:
                            self.status = "error"
                            self.error_message = "Falha ao trocar código por tokens"
                            return None
                    elif resp.status_code == 429:
                        # Muitas requisições, espera mais
                        await asyncio.sleep(self.interval * 2)
                        continue
                    # Outros status: ainda não aprovado, continua
            except Exception as e:
                if attempt > 10:  # Só loga depois de várias tentativas
                    self.error_message = str(e)

            await asyncio.sleep(self.interval)

        self.status = "expired"
        self.error_message = "Tempo limite excedido (10 min)"
        return None

    async def _exchange_code(self, auth_code: str, code_verifier: str) -> Optional[dict]:
        """Passo 4: Troca authorization_code por tokens finais."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{AUTH_BASE}/oauth/token",
                    data={
                        "grant_type": "authorization_code",
                        "client_id": CLIENT_ID,
                        "code": auth_code,
                        "code_verifier": code_verifier,
                        "redirect_uri": DEVICE_REDIRECT_URI,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code == 200:
                    tokens = resp.json()
                    return {
                        "access_token": tokens.get("access_token", ""),
                        "refresh_token": tokens.get("refresh_token", ""),
                        "id_token": tokens.get("id_token", ""),
                        "expires_in": tokens.get("expires_in", 3600),
                    }
                return None
        except Exception:
            return None


# ─── Sessões ativas de Device Code ────────────────────────────────
_device_sessions: dict[str, "DeviceCodeSession"] = {}


async def device_code_start() -> dict:
    """Passo 1: Inicia fluxo Device Code.
    Retorna { user_code, verification_uri, request_id }.
    O frontend deve chamar device_code_poll() periodicamente.
    """
    session = DeviceCodeSession()
    code_data = await session.request_code()

    if "error" in code_data:
        return {"status": "error", "message": code_data["error"]}

    request_id = session.device_auth_id or f"dev_{int(time.time())}"
    _device_sessions[request_id] = session

    return {
        "status": "pending",
        "user_code": code_data["user_code"],
        "verification_uri": code_data["verification_uri"],
        "request_id": request_id,
        "interval": session.interval,
    }


async def device_code_poll(request_id: str) -> dict:
    """
    Passo 2: Polling - faz UMA tentativa e retorna resultado.
    Segue o mesmo padrão do exemplo Tkinter.
    """
    from src.core.account_pool import add_account, fetch_codex_quota, update_account

    session = _device_sessions.get(request_id)
    if not session:
        return {"status": "not_found", "message": "Sessão expirou ou não encontrada"}

    if session.status == "saved":
        return {"status": "saved", "message": "Conta salva no pool!"}
    if session.status == "error":
        return {"status": "error", "message": session.error_message}
    if session.status == "expired":
        return {"status": "expired", "message": "Tempo limite excedido"}

    # Faz UMA tentativa de poll (igual ao exemplo Tkinter)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{AUTH_BASE}/api/accounts/deviceauth/token",
                json={
                    "client_id": CLIENT_ID,
                    "device_auth_id": session.device_auth_id,
                    "user_code": session.user_code,
                },
            )
            if resp.status_code == 200:
                # Usuário aprovou! Faz exchange e salva
                data = resp.json()
                auth_code = data.get("authorization_code", "")
                code_verifier = data.get("code_verifier", "")

                # Exchange auth_code → tokens (igual ao exemplo)
                async with httpx.AsyncClient(timeout=15) as client2:
                    exch_resp = await client2.post(
                        f"{AUTH_BASE}/oauth/token",
                        data={
                            "grant_type": "authorization_code",
                            "client_id": CLIENT_ID,
                            "code": auth_code,
                            "code_verifier": code_verifier,
                            "redirect_uri": DEVICE_REDIRECT_URI,
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    if exch_resp.status_code == 200:
                        tokens = exch_resp.json()
                        access_token = tokens.get("access_token", "")
                        refresh_token = tokens.get("refresh_token", "")

                        # 1. Salva a conta no pool
                        account = add_account("codex-chatgpt", {
                            "access_token": access_token,
                            "refresh_token": refresh_token,
                            "label": f"Device Code {session.user_code}",
                        })
                        account_id = account.get("account_id", "")

                        # 2. Já puxa a cota inicial (pra não mostrar 0%)
                        if access_token and account_id:
                            try:
                                quota = await fetch_codex_quota(access_token, account_id)
                                if quota and "error" not in quota:
                                    update_account("codex-chatgpt", account_id, {
                                        "quota_cache": quota,
                                        "last_quota_fetch": time.time(),
                                    })
                            except Exception:
                                pass  # Se falhou, tenta na próxima

                        session.status = "saved"
                        _device_sessions.pop(request_id, None)
                        return {
                            "status": "saved",
                            "message": "Conta autenticada e salva no pool!",
                        }
                    else:
                        err_body = await exch_resp.aread()
                        err_text = err_body.decode('utf-8', errors='replace')[:500]
                        session.status = "error"
                        session.error_message = f"Falha no exchange: HTTP {exch_resp.status_code} — {err_text}"
                        return {"status": "error", "message": session.error_message}
            elif resp.status_code == 429:
                return {"status": "pending", "message": "Rate limited, aguarde..."}

            # Qualquer outro código: ainda não aprovado
            return {"status": "pending", "message": "Aguardando autenticação..."}

    except Exception as e:
        session.error_message = str(e)
        return {"status": "error", "message": str(e)}


def get_device_session_status(request_id: str) -> dict:
    """Retorna o status atual de uma sessão (sem fazer poll)."""
    session = _device_sessions.get(request_id)
    if not session:
        return {"status": "not_found", "message": "Sessão não encontrada ou expirou"}
    return {
        "status": session.status,
        "user_code": session.user_code,
        "message": {
            "saved": "Conta autenticada e salva no pool!",
            "error": session.error_message,
            "expired": "Tempo limite excedido (10 min)",
        }.get(session.status, "Aguardando autenticação..."),
    }


# ─── API do ChatGPT ──────────────────────────────────────────────────

CODEX_RESPONSES_URL = f"{API_BASE}/codex/responses"
DEFAULT_INSTRUCTIONS = (
    "You are a helpful assistant. Respond in the same language as the user. "
    "Be concise and accurate."
)


def _collect_chunks(obj, key, result: list):
    """Caça recursivamente todas as ocorrências de uma chave num dict aninhado."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                result.append(v)
            _collect_chunks(v, key, result)
    elif isinstance(obj, list):
        for item in obj:
            _collect_chunks(item, key, result)


def _extract_response_output_text(response: dict) -> str:
    """Extrai texto do campo output do response.completed."""
    output = response.get("output", [])
    texts = []
    for item in output:
        if isinstance(item, dict):
            content = item.get("content", [])
            for part in content:
                if isinstance(part, dict):
                    texts.append(part.get("text", "") or "")
    return "".join(texts)


async def codex_responses_stream(
    access_token: str,
    account_id: str,
    model: str,
    input_messages: list[dict],
    instructions: str = "",
    reasoning_effort: str = "medium",
) -> AsyncGenerator[str, None]:
    """
    Chama a API Responses do Codex (/codex/responses) com stream:true.
    Segue exatamente o formato do server(2).py que você mandou.
    
    Yields strings com o delta de texto em tempo real.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": "Mozilla/5.0 (compatible; CodexChat/1.0)",
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id

    body = {
        "model": model,
        "input": input_messages,
        "store": False,
        "stream": True,
        "reasoning": {"effort": reasoning_effort},
        "instructions": instructions or DEFAULT_INSTRUCTIONS,
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                CODEX_RESPONSES_URL,
                json=body,
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    yield f"ERRO: HTTP {resp.status_code} — {error_text.decode('utf-8', errors='replace')[:300]}"
                    return

                buffer = ""
                async for raw_bytes in resp.aiter_bytes():
                    buffer += raw_bytes.decode("utf-8", errors="replace")
                    # Processa linhas completas
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if not chunk or chunk == "[DONE]":
                            continue
                        try:
                            event = json.loads(chunk)
                        except json.JSONDecodeError:
                            continue

                        # Extrai delta de texto
                        if event.get("type") == "response.output_text.delta":
                            delta = event.get("delta", "")
                            if delta:
                                yield delta

                        # Fallback: caça qualquer campo "delta" no evento
                        else:
                            deltas = []
                            _collect_chunks(event, "delta", deltas)
                            if deltas:
                                yield "".join(deltas)

    except Exception as e:
        yield f"ERRO: {str(e)}"


async def chat_completion_stream(
    access_token: str,
    account_id: str,
    model: str,
    messages: list[dict],
    max_tokens: int = 4096,
    instructions: str = "",
    reasoning_effort: str = "medium",
) -> AsyncGenerator[str, None]:
    """
    Chama a API do Codex com streaming.
    Primeiro tenta a nova API Responses (/codex/responses).
    Se falhar, cai no endpoint antigo (/conversation) como fallback.
    """
    # Primeiro tenta a nova API Responses
    if model and messages:
        generator = codex_responses_stream(
            access_token=access_token,
            account_id=account_id,
            model=model,
            input_messages=messages,
            instructions=instructions,
            reasoning_effort=reasoning_effort,
        )
        first = True
        async for chunk in generator:
            if first and chunk.startswith("ERRO: HTTP"):
                # Falhou a nova API, cai no fallback
                break
            first = False
            yield chunk
        else:
            # Nova API funcionou até o fim
            return

    # ─── Fallback: endpoint antigo /conversation ───
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ChatGPT-Account-Id": account_id,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": "Mozilla/5.0 (compatible; CodexChat/1.0)",
    }

    body = {
        "action": "next",
        "messages": messages,
        "model": model,
        "parent_message_id": None,
        "conversation_id": None,
        "history_and_training_disabled": False,
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{API_BASE}/conversation",
                json=body,
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    yield f"ERRO: HTTP {resp.status_code}"
                    return

                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = data.get("message", {}).get("content", {}).get("parts", [""])[0]
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        yield f"ERRO: {str(e)}"


async def check_account_valid(access_token: str, account_id: str) -> dict:
    """Verifica se uma conta ainda é válida."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{API_BASE}/accounts/check",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "ChatGPT-Account-Id": account_id,
                },
            )
            return {
                "status": resp.status_code,
                "valid": resp.status_code == 200,
            }
    except Exception as e:
        return {"status": 0, "valid": False, "error": str(e)}


# ─── Extract tokens de auth.json ───────────────────────────────────

def extract_tokens_from_json(data: dict) -> Optional[dict]:
    """Extrai tokens de qualquer formato de auth.json.
    
    Suporta:
    - Formato credential_pool (auth(infinity).json)
    - Formato oficial Codex (auth.json com 'tokens')
    - Formato simples { access, refresh }
    """
    # Formato 1: credential_pool
    if "credential_pool" in data:
        pool = data["credential_pool"]
        for provider_key in ("openai-codex", "chatgpt"):
            entries = pool.get(provider_key, [])
            if entries:
                return extract_tokens_from_entry(entries[0])

    # Formato 2: tokens aninhados
    if "tokens" in data:
        t = data["tokens"]
        return {
            "access_token": t.get("access_token", t.get("access", "")),
            "refresh_token": t.get("refresh_token", t.get("refresh", "")),
            "id_token": t.get("id_token", ""),
            "account_id": t.get("account_id", ""),
        }

    # Formato 3: direto
    if "access_token" in data or "access" in data:
        return {
            "access_token": data.get("access_token", data.get("access", "")),
            "refresh_token": data.get("refresh_token", data.get("refresh", "")),
            "id_token": data.get("id_token", ""),
            "account_id": data.get("account_id", ""),
        }

    return None


def extract_tokens_from_entry(entry: dict) -> Optional[dict]:
    """Extrai tokens de uma entrada do credential_pool."""
    if not isinstance(entry, dict):
        return None
    return {
        "access_token": entry.get("access_token", entry.get("access", "")),
        "refresh_token": entry.get("refresh_token", entry.get("refresh", "")),
        "id_token": entry.get("id_token", ""),
        "account_id": entry.get("account_id", ""),
    }
