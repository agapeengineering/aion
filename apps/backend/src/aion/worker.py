"""Foundation worker: schema probe/heartbeat only. It cannot send or schedule mail."""

import argparse
import logging
import signal
import threading
import time
from pathlib import Path

from aion.config import Settings
from aion.database import is_ready, make_engine

HEARTBEAT = Path("/tmp/aion-worker-heartbeat")


def heartbeat_fresh() -> bool:
    try:
        age = time.time() - HEARTBEAT.stat().st_mtime
        return 0 <= age < 45
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    engine = make_engine(Settings())
    if args.once:
        try:
            return 0 if is_ready(engine) else 1
        finally:
            engine.dispose()
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    previous = None
    try:
        while not stop.is_set():
            available = is_ready(engine)
            if available:
                HEARTBEAT.touch()
            else:
                HEARTBEAT.unlink(missing_ok=True)
            if previous != available:
                logging.info("worker_ready" if available else "worker_unavailable")
                previous = available
            stop.wait(15)
    finally:
        HEARTBEAT.unlink(missing_ok=True)
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
