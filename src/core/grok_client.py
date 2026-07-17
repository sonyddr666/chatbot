"""Streaming client for xAI Responses using per-user OAuth accounts."""

from __future__ import annotations

import json
from uuid import uuid4
from typing import AsyncGenerator

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.core.grok_oauth import GROK_CLIENT_VERSION, OAUTH_API_BASE, get_valid_account, list_accounts, refresh_access_token, update_account


def request_headers(account: dict, model: str, *, stream: bool = True) -> dict[str, str]:
    """Headers used by the official Grok Build subscription inference proxy."""
    return {
        "Authorization": f"Bearer {account['access_token']}",
        "Accept": "text/event-stream" if stream else "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"grok-shell/{GROK_CLIENT_VERSION} (windows; x86_64)",
        "x-grok-client-version": GROK_CLIENT_VERSION,
        "x-grok-client-identifier": "grok-shell",
        "x-grok-conv-id": str(uuid4()),
        "x-grok-req-id": str(uuid4()),
        "x-grok-model-override": model,
        "x-grok-session-id": str(uuid4()),
        "x-grok-agent-id": str(uuid4()),
        "x-grok-turn-idx": "0",
        "x-grok-user-id": str(account.get("subject") or ""),
    }


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text(item) for item in value)
    if isinstance(value, dict):
        return _text(value.get("text") or value.get("content") or "")
    return str(value or "")


def _payload(messages: list[BaseMessage], model: str, reasoning_effort: str | None) -> dict:
    instructions: list[str] = []
    input_messages: list[dict] = []
    for message in messages:
        content = _text(message.content)
        if isinstance(message, SystemMessage):
            instructions.append(content)
        elif isinstance(message, AIMessage):
            input_messages.append({"role": "assistant", "content": content})
        elif isinstance(message, HumanMessage):
            input_messages.append({"role": "user", "content": content})
        else:
            input_messages.append({"role": "user", "content": content})
    payload: dict = {
        "model": model,
        "input": input_messages,
        "stream": True,
    }
    if instructions:
        payload["instructions"] = "\n\n".join(instructions)
    if reasoning_effort in {"low", "medium", "high"}:
        payload["reasoning"] = {"effort": reasoning_effort}
        payload["include"] = ["reasoning.encrypted_content"]
    return payload


def _event_parts(event: dict) -> list[tuple[str, str]]:
    event_type = str(event.get("type") or "")
    delta = event.get("delta")
    text = delta if isinstance(delta, str) else ""
    if event_type in {"response.output_text.delta", "response.refusal.delta"} and text:
        return [("content", text)]
    if event_type in {"response.reasoning_summary_text.delta", "response.reasoning_text.delta"} and text:
        return [("reasoning", text)]
    if event_type in {"error", "response.failed"}:
        error = event.get("error") or (event.get("response") or {}).get("error") or event
        message = str(error.get("message") or error.get("code") or "Falha no stream do Grok") if isinstance(error, dict) else str(error)
        return [("error", message)]
    return []


async def chat_stream(
    user_id: int,
    messages: list[BaseMessage],
    *,
    model: str,
    reasoning_effort: str | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    candidates = [item for item in list_accounts(user_id, internal=True) if item.get("enabled")]
    if not candidates:
        yield ("error", "Conecte uma conta Grok antes de usar este provider.")
        return
    payload = _payload(messages, model, reasoning_effort)
    last_error = "Nenhuma conta Grok disponivel"
    timeout = httpx.Timeout(180.0, connect=15.0)

    for candidate in candidates:
        account_id = str(candidate["id"])
        try:
            account = await get_valid_account(user_id, account_id)
        except ValueError as exc:
            last_error = str(exc)
            continue
        for attempt in range(2):
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{OAUTH_API_BASE}/responses",
                    headers=request_headers(account, model),
                    json=payload,
                ) as response:
                    if response.status_code == 401 and attempt == 0:
                        await response.aread()
                        try:
                            account = await refresh_access_token(user_id, account_id, force=True)
                        except ValueError as exc:
                            last_error = str(exc)
                            break
                        continue
                    if response.status_code in {403, 429}:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        status = "blocked" if response.status_code == 403 else "rate_limited"
                        update_account(user_id, account_id, {"access_status": status, "last_error": detail})
                        last_error = (
                            "Conta conectada, mas o acesso aos modelos foi bloqueado pela xAI (403)."
                            if response.status_code == 403
                            else "Conta Grok temporariamente limitada (429)."
                        )
                        break
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:700]
                        last_error = f"Grok HTTP {response.status_code}: {detail}"
                        update_account(user_id, account_id, {"access_status": "error", "last_error": detail})
                        break

                    update_account(user_id, account_id, {"access_status": "confirmed", "last_error": ""})
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(event, dict):
                            for part in _event_parts(event):
                                yield part
                    return
        # 403/429/refresh failure: continue with the next enabled account.
    yield ("error", last_error)
