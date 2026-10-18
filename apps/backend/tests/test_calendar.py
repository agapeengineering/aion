import json
from pathlib import Path

from aion.calendar import calculate


def test_unchanged_shared_calendar_snapshot_fixtures():
    path = Path(__file__).resolve().parents[3] / "tests/fixtures/calendar-clock/v1.json"
    fixtures = json.loads(path.read_text())
    for case in fixtures["cases"]:
        assert calculate(case["input"]) == case["expected"], case["id"]
