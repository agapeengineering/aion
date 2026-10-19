"""Schema heartbeat, expiry cleanup and opt-in local verification-mail capture."""

import argparse
import logging
import signal
import threading
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from aion.auth import AuthService, utc_now
from aion.config import Settings
from aion.database import is_ready, make_engine
from aion.reminder_delivery import deliver_reminders, schedule_due
from aion.resend_mail import ResendSender
from aion.verification_mail import LocalCapture, Sender, cleanup_expired, deliver_pending

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
    settings = Settings()
    engine = make_engine(settings)
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
        auth = AuthService(engine, settings) if settings.auth_enabled else None
        sender: Sender | None = None
        if settings.resend_enabled:
            sender = ResendSender(settings)
        elif settings.local_mail_capture:
            sender = LocalCapture()
        while not stop.is_set():
            available = is_ready(engine)
            if available:
                try:
                    cleanup_expired(engine, utc_now())
                    if auth is not None and sender is not None:
                        deliver_pending(engine, auth.keys, sender, utc_now())
                        schedule_due(auth, utc_now())
                        deliver_reminders(auth, sender, utc_now())
                except SQLAlchemyError:
                    available = False
            if available:
                HEARTBEAT.touch()
            else:
                HEARTBEAT.unlink(missing_ok=True)
            if previous != available:
                logging.info("worker_ready" if available else "worker_unavailable")
                previous = available
            stop.wait(2 if sender is not None else 15)
    finally:
        HEARTBEAT.unlink(missing_ok=True)
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
