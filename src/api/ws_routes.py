"""WebSocket handler para chat persistente.
Conexão única por sessão, eliminando handshakes HTTP repetidos.
"""

import json
import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.memory import get_session
from src.core.chat import ChatEngine
from src.core.classifier import classify_route
from src.core.moderation import moderate_text
from src.core.multilang import detect_language
from src.rag.retriever import retrieve_context
from src.db.repository import ConversationRepo
from src.core.metrics import MESSAGES_TOTAL, ERRORS_TOTAL, LATENCY_HISTOGRAM
from src.config import settings

ws_router = APIRouter()

# Conexões ativas: session_id -> WebSocket
active_connections: dict[str, list[WebSocket]] = {}


async def async_add_message(session_id: str, role: str, content: str, **metadata):
    """DB em thread separada."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: ConversationRepo.add_message(session_id, role, content, **metadata),
    )


async def handle_chat_message(websocket: WebSocket, data: dict, session_id: str):
    """Processa uma mensagem de chat e envia chunks via WebSocket."""
    t0 = time.time()
    message = data.get("message", "").strip()
    use_rag = data.get("use_rag", True)
    use_thinking = data.get("use_thinking", True)

    if not message:
        await websocket.send_json({"type": "error", "text": "Mensagem vazia"})
        return

    # ── Classifica rota ──
    route = classify_route(message)
    if route == "fast":
        use_rag = False
        use_thinking = False

    t1 = time.time()

    # ── Moderação (rápida, paralela) ──
    if settings.enable_moderation:
        blocked = moderate_text(message)
        if blocked:
            await websocket.send_json({"type": "token", "text": blocked})
            await websocket.send_json({"type": "done"})
            return

    t2 = time.time()

    from src.core.provider_manager import get_active_model_metadata
    model_meta = get_active_model_metadata()

    # ── Sinaliza start ──
    await websocket.send_json({
        "type": "start",
        "route": route,
        "session_id": session_id,
        **model_meta,
    })

    # ── Prepara engine ──
    memory = get_session(session_id)
    MESSAGES_TOTAL.labels(role="user").inc()

    # ── RAG em background ──
    rag_context = None
    rag_task = None
    if use_rag and settings.enable_rag:
        async def fetch_rag():
            nonlocal rag_context
            loop = asyncio.get_event_loop()
            rag_context = await loop.run_in_executor(None, retrieve_context, message)

        rag_task = asyncio.create_task(fetch_rag())
        await websocket.send_json({"type": "status", "text": "Consultando base de conhecimento..."})

    # ── Thinking opcional ──
    if use_thinking:
        await websocket.send_json({"type": "status", "text": "Pensando..."})

    # ── Salva msg do user em background ──
    save_task = asyncio.create_task(async_add_message(session_id, "user", message))

    # ── Se tiver RAG, espera ──
    if rag_task:
        await rag_task
        if rag_context:
            memory.update_system_prompt(rag_context)

    # ── Inicia streaming do LLM ──
    t3 = time.time()
    engine = ChatEngine(memory)
    full_response = ""
    has_reasoning = False

    try:
        async for typ, text in engine.chat_stream(message):
            if typ == "reasoning":
                has_reasoning = True
                await websocket.send_json({"type": "reasoning", "text": text})
            else:
                full_response += text
                await websocket.send_json({"type": "token", "text": text})
    except Exception as e:
        ERRORS_TOTAL.labels(type="llm").inc()
        await websocket.send_json({"type": "error", "text": str(e)})
        return

    t4 = time.time()
    MESSAGES_TOTAL.labels(role="assistant").inc()

    # ── Salva resposta ──
    await save_task
    ai_msg = await async_add_message(session_id, "assistant", full_response, **model_meta)

    # ── Métricas ──
    ttft = t3 - t0
    total_time = t4 - t0
    LATENCY_HISTOGRAM.labels(route=route).observe(total_time)

    # ── Done ──
    await websocket.send_json({
        "type": "done",
        "message_id": ai_msg.id,
        "has_reasoning": has_reasoning,
        **model_meta,
        "metrics": {
            "ttft_s": round(ttft, 2),
            "total_s": round(total_time, 2),
            "route": route,
            "classify_ms": round((t1 - t0) * 1000),
            "moderation_ms": round((t2 - t1) * 1000),
        },
    })


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket persistente para chat em tempo real.

    Formato das mensagens (recebidas):
    ```json
    {"type": "chat", "message": "texto", "session_id": "abc", "use_rag": true, "use_thinking": true}
    {"type": "ping"}
    ```

    Formato das mensagens (enviadas):
    ```json
    {"type": "start", "route": "fast|full", "session_id": "abc"}
    {"type": "status", "text": "Consultando..."}
    {"type": "reasoning", "text": "..."}
    {"type": "token", "text": "..."}
    {"type": "done", "message_id": 1, "has_reasoning": false, "metrics": {...}}
    {"type": "error", "text": "..."}
    ```
    """
    await websocket.accept()

    # Registra conexão
    session_id = "default"

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "chat":
                session_id = data.get("session_id", session_id)
                # Registra nos active_connections
                if session_id not in active_connections:
                    active_connections[session_id] = []
                active_connections[session_id].append(websocket)

                await handle_chat_message(websocket, data, session_id)

            elif msg_type == "close":
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "text": f"Erro interno: {str(e)}"})
        except Exception:
            pass
    finally:
        # Remove das conexões ativas
        for sid, conns in active_connections.items():
            if websocket in conns:
                conns.remove(websocket)
                if not conns:
                    del active_connections[sid]
                break
