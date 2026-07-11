"""Timezone-safe helpers for API timestamps."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_isoformat(value: datetime) -> str:
    """Serialize SQLite's naive UTC datetimes with an explicit UTC suffix."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
