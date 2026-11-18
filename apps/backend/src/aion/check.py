"""Container-local health checks; no credential or response body output."""

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HEARTBEAT = Path("/tmp/aion-worker-heartbeat")


def heartbeat_fresh() -> bool:
    try:
        age = time.time() - HEARTBEAT.stat().st_mtime
        return 0 <= age < 45
    except OSError:
        return False


def main() -> int:
    if sys.argv[1:] == ["worker"]:
        return 0 if heartbeat_fresh() else 1
    if sys.argv[1:] != ["api"]:
        return 2
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health/ready", timeout=5) as r:
            return 0 if r.status == 200 else 1
    except OSError, urllib.error.URLError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
