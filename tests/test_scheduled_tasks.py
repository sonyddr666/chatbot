import asyncio
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.config import settings
from src.core.scheduled_tasks import process_due_schedules
from src.db.models import ScheduledAgentTask, get_session_db, init_db
from src.db.repository import ChatJobRepo, ScheduledTaskRepo, UserRepo


class ScheduledAgentTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_database_url = settings.database_url
        self.previous_user_data_dir = settings.user_data_dir
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path("C:/tmp") / f"chatbot-schedule-{uuid.uuid4().hex}.db"
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        settings.user_data_dir = str(Path(self.tmp.name) / "users")
        init_db()
        self.user = UserRepo.create_user(
            f"schedule-{uuid.uuid4().hex[:8]}@example.test",
            f"schedule_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Schedule",
        )

    def tearDown(self):
        settings.database_url = self.previous_database_url
        settings.user_data_dir = self.previous_user_data_dir

    def test_schedule_survives_storage_and_enqueues_durable_job(self):
        task = ScheduledTaskRepo.create(
            self.user.id,
            f"u{self.user.id}:scheduled-test",
            "Diga que o lembrete agendado foi executado.",
            datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        db = get_session_db()
        try:
            row = db.query(ScheduledAgentTask).filter(ScheduledAgentTask.id == task["id"]).one()
            row.run_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()

        config = {
            "provider_id": "test",
            "name": "Test",
            "model_id": "test-model",
            "model_name": "Test Model",
        }
        with (
            patch("src.core.scheduled_tasks.get_active_config_for_user", return_value=config),
            patch("src.core.scheduled_tasks.start_chat_job") as start,
        ):
            processed = asyncio.run(process_due_schedules())

        self.assertEqual(processed, 1)
        stored = ScheduledTaskRepo.list_for_user(self.user.id)[0]
        self.assertEqual(stored["status"], "completed")
        self.assertTrue(stored["job_id"])
        job = ChatJobRepo.get(stored["job_id"], self.user.id)
        self.assertEqual(job["status"], "queued")
        start.assert_called_once_with(stored["job_id"])

    def test_pending_schedule_can_be_cancelled_only_by_owner(self):
        task = ScheduledTaskRepo.create(
            self.user.id,
            f"u{self.user.id}:scheduled-test",
            "Lembrete futuro",
            datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        self.assertFalse(ScheduledTaskRepo.cancel(task["id"], self.user.id + 1))
        self.assertTrue(ScheduledTaskRepo.cancel(task["id"], self.user.id))
        self.assertEqual(ScheduledTaskRepo.list_for_user(self.user.id)[0]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
