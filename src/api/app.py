"""Aplicação FastAPI com suporte WebSocket para chat persistente."""

import base64
import binascii
import json
import asyncio
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.api.routes import router
from src.api.workspace_routes import router as workspace_router
from src.api.tts_routes import router as tts_router
from src.config import settings
from src.core.auth_required import resolve_authorized_user
from src.db.models import init_db as initialize_database
from src.db.repository import ChatJobRepo, UserRepo
from src.core.chat_jobs import start_chat_job
from src.core.scheduled_tasks import start_schedule_runner, stop_schedule_runner

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


def _websocket_auth_token(websocket: WebSocket) -> tuple[str, str | None]:
    offered_protocols = [
        protocol.strip()
        for protocol in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if protocol.strip()
    ]
    accepted_protocol = "chatbot" if "chatbot" in offered_protocols else None
    for protocol in offered_protocols:
        if not protocol.startswith("auth."):
            continue
        encoded = protocol.removeprefix("auth.")
        try:
            padding = "=" * (-len(encoded) % 4)
            token = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
            if token:
                return token, accepted_protocol
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
    # Temporary compatibility for clients deployed before subprotocol auth.
    return websocket.query_params.get("token", ""), accepted_protocol


@app.on_event("startup")
async def initialize_persistent_runtime():
    initialize_database()
    UserRepo.ensure_initial_admin()
    await asyncio.to_thread(ChatJobRepo.interrupt_stale)
    queued_job_ids = await asyncio.to_thread(ChatJobRepo.list_queued_ids)
    for job_id in queued_job_ids:
        start_chat_job(job_id)
    from src.db.repository import ScheduledTaskRepo
    await asyncio.to_thread(ScheduledTaskRepo.recover_running)
    start_schedule_runner()


@app.on_event("shutdown")
async def stop_persistent_runtime():
    await stop_schedule_runner()


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
    from src.core.skill_runtime import run_enabled_skill_context, runtime_skill_activity, user_has_personal_rag
    from src.core.workspace_agent import create_workspace_plan, model_requests_workspace, workspace_plan_message, workspace_plan_status_context
    from src.core.preference_suggestions import create_suggestion_from_message
    from src.core.user_provider_manager import get_active_config_for_user, metadata_from_config
    from src.rag.personal import retrieve_user_context
    from src.db.repository import ConversationRepo, SkillRepo, UserPreferenceRepo
    from src.db.models import init_db
    from src.core.metrics import MESSAGES_TOTAL, ERRORS_TOTAL, LATENCY_HISTOGRAM
    from src.core.response_modes import normalize_reasoning_effort, normalize_response_mode, response_mode_status

    async def _add_msg(session_id: str, role: str, content: str, user_id: int | None = None, **metadata):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: ConversationRepo.add_message(session_id, role, content, user_id=user_id, **metadata),
        )

    def _observe_preference_suggestion(user_id: int, message: str) -> None:
        try:
            create_suggestion_from_message(user_id, message)
        except Exception:
            return

    def _scoped_session_id(user_id: int, raw_session_id: str) -> str:
        if raw_session_id.startswith(f"u{user_id}:"):
            return raw_session_id
        return f"u{user_id}:{raw_session_id or 'default'}"

    def _user_prompt_context(
        user_id: int,
        rag_context: str | None = None,
        runtime_context: str | None = None,
    ) -> str | None:
        sections = []
        if rag_context:
            sections.append("Base de conhecimento pessoal do usuario:\n" + rag_context)
        if runtime_context:
            sections.append(runtime_context)
        workspace_status = workspace_plan_status_context(user_id)
        if workspace_status:
            sections.append(workspace_status)
        preferences_context = UserPreferenceRepo.prompt_context_for_user(user_id)
        if preferences_context:
            sections.append(preferences_context)
        skills_context = SkillRepo.enabled_context_for_user(user_id)
        if skills_context:
            sections.append(skills_context)
        return "\n\n".join(sections) if sections else None

    token, accepted_protocol = _websocket_auth_token(websocket)

    def _current_user():
        return resolve_authorized_user(f"Bearer {token}") if token else None

    init_db()
    SkillRepo.ensure_defaults()
    user = _current_user()
    if not user:
        await websocket.accept(subprotocol=accepted_protocol)
        await websocket.send_json({"type": "error", "text": "Nao autenticado"})
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol=accepted_protocol)
    session_id = _scoped_session_id(user.id, "default")

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
                response_mode = normalize_response_mode(
                    data.get("response_mode"),
                    legacy_use_thinking=data.get("use_thinking"),
                    default=settings.codex_response_mode_default,
                )
                reasoning_effort = normalize_reasoning_effort(
                    data.get("reasoning_effort"),
                    mode=response_mode,
                )

                if not message:
                    await websocket.send_json({"type": "error", "text": "Mensagem vazia"})
                    continue

                # Classifica rota
                route = classify_route(message)
                if route == "fast":
                    use_rag = False

                # Moderação
                if settings.enable_moderation:
                    blocked = moderate_text(message)
                    if blocked:
                        await websocket.send_json({"type": "token", "text": blocked})
                        await websocket.send_json({"type": "done"})
                        continue

                provider_config = get_active_config_for_user(user.id)
                model_meta = metadata_from_config(provider_config)
                workspace_request = await model_requests_workspace(
                    user.id,
                    message,
                    provider_config,
                    session_id=session_id,
                )
                if not workspace_request and user_has_personal_rag(user.id, message, log_run=True):
                    use_rag = True

                # Start
                await websocket.send_json({
                    "type": "start",
                    "route": route,
                    "session_id": session_id,
                    "response_mode": response_mode,
                    "reasoning_effort": reasoning_effort,
                    **model_meta,
                })
                MESSAGES_TOTAL.labels(role="user").inc()
                memory = get_session(session_id)

                # RAG em background
                rag_context = None
                rag_task = None
                if not workspace_request and use_rag and settings.enable_rag:
                    async def fetch_rag():
                        nonlocal rag_context
                        loop = asyncio.get_event_loop()
                        rag_context = await loop.run_in_executor(None, retrieve_user_context, user.id, message, 4, None)
                    rag_task = asyncio.create_task(fetch_rag())
                    await websocket.send_json({"type": "status", "text": "Consultando base de conhecimento..."})

                await websocket.send_json({"type": "status", "text": "Preparando resposta..."})

                save_task = asyncio.create_task(_add_msg(session_id, "user", message, user_id=user.id))

                if workspace_request:
                    await websocket.send_json({"type": "status", "text": "Planejando alteracoes no Workspace..."})
                    try:
                        plan = await create_workspace_plan(
                            user.id,
                            message,
                            provider_config,
                            session_id=session_id,
                        )
                        full_response = workspace_plan_message(plan)
                        await websocket.send_json({"type": "token", "text": full_response})
                        await websocket.send_json({"type": "workspace_plan", "plan": plan})
                    except Exception as exc:
                        full_response = f"Nao consegui preparar o plano do Workspace: {exc}"
                        await websocket.send_json({"type": "token", "text": full_response})

                    memory.add_user_message(message)
                    memory.add_ai_message(full_response)
                    MESSAGES_TOTAL.labels(role="assistant").inc()
                    user_msg = await save_task
                    _observe_preference_suggestion(user.id, user_msg.content)
                    ai_msg = await _add_msg(session_id, "assistant", full_response, user_id=user.id, **model_meta)
                    await websocket.send_json({
                        "type": "done",
                        "message_id": ai_msg.id,
                        "has_reasoning": False,
                        **model_meta,
                    })
                    continue

                if rag_task:
                    await rag_task
                await websocket.send_json({"type": "status", "text": "Verificando skills e contexto..."})
                runtime_context = await run_enabled_skill_context(user.id, message, session_id=session_id)
                skill_activity = runtime_skill_activity(runtime_context)
                if skill_activity:
                    await websocket.send_json({"type": "skill_activity", "activity": skill_activity})
                prompt_context = _user_prompt_context(user.id, rag_context, runtime_context)
                memory.update_system_prompt(prompt_context)
                await websocket.send_json({
                    "type": "status",
                    "text": response_mode_status(response_mode),
                })

                # Streaming LLM
                engine = ChatEngine(
                    memory,
                    provider_config=provider_config,
                    response_mode=response_mode,
                    reasoning_effort=reasoning_effort,
                )
                full_response = ""
                full_reasoning = ""
                has_reasoning = False
                t_start = time.perf_counter()
                first_output_at = None

                try:
                    async for typ, text in engine.chat_stream(message):
                        if first_output_at is None:
                            first_output_at = time.perf_counter()
                        if typ == "reasoning":
                            has_reasoning = True
                            full_reasoning += text
                            await websocket.send_json({"type": "reasoning", "text": text})
                        else:
                            full_response += text
                            await websocket.send_json({"type": "token", "text": text})
                except Exception as e:
                    ERRORS_TOTAL.labels(type="llm").inc()
                    await websocket.send_json({"type": "error", "text": str(e)})
                    continue

                MESSAGES_TOTAL.labels(role="assistant").inc()
                user_msg = await save_task
                _observe_preference_suggestion(user.id, user_msg.content)
                ai_msg = await _add_msg(
                    session_id,
                    "assistant",
                    full_response,
                    user_id=user.id,
                    reasoning=full_reasoning,
                    skill_activities=[skill_activity] if skill_activity else [],
                    **model_meta,
                )

                total_time = time.perf_counter() - t_start
                LATENCY_HISTOGRAM.labels(route=route).observe(total_time)

                await websocket.send_json({
                    "type": "done",
                    "message_id": ai_msg.id,
                    "has_reasoning": has_reasoning,
                    "response_mode": response_mode,
                    "reasoning_effort": reasoning_effort,
                    **model_meta,
                    "metrics": {
                        "total_s": round(total_time, 2),
                        "route": route,
                        "ttft_s": round((first_output_at or time.perf_counter()) - t_start, 3),
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
app.include_router(workspace_router, prefix="/api/v1")
app.include_router(tts_router, prefix="/api/v1")
