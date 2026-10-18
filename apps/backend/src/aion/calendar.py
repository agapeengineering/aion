"""Pure Gregorian calendar arithmetic; shared JSON fixtures are the contract."""

import calendar
import math
import re
from datetime import date
from typing import Any


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def anniversary(start: date, count: int, years: bool) -> date:
    index = (start.year - 1) * 12 + start.month - 1 + count * (12 if years else 1)
    year, month = index // 12 + 1, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def completed(start: date, end: date, years: bool) -> int:
    n = end.year - start.year if years else (end.year - start.year) * 12 + end.month - start.month
    return n - int(anniversary(start, n, years) > end)


def calculate(value: dict[str, Any]) -> dict[str, Any]:
    def error(field: str, code: str) -> dict[str, Any]:
        return {"error": {"field": field, "code": code}}

    clock: Any = value.get("clock")
    today = parse_date(clock.get("date")) if isinstance(clock, dict) else None
    if (
        today is None
        or not isinstance(clock.get("time"), str)
        or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]", clock["time"])
    ):
        return error("clock", "INVALID_CLOCK")
    birth = parse_date(value.get("birthDate"))
    if birth is None:
        return error("birthDate", "INVALID_BIRTH_DATE")
    if birth > today:
        return error("birthDate", "FUTURE_BIRTH_DATE")
    lifespan: Any = value.get("lifespanYears")
    if (
        type(lifespan) not in (int, float)
        or lifespan <= 0
        or lifespan > 9007199254740991
        or not math.isfinite(lifespan)
        or lifespan != int(lifespan)
    ):
        return error("lifespanYears", "INVALID_LIFESPAN")
    if birth.year + lifespan > 9999:
        return error("lifespanYears", "HORIZON_OUT_OF_RANGE")
    horizon = anniversary(birth, int(lifespan), True)
    b, t, h = birth.toordinal(), today.toordinal(), horizon.toordinal()
    hours, minutes, seconds = map(int, clock["time"].split(":"))
    q = hours * 3600 + minutes * 60 + seconds
    lived, remaining, span = t - b, max(0, h - t), h - b
    cells = (span + 6) // 7
    elapsed = lived // 7 if t < h else cells
    current = elapsed if t < h else None

    def totals(start: date, end: date, days: int, sec: int) -> dict[str, int]:
        return {
            "years": completed(start, end, True),
            "months": completed(start, end, False),
            "weeks": days // 7,
            "days": days,
            "hours": sec // 3600,
            "minutes": sec // 60,
            "seconds": sec,
        }

    return {
        "horizonDate": horizon.isoformat(),
        "horizonState": "before" if t < h else "reached" if t == h else "passed",
        "lived": totals(birth, today, lived, lived * 86400 + q),
        "remaining": totals(today, horizon, remaining, max(0, remaining * 86400 - q))
        if t < h
        else dict.fromkeys(["years", "months", "weeks", "days", "hours", "minutes", "seconds"], 0),
        "grid": {
            "totalCells": cells,
            "elapsedCells": elapsed,
            "currentIndex": current,
            "futureCells": cells - elapsed - int(current is not None),
            "currentStart": None
            if current is None
            else date.fromordinal(b + current * 7).isoformat(),
            "currentEndExclusive": None
            if current is None
            else date.fromordinal(min(b + (current + 1) * 7, h)).isoformat(),
            "finalCellDays": (span - 1) % 7 + 1,
        },
    }
