"""Reserve space in the UTC daily verification-mail budget before provider I/O."""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from aion.models import RateLimitBucket

NAMESPACE = "verification_mail_daily"
SUBJECT = hashlib.sha256(NAMESPACE.encode()).digest()


def window_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def next_window(now: datetime) -> datetime:
    return window_start(now) + timedelta(days=1)


def full(db: DbSession, now: datetime, limit: int) -> bool:
    row = db.get(RateLimitBucket, (NAMESPACE, SUBJECT, window_start(now)))
    return row is not None and row.attempts >= limit


def reserve(db: DbSession, now: datetime, limit: int) -> bool:
    statement = insert(RateLimitBucket).values(
        namespace=NAMESPACE,
        subject_digest=SUBJECT,
        window_start=window_start(now),
        expires_at=next_window(now),
        attempts=1,
    )
    return (
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["namespace", "subject_digest", "window_start"],
                set_={"attempts": RateLimitBucket.attempts + 1},
                where=RateLimitBucket.attempts < limit,
            ).returning(RateLimitBucket.attempts)
        ).scalar_one_or_none()
        is not None
    )
