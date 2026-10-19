"""Atomic session revocation and cancellation of its pending confirmation mail."""

import uuid
from datetime import datetime

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session as DbSession

from aion.models import EmailChallenge, Session, VerificationMail


def revoke(db: DbSession, identifiers: list[uuid.UUID], now: datetime) -> None:
    # Callers hold the owner's per-email dispatch barrier before locking sessions.
    db.execute(
        update(Session)
        .where(Session.id.in_(identifiers), Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    challenges = select(EmailChallenge.id).where(
        EmailChallenge.session_id.in_(identifiers),
        EmailChallenge.purpose == "reverify",
    )
    db.execute(
        update(VerificationMail)
        .where(VerificationMail.challenge_id.in_(challenges), VerificationMail.status == "pending")
        .values(
            status=case((VerificationMail.acceptance_unknown, "uncertain"), else_="cancelled"),
            encrypted_payload=None,
        )
    )
    db.execute(
        update(EmailChallenge)
        .where(
            EmailChallenge.id.in_(challenges),
            EmailChallenge.consumed_at.is_(None),
            EmailChallenge.invalidated_at.is_(None),
        )
        .values(invalidated_at=now)
    )
