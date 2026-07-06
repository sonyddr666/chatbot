"""Aplicação FastAPI com suporte WebSocket para chat persistente."""

import json
import asyncio
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.api.routes import router
from src.config import settings
from src.core.auth import decode_access_token, rag_collection_for_user

app = FastAPI(
    title="Chatbot API",
    version="0.1.0",
    description="API do Chatbot Inteligente com RAG + WebSocket",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "Chatbot API",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/v1/health",
            "chat": "/api/v1/chat",
            "stream": "/api/v1/chat/stream",
            "ws": "/ws",
        },
        "frontend": "http://localhost:3000",
    }


@app.get("/docs")
async def swagger_redirect():
    return RedirectResponse(url="/docs")


# ─── WebSocket para chat persistente ───
@app.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """WebSocket persistente para chat em tempo real."""
    # Imports lazy para evitar travamento no startup
    from src.core.memory import get_session
    from src.core.chat import ChatEngine
    from src.core.classifier import classify_route
    from src.core.moderation import moderate_text
    from src.rag.retriever import retrieve_context
    from src.db.repository import ConversationRepo, SkillRepo, UserRepo
    from src.db.models import init_db
    from src.core.metrics import MESSAGES_TOTAL, ERRORS_TOTAL, LATENCY_HISTOGRAM

    async def _add_msg(session_id: str, role: str, content: str, user_id: int | None = None, **metadata):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: ConversationRepo.add_message(session_id, role, content, user_id=user_id, **metadata),
        )

    def _scoped_session_id(user_id: int, raw_session_id: str) -> str:
        if raw_session_id.startswith(f"u{user_id}:"):
            return raw_session_id
        return f"u{user_id}:{raw_session_id or 'default'}"

    def _user_prompt_context(user_id: int, rag_context: str | None = None) -> str | None:
        sections = []
        if rag_context:
            sections.append("Base de conhecimento pessoal do usuario:\n" + rag_context)
        skills_context = SkillRepo.enabled_context_for_user(user_id)
        if skills_context:
            sections.append(skills_context)
        return "\n\n".join(sections) if sections else None

    def _current_user():
        token = websocket.query_params.get("token", "")
        if token:
            payload = decode_access_token(token)
            if payload:
                user = UserRepo.get(int(payload.get("sub", 0)))
                if user:
                    return user
        return UserRepo.ensure_default_user()

    init_db()
    SkillRepo.ensure_defaults()
    await websocket.accept()
    user = _current_user()
    session_id = _scoped_session_id(user.id, "default")
    rag_collection = rag_collection_for_user(user.id)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "chat":
                session_id = _scoped_session_id(user.id, data.get("session_id", "default"))
                message = data.get("message", "").strip()
                use_rag = data.get("use_rag", True)
                use_thinking = data.get("use_thinking", True)

                if not message:
                    await websocket.send_json({"type": "error", "text": "Mensagem vazia"})
                    continue

                # Classifica rota
                route = classify_route(message)
                if route == "fast":
                    use_rag = False
                    use_thinking = False

                # Moderação
                if settings.enable_moderation:
                    blocked = moderate_text(message)
                    if blocked:
                        await websocket.send_json({"type": "token", "text": blocked})
                        await websocket.send_json({"type": "done"})
                        continue

                from src.core.provider_manager import get_active_model_metadata
                model_meta = get_active_model_metadata()

                # Start
                await websocket.send_json({"type": "start", "route": route, "session_id": session_id, **model_meta})
                MESSAGES_TOTAL.labels(role="user").inc()
                memory = get_session(session_id)

                # RAG em background
                rag_context = None
                rag_task = None
                if use_rag and settings.enable_rag:
                    async def fetch_rag():
                        nonlocal rag_context
                        loop = asyncio.get_event_loop()
                        rag_context = await loop.run_in_executor(None, retrieve_context, message, 4, None, rag_collection)
                    rag_task = asyncio.create_task(fetch_rag())
                    await websocket.send_json({"type": "status", "text": "Consultando base de conhecimento..."})

                if use_thinking:
                    await websocket.send_json({"type": "status", "text": "Pensando..."})

                save_task = asyncio.create_task(_add_msg(session_id, "user", message, user_id=user.id))

                if rag_task:
                    await rag_task
                prompt_context = _user_prompt_context(user.id, rag_context)
                memory.update_system_prompt(prompt_context)

                # Streaming LLM
                engine = ChatEngine(memory)
                full_response = ""
                has_reasoning = False
                t_start = time.time()

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
                    continue

                MESSAGES_TOTAL.labels(role="assistant").inc()
                await save_task
                ai_msg = await _add_msg(session_id, "assistant", full_response, user_id=user.id, **model_meta)

                total_time = time.time() - t_start
                LATENCY_HISTOGRAM.labels(route=route).observe(total_time)

                await websocket.send_json({
                    "type": "done",
                    "message_id": ai_msg.id,
                    "has_reasoning": has_reasoning,
                    **model_meta,
                    "metrics": {
                        "total_s": round(total_time, 2),
                        "route": route,
                        "ttft_s": round(total_time * 0.3, 2),  # estimativa
                    },
                })

            elif msg_type == "close":
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "text": f"Erro: {str(e)}"})
        except Exception:
            pass


app.include_router(router, prefix="/api/v1")
