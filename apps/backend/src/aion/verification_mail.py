"""Sealed verification outbox with injectable sender and a synthetic local-only SMTP adapter."""

import json
import random
import smtplib
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from cryptography.fernet import InvalidToken
from sqlalchemy import Connection, Engine, case, delete, select, text, update
from sqlalchemy.orm import Session as DbSession

from aion.auth import AuthKeys
from aion.mail_content import verification_content, verification_html
from aion.models import (
    EmailChallenge,
    EmailEvent,
    EmailSuppression,
    ProfileMutation,
    RateLimitBucket,
    ReminderMail,
    Session,
    VerificationMail,
)


@dataclass(repr=False)
class Message:
    email: str
    code: str
    language: str
    provider_payload: dict[str, object] | None = None
    purpose: str = "login"


class Sender(Protocol):
    def send(self, message: Message, key: str) -> str | None: ...


class LocalCapture:
    def send(self, message: Message, key: str) -> None:
        if not message.email.endswith("@example.test"):
            raise ValueError("Local capture only accepts synthetic recipients")
        mail = EmailMessage()
        mail["From"], mail["To"] = "Aion <aion@example.test>", message.email
        mail["Message-ID"] = f"<{key}@aion.example.test>"
        payload = message.provider_payload
        if payload:
            subject, body = str(payload["subject"]), str(payload["text"])
            html = str(payload["html"])
        else:
            subject, body = verification_content(
                message.code, message.language, "support@example.test", message.purpose
            )
            html = verification_html(
                message.code, message.language, "support@example.test", message.purpose
            )
        mail["Subject"] = subject
        mail["Reply-To"] = "support@example.test"
        mail.set_content(body)
        mail.add_alternative(html, subtype="html")
        headers = payload.get("headers") if payload else None
        if isinstance(headers, dict):
            for header, value in headers.items():
                mail[header] = value
        with smtplib.SMTP("mailpit", 1025, timeout=3) as smtp:
            smtp.send_message(mail)


class RetryDeliveryError(Exception):
    def __init__(self, retry_after: float = 0, *, uncertain: bool = False) -> None:
        self.retry_after = retry_after
        self.uncertain = uncertain
        super().__init__("Mail provider temporarily unavailable")


class PermanentDeliveryError(Exception):
    def __init__(self) -> None:
        super().__init__("Mail provider rejected the request")


def terminal(job: VerificationMail, fallback: str) -> None:
    job.status = "uncertain" if job.acceptance_unknown else fallback
    job.encrypted_payload = None


def retry(job: VerificationMail, now: datetime, delay: float = 0) -> None:
    seconds = max(delay, min(60, 2**job.attempts) + random.uniform(0, 1))
    due = now + timedelta(seconds=seconds)
    if job.attempts >= 6 or due >= job.expires_at:
        terminal(job, "failed")
    else:
        job.next_attempt_at = due


@contextmanager
def delivery_lock(engine: Engine, keys: AuthKeys, email: str) -> Iterator[Connection]:
    # Session advisory locks conflict with auth's transaction advisory locks. Keep
    # the send barrier across commits so the pre-send uncertainty marker is durable.
    key = int.from_bytes(keys.digest("email_lock", email)[:8], signed=True)
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
        connection.commit()
        try:
            yield connection
        finally:
            try:
                connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                connection.commit()
            except Exception:
                connection.invalidate()
                raise


def deliver_pending(engine: Engine, keys: AuthKeys, sender: Sender, now: datetime) -> int:
    sent = 0
    started = time.monotonic()
    with DbSession(engine) as db:
        candidates = list(
            db.execute(
                select(VerificationMail.id, EmailChallenge.email)
                .join(EmailChallenge, EmailChallenge.id == VerificationMail.challenge_id)
                .where(
                    VerificationMail.status == "pending", VerificationMail.next_attempt_at <= now
                )
                .order_by(VerificationMail.next_attempt_at)
                .limit(5)
            )
        )
    for job_id, email in candidates:
        with delivery_lock(engine, keys, email) as connection:
            dispatch_now = now + timedelta(seconds=time.monotonic() - started)
            with DbSession(bind=connection) as db, db.begin():
                job = db.get(VerificationMail, job_id, with_for_update=True)
                if job is None or job.status != "pending" or job.next_attempt_at > dispatch_now:
                    continue
                challenge = db.get(EmailChallenge, job.challenge_id)
                if (
                    db.get(EmailSuppression, keys.digest("suppression", email)) is not None
                    or challenge is None
                    or challenge.consumed_at is not None
                    or challenge.invalidated_at is not None
                    or challenge.expires_at <= dispatch_now
                    or job.expires_at <= dispatch_now
                ):
                    terminal(job, "cancelled")
                    continue
                if challenge.purpose == "reverify":
                    bound = db.get(Session, challenge.session_id)
                    if (
                        bound is None
                        or bound.revoked_at is not None
                        or bound.expires_at <= dispatch_now
                        or bound.absolute_expires_at <= dispatch_now
                    ):
                        terminal(job, "cancelled")
                        continue
                try:
                    assert job.encrypted_payload is not None
                    payload = json.loads(keys.seal.decrypt(job.encrypted_payload))
                    if payload["email"] != challenge.email:
                        raise ValueError("Payload identity mismatch")
                    message = Message(
                        payload["email"],
                        payload["code"],
                        payload["language"],
                        payload.get("resend"),
                        payload.get("purpose", "login"),
                    )
                except InvalidToken, ValueError, KeyError:
                    terminal(job, "failed")
                    continue
                if job.attempts >= 6:
                    terminal(job, "failed")
                    continue
                prior_unknown = job.acceptance_unknown
                job.attempts += 1
                # Commit before network I/O: a crash may have sent mail. The same
                # sealed payload/key can be retried only within the code expiry.
                job.acceptance_unknown = True
            provider_id = None
            outcome = "accepted"
            delay = 0.0
            uncertain = False
            try:
                provider_id = sender.send(message, str(job_id))
            except ValueError, PermanentDeliveryError:
                outcome = "failed"
            except RetryDeliveryError as error:
                outcome, delay, uncertain = "retry", error.retry_after, error.uncertain
            except OSError, smtplib.SMTPException:
                outcome, uncertain = "retry", True
            with DbSession(bind=connection) as db, db.begin():
                job = db.get(VerificationMail, job_id, with_for_update=True)
                if job is None:
                    continue
                job.acceptance_unknown = prior_unknown or uncertain
                if outcome == "failed":
                    terminal(job, "failed")
                elif outcome == "retry":
                    retry(job, now + timedelta(seconds=time.monotonic() - started), delay)
                else:
                    job.provider_message_id = provider_id
                    job.acceptance_unknown = False
                    job.status = "accepted" if provider_id else "sent"
                    job.encrypted_payload = None
                    sent += 1
    return sent


def cleanup_expired(engine: Engine, now: datetime) -> None:
    with DbSession(engine) as db, db.begin():
        db.execute(
            update(VerificationMail)
            .where(
                VerificationMail.expires_at <= now, VerificationMail.encrypted_payload.is_not(None)
            )
            .values(
                status=case((VerificationMail.acceptance_unknown, "uncertain"), else_="cancelled"),
                encrypted_payload=None,
            )
        )
        db.execute(
            delete(EmailChallenge).where(EmailChallenge.expires_at <= now - timedelta(hours=24))
        )
        db.execute(
            delete(Session).where(
                (Session.expires_at <= now - timedelta(days=7))
                | (Session.revoked_at <= now - timedelta(days=7))
            )
        )
        db.execute(
            delete(ProfileMutation).where(ProfileMutation.created_at <= now - timedelta(days=30))
        )
        db.execute(
            update(ReminderMail)
            .where(ReminderMail.expires_at <= now, ReminderMail.encrypted_payload.is_not(None))
            .values(
                status=case((ReminderMail.acceptance_unknown, "uncertain"), else_="expired"),
                encrypted_payload=None,
                lease_until=None,
            )
        )
        db.execute(delete(ReminderMail).where(ReminderMail.expires_at <= now - timedelta(days=30)))
        db.execute(delete(EmailEvent).where(EmailEvent.received_at <= now - timedelta(days=30)))
        db.execute(delete(RateLimitBucket).where(RateLimitBucket.expires_at <= now))
