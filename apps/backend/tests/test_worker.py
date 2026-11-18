import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aion import worker


@pytest.mark.parametrize("age,exit_code", [(0, 0), (60, 1), (-60, 1), (None, 1)])
def test_heartbeat_probe_runs_without_backend_dependencies(
    tmp_path: Path, age: int | None, exit_code: int
) -> None:
    heartbeat = tmp_path / "heartbeat"
    if age is not None:
        heartbeat.touch()
        stamp = time.time() - age
        os.utime(heartbeat, (stamp, stamp))
    source = Path(__file__).resolve().parents[1] / "src"
    script = """
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from aion import check

check.HEARTBEAT = Path(sys.argv[2])
sys.argv = ["aion.check", "worker"]
raise SystemExit(check.main())
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            script,
            str(source),
            str(heartbeat),
        ],
        capture_output=True,
        timeout=3,
        check=False,
    )
    assert result.returncode == exit_code


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
