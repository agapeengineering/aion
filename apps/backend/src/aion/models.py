"""Initial identity schema. Tables alone do not implement authentication/authorization."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
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
