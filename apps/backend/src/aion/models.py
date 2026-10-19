"""Initial identity schema. Tables alone do not implement authentication/authorization."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    MetaData,
    String,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email = lower(btrim(email)) AND length(email) > 3", name="canonical_email"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("octet_length(token_digest) = 32", name="token_digest_length"),
        CheckConstraint("octet_length(csrf_digest) = 32", name="csrf_digest_length"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint("absolute_expires_at >= expires_at", name="absolute_expiry"),
        Index("ix_sessions_expiry", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_digest: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    csrf_digest: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reverified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailChallenge(Base):
    __tablename__ = "email_challenges"
    __table_args__ = (
        CheckConstraint("purpose IN ('login', 'reverify')", name="purpose"),
        CheckConstraint("attempts BETWEEN 0 AND 5", name="attempt_range"),
        CheckConstraint("octet_length(code_digest) = 32", name="code_digest_length"),
        CheckConstraint("octet_length(browser_digest) = 32", name="browser_digest_length"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "email = lower(btrim(email)) AND length(email) > 3", name="canonical_email"
        ),
        CheckConstraint(
            "(purpose = 'login' AND user_id IS NULL) "
            "OR (purpose = 'reverify' AND user_id IS NOT NULL)",
            name="purpose_owner",
        ),
        CheckConstraint(
            "(purpose = 'login' AND session_id IS NULL) OR "
            "(purpose = 'reverify' AND session_id IS NOT NULL)",
            name="purpose_session",
        ),
        Index(
            "uq_email_challenges_active",
            "email",
            "purpose",
            unique=True,
            postgresql_where=text("consumed_at IS NULL AND invalidated_at IS NULL"),
        ),
        Index("ix_email_challenges_expiry", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254))
    purpose: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    code_digest: Mapped[bytes] = mapped_column(LargeBinary)
    browser_digest: Mapped[bytes] = mapped_column(LargeBinary)
    attempts: Mapped[int] = mapped_column(server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        CheckConstraint("octet_length(subject_digest) = 32", name="subject_digest_length"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        Index("ix_rate_limit_buckets_expiry", "expires_at"),
    )

    namespace: Mapped[str] = mapped_column(String(48), primary_key=True)
    subject_digest: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    attempts: Mapped[int] = mapped_column(server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationMail(Base):
    """Short-lived sealed verification payload, not a permanent email archive."""

    __tablename__ = "verification_mail"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'accepted', 'cancelled', 'failed', 'uncertain')",
            name="status",
        ),
        CheckConstraint("attempts BETWEEN 0 AND 6", name="attempt_range"),
        Index("ix_verification_mail_due", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_challenges.id", ondelete="CASCADE"), unique=True
    )
    encrypted_payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    attempts: Mapped[int] = mapped_column(server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    provider_message_id: Mapped[str | None] = mapped_column(String(64))
    acceptance_unknown: Mapped[bool] = mapped_column(server_default="false")


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint(
            "(birth_date IS NULL AND lifespan_years IS NULL AND language IS "
            "NULL AND unit IS NULL AND hide_remaining IS NULL) OR "
            "(birth_date IS NOT NULL AND lifespan_years IS NOT NULL AND "
            "language IS NOT NULL AND unit IS NOT NULL AND lifespan_years > "
            "0 AND extract(year FROM birth_date) >= 1 AND extract(year FROM "
            "birth_date) + lifespan_years <= 9999 "
            "AND language IN ('en', 'es') AND unit IN ('years', 'months', "
            "'weeks', 'days', 'hours', 'minutes', 'seconds') AND "
            "hide_remaining IS NOT NULL)",
            name="complete_profile",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(BigInteger)
    birth_date: Mapped[date | None] = mapped_column(Date)
    lifespan_years: Mapped[int | None]
    language: Mapped[str | None] = mapped_column(String(2))
    unit: Mapped[str | None] = mapped_column(String(16))
    hide_remaining: Mapped[bool | None]


class ProfileMutation(Base):
    __tablename__ = "profile_mutations"
    __table_args__ = (
        CheckConstraint("octet_length(payload_digest) = 32", name="digest_length"),
        CheckConstraint("result_revision > 0", name="revision_positive"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    payload_digest: Mapped[bytes] = mapped_column(LargeBinary)
    result_revision: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReminderPreference(Base):
    __tablename__ = "reminder_preferences"
    __table_args__ = (
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint("frequency IN ('daily', 'weekly')", name="frequency"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("language IN ('en', 'es')", name="language"),
        CheckConstraint(
            "NOT enabled OR (consent_at IS NOT NULL AND next_due_at IS NOT NULL)",
            name="enabled_consent",
        ),
        Index("ix_reminder_preferences_due", "enabled", "next_due_at"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(server_default="false")
    frequency: Mapped[str] = mapped_column(String(8))
    timezone: Mapped[str] = mapped_column(String(64))
    send_time: Mapped[str] = mapped_column(String(5))
    weekday: Mapped[int]
    language: Mapped[str] = mapped_column(String(2))
    include_phrase: Mapped[bool]
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notice_version: Mapped[str] = mapped_column(String(32))
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribe_digest: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    encrypted_token: Mapped[bytes] = mapped_column(LargeBinary)


class ReminderMail(Base):
    __tablename__ = "reminder_mail"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'accepted', 'cancelled', "
            "'failed', 'uncertain', 'expired')",
            name="status",
        ),
        CheckConstraint("attempts BETWEEN 0 AND 6", name="attempt_range"),
        Index("uq_reminder_mail_day", "user_id", "local_date", unique=True),
        Index("ix_reminder_mail_due", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    local_date: Mapped[date] = mapped_column(Date)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preference_revision: Mapped[int] = mapped_column(BigInteger)
    profile_revision: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    attempts: Mapped[int] = mapped_column(server_default="0")
    acceptance_unknown: Mapped[bool] = mapped_column(server_default="false")
    encrypted_payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    provider_message_id: Mapped[str | None] = mapped_column(String(64), index=True)
    delivery_status: Mapped[str | None] = mapped_column(String(24))
    phrase_id: Mapped[str | None] = mapped_column(String(80))
    content_version: Mapped[str | None] = mapped_column(String(64))


class EmailSuppression(Base):
    __tablename__ = "email_suppressions"
    email_digest: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    reason: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmailEvent(Base):
    __tablename__ = "email_events"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider_message_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DeletionLedger(Base):
    __tablename__ = "deletion_ledger"
    # No user foreign key: survives deletion and supports safe backup reconciliation.
    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email_digest: Mapped[bytes] = mapped_column(LargeBinary)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
