"""Persistent one-shot agent schedules that enqueue ordinary durable chat jobs."""

from __future__ import annotations

import asyncio

from src.core.chat_jobs import start_chat_job
from src.core.user_provider_manager import get_active_config_for_user, metadata_from_config
from src.db.repository import ChatJobRepo, ScheduledTaskRepo


POLL_SECONDS = 5
_runner: asyncio.Task | None = None


async def _execute(task: dict) -> None:
    task_id = str(task["id"])
    user_id = int(task["user_id"])
    try:
        config = await asyncio.to_thread(get_active_config_for_user, user_id)
        provider = metadata_from_config(config)
        session_id = str(task.get("session_id") or f"u{user_id}:scheduled:{task_id}")
        if not session_id.startswith(f"u{user_id}:"):
            session_id = f"u{user_id}:{session_id}"
        job = await asyncio.to_thread(
            ChatJobRepo.create_with_messages,
            user_id=user_id,
            session_id=session_id,
            message=str(task["prompt"]),
            provider=provider,
            response_mode="thinking",
            reasoning_effort="medium",
            use_rag=False,
            client_request_id=task_id[:64],
            attachment_ids=None,
        )
        await asyncio.to_thread(
            ScheduledTaskRepo.finish,
            task_id,
            "completed",
            job_id=str(job["id"]),
        )
        start_chat_job(str(job["id"]))
    except Exception as exc:
        await asyncio.to_thread(
            ScheduledTaskRepo.finish,
            task_id,
            "failed",
            error=str(exc),
        )


async def process_due_schedules() -> int:
    due = await asyncio.to_thread(ScheduledTaskRepo.claim_due)
    if due:
        await asyncio.gather(*(_execute(task) for task in due))
    return len(due)


async def _loop() -> None:
    while True:
        try:
            await process_due_schedules()
        except asyncio.CancelledError:
            raise
        except Exception:
            # One polling failure must not kill future schedules.
            pass
        await asyncio.sleep(POLL_SECONDS)


def start_schedule_runner() -> None:
    global _runner
    if _runner and not _runner.done():
        return
    _runner = asyncio.create_task(_loop(), name="scheduled-agent-runner")


async def stop_schedule_runner() -> None:
    global _runner
    if not _runner:
        return
    _runner.cancel()
    try:
        await _runner
    except asyncio.CancelledError:
        pass
    _runner = None
