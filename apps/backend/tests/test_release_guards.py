"""Production mail and write-ahead recovery boundaries with synthetic accounts."""

import base64
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from test_accounts import reverify
from test_auth import auth as auth
from test_auth import login
from test_reminders import sign_event

from aion.config import Settings
from aion.mail_budget import full, next_window, reserve
from aion.models import DeletionLedger, EmailEvent, EmailSuppression, VerificationMail
from aion.recovery_journal import JournalUnavailable
from aion.verification_mail import RetryDeliveryError, deliver_pending


def test_public_mail_requires_explicit_safe_settings(tmp_path: Path) -> None:
    secret = tmp_path / "webhook"
    secret.write_text("whsec_" + base64.b64encode(b"s" * 32).decode())
    epoch_file = tmp_path / "journal-epoch"
    epoch_file.write_text("a" * 32)
    values = dict(
        database_url=SecretStr("postgresql+psycopg://aion_app:synthetic@localhost:1/aion"),
        auth_enabled=True,
        resend_enabled=True,
        resend_public_accounts=True,
        resend_daily_limit=17,
        recovery_journal_socket=tmp_path / "journal.sock",
        recovery_journal_epoch_file=epoch_file,
        resend_webhook_secret_file=secret,
        email_reply_to="support@example.test",
    )
    public = Settings(**values)
    assert public.resend_recipient_allowed("new-recipient@example.test")
    assert public.recovery_journal_epoch == "a" * 32
    preview = Settings(
        **(
            values
            | {"resend_public_accounts": False, "resend_allowed_recipients": ["a@example.test"]}
        )
    )
    assert preview.resend_recipient_allowed("a@example.test")
    assert not preview.resend_recipient_allowed("new-recipient@example.test")
    for invalid in (
        {"resend_daily_limit": None},
        {"recovery_journal_socket": None, "recovery_journal_epoch_file": None},
        {"recovery_journal_epoch_file": tmp_path / "missing-epoch"},
        {"resend_webhook_secret_file": None},
        {"resend_allowed_recipients": ["a@example.test"]},
        {"auth_origin": "https://127.0.0.1:28443"},
        {"reminders_enabled": True},
        {"resend_enabled": False},
        {"email_from": "Other <other@example.test>"},
    ):
        with pytest.raises(ValidationError):
            Settings(**(values | invalid))


@pytest.mark.integration
def test_delete_fails_closed_and_waits_for_independent_ack(auth):
    client, service, now, _ = auth
    account = login(auth).json()
    headers, _ = reverify(auth)
    owner = uuid.UUID(account["user"]["id"])

    class Journal:
        available = False
        drop_reply = False
        recorded = set()

        def deletion(self, key, digest, timestamp):
            # A separate connection can still see the account and no committed deletion.
            with DbSession(service.engine) as reader:
                assert reader.get(DeletionLedger, key) is None
            if not self.available:
                raise JournalUnavailable
            self.recorded.add((key, digest, timestamp))
            if self.drop_reply:
                raise JournalUnavailable

    journal = Journal()
    service.journal = journal
    failed = client.request(
        "DELETE", "/api/v1/account", headers=headers, json={"confirmation": "delete"}
    )
    assert failed.status_code == 503 and failed.json() == {
        "error": {"code": "recovery_unavailable"}
    }
    assert client.get("/api/v1/me").status_code == 200
    journal.available = True
    journal.drop_reply = True
    assert (
        client.request(
            "DELETE", "/api/v1/account", headers=headers, json={"confirmation": "delete"}
        ).status_code
        == 503
    )
    assert client.get("/api/v1/me").status_code == 200
    assert len(journal.recorded) == 1
    journal.drop_reply = False
    assert (
        client.request(
            "DELETE", "/api/v1/account", headers=headers, json={"confirmation": "delete"}
        ).status_code
        == 204
    )
    assert journal.recorded == {
        (owner, service.keys.digest("suppression", "person@example.test"), now[0])
    }
    assert client.get("/api/v1/me").status_code == 401
    with DbSession(service.engine) as reader:
        assert reader.get(DeletionLedger, owner) is not None


@pytest.mark.integration
def test_suppression_requires_verified_recipient_and_journal_ack(auth, tmp_path):
    client, service, now, _ = auth

    class Journal:
        available = False
        recorded = []

        def suppression(self, digests, reason, timestamp):
            with DbSession(service.engine) as reader:
                assert reader.get(EmailSuppression, digests[0]) is None
            if not self.available:
                raise JournalUnavailable
            self.recorded.append((digests, reason, timestamp))

    journal = Journal()
    service.journal = journal
    callback = "/api/v1/webhooks/resend"
    body, headers = sign_event(auth, tmp_path, "empty", "email.bounced", str(uuid.uuid4()), to=[])
    assert client.post(callback, headers=headers, content=body).status_code == 400
    body, headers = sign_event(auth, tmp_path, "journaled", "email.bounced", str(uuid.uuid4()))
    assert client.post(callback, headers=headers, content=body).status_code == 503
    with DbSession(service.engine) as reader:
        assert reader.get(EmailEvent, "journaled") is None
    journal.available = True
    for _ in range(2):
        assert client.post(callback, headers=headers, content=body).status_code == 204
    assert journal.recorded == [
        ([service.keys.digest("suppression", "person@example.test")], "bounced", now[0])
    ]
    with DbSession(service.engine) as reader:
        assert reader.scalar(select(func.count()).select_from(EmailSuppression)) == 1


@pytest.mark.integration
def test_dispatch_does_not_refund_an_uncertain_provider_attempt(auth):
    client, service, now, _ = auth
    service.settings.resend_enabled = True
    service.settings.resend_public_accounts = True
    service.settings.resend_daily_limit = 1
    endpoint = "/api/v1/auth/challenges"
    for address in ("one@example.test", "two@example.test"):
        assert client.post(endpoint, json={"email": address}).status_code == 202

    class Sender:
        attempts = 0

        def send(self, message, key):
            self.attempts += 1
            with DbSession(service.engine) as reader:
                assert full(reader, now[0], 1)
            raise RetryDeliveryError(uncertain=True)

    sender = Sender()
    assert deliver_pending(service.engine, service.keys, sender, now[0], daily_limit=1) == 0
    until_retry = now[0] + timedelta(seconds=30)
    assert deliver_pending(service.engine, service.keys, sender, until_retry, daily_limit=1) == 0
    assert sender.attempts == 1
    with DbSession(service.engine) as reader:
        states = sorted(job.status for job in reader.scalars(select(VerificationMail)))
        assert states == ["cancelled", "uncertain"]
    blocked = client.post(endpoint, json={"email": "three@example.test"})
    assert blocked.status_code == 429 and 0 < int(blocked.headers["Retry-After"]) <= 86400
    now[0] = next_window(now[0])
    assert client.post(endpoint, json={"email": "three@example.test"}).status_code == 202


@pytest.mark.integration
def test_shared_daily_limit_serializes_concurrent_reservations(auth):
    _, service, now, _ = auth

    def attempt(_: int) -> bool:
        with DbSession(service.engine) as db, db.begin():
            return reserve(db, now[0], 3)

    with ThreadPoolExecutor(max_workers=5) as pool:
        assert sum(pool.map(attempt, range(10))) == 3
    with DbSession(service.engine) as db:
        assert full(db, now[0], 3)
