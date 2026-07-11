import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.core.time_utils import utc_isoformat


ROOT = Path(__file__).resolve().parents[1]


class TimestampTimezoneTest(unittest.TestCase):
    def test_naive_sqlite_datetime_is_serialized_as_explicit_utc(self):
        self.assertEqual(utc_isoformat(datetime(2026, 7, 11, 1, 13)), "2026-07-11T01:13:00Z")

    def test_aware_local_datetime_is_converted_to_utc(self):
        sao_paulo = timezone(timedelta(hours=-3))
        local = datetime(2026, 7, 10, 22, 13, tzinfo=sao_paulo)
        self.assertEqual(utc_isoformat(local), "2026-07-11T01:13:00Z")

    def test_frontend_uses_legacy_safe_timestamp_parser(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")
        sidebar = (ROOT / "frontend/src/components/Sidebar.tsx").read_text(encoding="utf-8")

        self.assertIn("export function parseApiTimestamp", api)
        self.assertIn("timestamp: parseApiTimestamp(m.created_at)", store)
        self.assertIn("parseApiTimestamp(c.updated_at)", sidebar)


if __name__ == "__main__":
    unittest.main()
