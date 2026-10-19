"""Local calendar schedules: first fold occurrence, first valid minute after a gap."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo


def resolve_wall(day: datetime, zone: ZoneInfo) -> datetime:
    # Civil-time gaps can span a whole date (e.g. Pacific/Apia in 2011).
    for minute in range(2 * 24 * 60 + 1):
        wall = day + timedelta(minutes=minute)
        instant = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == wall:
            return instant
    raise ValueError("No valid local send time")


def next_occurrence(
    now: datetime, timezone: str, send_time: str, frequency: str, weekday: int
) -> datetime:
    zone = ZoneInfo(timezone)
    local = now.astimezone(zone)
    hour, minute = map(int, send_time.split(":"))
    for offset in range(10):
        day = local.date() + timedelta(days=offset)
        if frequency == "weekly" and day.weekday() != weekday:
            continue
        instant = resolve_wall(datetime.combine(day, time(hour, minute)), zone)
        if instant > now:
            return instant
    raise ValueError("Schedule has no next occurrence")
