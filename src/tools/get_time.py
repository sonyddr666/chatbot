"""Deterministic current date/time tool using the user's configured timezone."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.db.repository import UserRepo


DEFAULT_TIMEZONE = "America/Sao_Paulo"
WEEKDAYS_PT = (
    "segunda-feira",
    "terca-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sabado",
    "domingo",
)


def _timezone(value: str):
    name = (value or DEFAULT_TIMEZONE).strip()
    try:
        return name, ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # Windows installations without the optional tzdata wheel still need
        # the product default to work. Production installs tzdata explicitly.
        if name == DEFAULT_TIMEZONE:
            return name, timezone(timedelta(hours=-3), name="-03:00")
        if name.upper() in {"UTC", "ETC/UTC"}:
            return "UTC", timezone.utc
        raise ValueError(f"Fuso horario IANA invalido: {name}")


def current_time(
    user_id: int,
    requested_timezone: str = "",
    *,
    now_utc: datetime | None = None,
) -> dict:
    profile = UserRepo.get_profile(user_id)
    profile_timezone = str(getattr(profile, "timezone", "") or "")
    timezone_name, zone = _timezone(requested_timezone or profile_timezone or DEFAULT_TIMEZONE)
    reference = now_utc or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    local = reference.astimezone(zone)
    offset = local.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return {
        "timezone": timezone_name,
        "iso": local.isoformat(),
        "date": local.strftime("%Y-%m-%d"),
        "time": local.strftime("%H:%M:%S"),
        "weekday": WEEKDAYS_PT[local.weekday()],
        "utc_offset": f"{sign}{hours:02d}:{minutes:02d}",
    }
