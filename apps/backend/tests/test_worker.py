import sys
from pathlib import Path

import pytest

from aion import worker


@pytest.mark.parametrize("available,exit_code", [(True, 0), (False, 1)])
def test_one_shot_probe_does_not_remove_running_workers_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available: bool, exit_code: int
) -> None:
    heartbeat = tmp_path / "existing-worker-heartbeat"
    heartbeat.write_text("owned by the long-running worker")
    before = heartbeat.stat().st_mtime_ns
    monkeypatch.setattr(worker, "HEARTBEAT", heartbeat)
    monkeypatch.setattr(worker, "is_ready", lambda _: available)
    monkeypatch.setattr(sys, "argv", ["aion.worker", "--once"])
    monkeypatch.delenv("AION_DATABASE_URL_FILE", raising=False)
    monkeypatch.setenv(
        "AION_DATABASE_URL", "postgresql+psycopg://synthetic:not-real@127.0.0.1:1/aion"
    )
    assert worker.main() == exit_code
    assert heartbeat.read_text() == "owned by the long-running worker"
    assert heartbeat.stat().st_mtime_ns == before
