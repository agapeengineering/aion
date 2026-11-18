"""Exercise the API and inspect synthetic fixtures inside an isolated recovery project."""

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from svix.webhooks import Webhook

from aion.auth import CHALLENGE_COOKIE, SESSION_COOKIE, AuthKeys, token_digest
from aion.config import Settings
from aion.database import make_engine
from aion.models import (
    EmailChallenge,
    EmailSuppression,
    Profile,
    ReminderMail,
    ReminderPreference,
    Session,
    User,
    VerificationMail,
)

DELETED, RETAINED, ISOLATED = (
    uuid.UUID(f"78130000-0000-4000-8000-{number:012d}") for number in (1, 2, 3)
)
OLD_CHALLENGE = uuid.UUID("78130000-0000-4000-8002-000000000003")
OLD_SESSIONS = (
    "synthetic-recovery-deleted-session",
    "synthetic-recovery-retained-session",
)
DRILL_SESSIONS = ("synthetic-recovery-new-retained", "synthetic-recovery-new-isolated")
BROWSER = "synthetic-bound-browser"
CODE = "12345678"
ORIGIN = "https://127.0.0.1:28443"
BASE = "http://127.0.0.1:8000/api/v1"


def request(
    path: str,
    status: int,
    *,
    token: str | None = None,
    owner: uuid.UUID | None = None,
    method: str = "GET",
    payload: dict | None = None,
    csrf: str | None = None,
    extra_headers: dict | None = None,
) -> dict:
    headers = {"Origin": ORIGIN} | (extra_headers or {})
    if token is not None:
        headers["Cookie"] = f"{SESSION_COOKIE}={token}"
    if owner is not None:
        headers["X-Aion-Account"] = str(owner)
    if csrf:
        headers["X-CSRF-Token"] = csrf
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    if path == "/auth/verify":
        headers["Cookie"] = f"{CHALLENGE_COOKIE}={BROWSER}"
    try:
        response = urllib.request.urlopen(
            urllib.request.Request(BASE + path, data, headers, method=method),
            timeout=12,
        )
    except urllib.error.HTTPError as err:
        response = err
    with response:
        if response.status != status:
            raise AssertionError(f"{method} {path}: expected {status}, got {response.status}")
        assert response.headers["Cache-Control"] == "no-store"
        return json.loads(response.read()) if status != 204 else {}


def wait_ready() -> None:
    for _ in range(30):
        try:
            assert request("/health/ready", 200) == {"status": "ok"}
            return
        except urllib.error.URLError:
            time.sleep(0.5)
    raise SystemExit("The isolated recovery API did not start.")


def count(db: DbSession, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "delete", "restored", "rollback"))
    args = parser.parse_args()
    settings = Settings()
    assert settings.auth_enabled and settings.auth_origin == ORIGIN
    assert not any(
        (
            settings.local_mail_capture,
            settings.resend_enabled,
            settings.reminders_enabled,
        )
    )
    engine = make_engine(settings)
    keys = AuthKeys(settings)
    suppression_key = keys.digest("suppression", "retained-recovery@example.test")
    try:
        wait_ready()
        if args.phase == "prepare":
            with DbSession(engine) as db, db.begin():
                assert count(db, User) == 3 and count(db, Session) == 2
                session = db.scalar(select(Session).where(Session.user_id == DELETED))
                assert session is not None
                session.reverified_at = datetime.now(UTC)
                session.csrf_digest = token_digest(keys.csrf_token(OLD_SESSIONS[0]))
                challenge = db.get(EmailChallenge, OLD_CHALLENGE)
                assert challenge is not None
                challenge.code_digest = keys.digest("code", f"{OLD_CHALLENGE}:{CODE}")
                challenge.browser_digest = token_digest(BROWSER)
            assert request("/me", 200, token=OLD_SESSIONS[0])["id"] == str(DELETED)
            assert request("/me", 200, token=OLD_SESSIONS[1])["id"] == str(RETAINED)
            print("Synthetic accounts, known sessions and a browser-bound code are ready.")
            return

        if args.phase == "delete":
            request(
                "/account",
                204,
                token=OLD_SESSIONS[0],
                owner=DELETED,
                method="DELETE",
                payload={"confirmation": "delete"},
                csrf=keys.csrf_token(OLD_SESSIONS[0]),
            )
            assert request("/me", 401, token=OLD_SESSIONS[0])["error"]["code"] == "unauthenticated"
            webhook_file = settings.resend_webhook_secret_file
            if webhook_file is not None:
                now = datetime.now(UTC)
                event_id = str(uuid.uuid4())
                event = {
                    "type": "email.bounced",
                    "data": {
                        "email_id": str(uuid.uuid4()),
                        "from": settings.email_from,
                        "to": ["retained-recovery@example.test"],
                    },
                }
                request(
                    "/webhooks/resend",
                    204,
                    method="POST",
                    payload=event,
                    extra_headers={
                        "svix-id": event_id,
                        "svix-timestamp": str(int(now.timestamp())),
                        "svix-signature": Webhook(webhook_file.read_text().strip()).sign(
                            event_id, now, json.dumps(event)
                        ),
                    },
                )
            with DbSession(engine) as db, db.begin():
                assert db.get(User, DELETED) is None and db.get(Profile, DELETED) is None
                if webhook_file is None:
                    db.add(
                        EmailSuppression(
                            email_digest=suppression_key,
                            reason="bounced",
                            created_at=datetime.now(UTC),
                        )
                    )
                else:
                    assert db.get(EmailSuppression, suppression_key) is not None
            print("Aion deleted the synthetic account; recorded a synthetic bounce separately.")
            return

        with DbSession(engine) as db, db.begin():
            assert count(db, User) == count(db, Profile) == 2
            assert count(db, EmailChallenge) == count(db, VerificationMail) == 0
            assert db.get(User, DELETED) is None and db.get(Profile, DELETED) is None
            suppression = db.get(EmailSuppression, suppression_key)
            assert suppression is not None and suppression.reason == "bounced"
            job = db.scalar(select(ReminderMail))
            assert job is not None and job.status == "uncertain"
            assert job.lease_until is None and job.encrypted_payload is None
            preference = db.get(ReminderPreference, RETAINED)
            assert (
                preference is not None and not preference.enabled and preference.next_due_at is None
            )
            if args.phase == "restored":
                assert count(db, Session) == 0
                now = datetime.now(UTC)
                for user, token in zip((RETAINED, ISOLATED), DRILL_SESSIONS, strict=True):
                    db.add(
                        Session(
                            user_id=user,
                            token_digest=token_digest(token),
                            csrf_digest=token_digest(keys.csrf_token(token)),
                            last_seen_at=now,
                            expires_at=now + timedelta(hours=1),
                            absolute_expires_at=now + timedelta(days=1),
                        )
                    )

        for token in OLD_SESSIONS:
            assert request("/me", 401, token=token)["error"]["code"] == "unauthenticated"
        assert (
            request(
                "/auth/verify",
                400,
                method="POST",
                payload={"challenge_id": str(OLD_CHALLENGE), "code": CODE},
            )["error"]["code"]
            == "verification_failed"
        )
        for user, other, token, lifespan in (
            (RETAINED, ISOLATED, DRILL_SESSIONS[0], 89),
            (ISOLATED, RETAINED, DRILL_SESSIONS[1], 87),
        ):
            own = request("/profile", 200, owner=user, token=token)
            assert own["user_id"] == str(user) and own["revision"] == 1
            assert own["profile"]["lifespanYears"] == lifespan
            for wrong in (other, DELETED):
                assert request("/profile", 409, owner=wrong, token=token) == {
                    "error": {"code": "account_changed"}
                }
        print(
            f"{args.phase}: schema ready; deleted account absent; stale work cleared; "
            "suppression retained; old sessions and code denied; both profiles isolated."
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
