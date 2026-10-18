"""Sealed verification outbox with injectable sender and a synthetic local-only SMTP adapter."""

import json
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from cryptography.fernet import InvalidToken
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session as DbSession

from aion.auth import AuthKeys, lock_email
from aion.models import EmailChallenge, RateLimitBucket, Session, VerificationMail


@dataclass(repr=False)
class Message:
    email: str
    code: str
    language: str


class Sender(Protocol):
    def send(self, message: Message, key: str) -> None: ...


class LocalCapture:
    def send(self, message: Message, key: str) -> None:
        if not message.email.endswith("@example.test"):
            raise ValueError("Local capture only accepts synthetic recipients")
        mail = EmailMessage()
        mail["From"], mail["To"] = "Aion <aion@example.test>", message.email
        mail["Message-ID"] = f"<{key}@aion.example.test>"
        mail["Subject"] = (
            "Tu código de Aion" if message.language == "es" else "Your Aion sign-in code"
        )
        mail.set_content(
            (
                f"Tu código es {message.code}. Caduca en diez minutos. "
                "Si no lo solicitaste, ignora este correo."
            )
            if message.language == "es"
            else (
                f"Your code is {message.code}. It expires in ten minutes. "
                "If you did not request this, ignore this email."
            )
        )
        with smtplib.SMTP("mailpit", 1025, timeout=3) as smtp:
            smtp.send_message(mail)


def deliver_pending(engine: Engine, keys: AuthKeys, sender: Sender, now: datetime) -> int:
    sent = 0
    with DbSession(engine) as db:
        ids = list(
            db.scalars(
                select(VerificationMail.id)
                .where(
                    VerificationMail.status == "pending", VerificationMail.next_attempt_at <= now
                )
                .order_by(VerificationMail.next_attempt_at)
                .limit(20)
            )
        )
    for job_id in ids:
        with DbSession(engine) as db, db.begin():
            candidate = db.get(VerificationMail, job_id)
            if candidate is None:
                continue
            challenge = db.get(EmailChallenge, candidate.challenge_id)
            if challenge is None:
                continue
            lock_email(db, challenge.email, keys)
            db.refresh(challenge)
            job = db.scalars(
                select(VerificationMail)
                .where(VerificationMail.id == job_id)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).first()
            if job is None or job.status != "pending" or job.next_attempt_at > now:
                continue
            if (
                challenge.consumed_at is not None
                or challenge.invalidated_at is not None
                or challenge.expires_at <= now
                or job.expires_at <= now
            ):
                job.status, job.encrypted_payload = "cancelled", None
                continue
            try:
                assert job.encrypted_payload is not None
                payload = json.loads(keys.seal.decrypt(job.encrypted_payload))
                if payload["email"] != challenge.email:
                    raise ValueError("Payload identity mismatch")
                job.attempts += 1
                sender.send(
                    Message(payload["email"], payload["code"], payload["language"]), str(job.id)
                )
            except InvalidToken, ValueError, KeyError:
                job.status, job.encrypted_payload = "failed", None
            except OSError, smtplib.SMTPException:
                if job.attempts >= 6:
                    job.status, job.encrypted_payload = "failed", None
                else:
                    job.next_attempt_at = now + timedelta(seconds=min(60, 2**job.attempts))
            else:
                job.status, job.encrypted_payload = "sent", None
                sent += 1
    return sent


def cleanup_expired(engine: Engine, now: datetime) -> None:
    with DbSession(engine) as db, db.begin():
        db.execute(
            update(VerificationMail)
            .where(
                VerificationMail.expires_at <= now, VerificationMail.encrypted_payload.is_not(None)
            )
            .values(status="cancelled", encrypted_payload=None)
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
        db.execute(delete(RateLimitBucket).where(RateLimitBucket.expires_at <= now))
