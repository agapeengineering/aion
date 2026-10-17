import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migrate
from sqlalchemy import Engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from aion.database import is_ready
from aion.models import Base, EmailChallenge, RateLimitBucket, Session, User

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


def user() -> User:
    return User(email=f"person-{uuid.uuid4().hex}@example.test", verified_at=NOW)


def challenge(email: str) -> EmailChallenge:
    return EmailChallenge(
        email=email,
        purpose="login",
        code_digest=b"c" * 32,
        browser_digest=b"b" * 32,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def test_initial_upgrade_matches_models_and_can_be_reapplied(database: Engine) -> None:
    assert is_ready(database)
    assert set(inspect(database).get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    migrate(database)
    with database.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert (
            connection.execute(
                text(
                    "SELECT rolsuper OR rolcreatedb OR rolcreaterole "
                    "FROM pg_roles WHERE rolname=current_user"
                )
            ).scalar_one()
            is False
        )


def test_down_and_up_only_in_random_disposable_schema(database: Engine) -> None:
    with database.connect() as connection:
        assert (
            connection.execute(text("SELECT current_schema()"))
            .scalar_one()
            .startswith("aion_test_")
        )
    migrate(database, "base", down=True)
    assert not is_ready(database)
    assert set(inspect(database).get_table_names()) == {"alembic_version"}
    migrate(database)
    assert is_ready(database)


def test_normalized_identity_is_unique_and_noncanonical_email_rejected(database: Engine) -> None:
    with DbSession(database) as db:
        person = user()
        db.add(person)
        db.commit()
        same_email = person.email
    for email in (same_email, "UPPER@example.test", " person@example.test "):
        with pytest.raises(IntegrityError), DbSession(database) as db, db.begin():
            db.add(User(email=email, verified_at=NOW))


def test_session_secrets_foreign_key_and_delete_cascade(database: Engine) -> None:
    with DbSession(database) as db, db.begin():
        person = user()
        db.add(person)
        db.flush()
        person_id = person.id
        db.add(
            Session(
                user_id=person_id,
                token_digest=b"t" * 32,
                csrf_digest=b"x" * 32,
                created_at=NOW,
                last_seen_at=NOW,
                expires_at=NOW + timedelta(days=7),
                absolute_expires_at=NOW + timedelta(days=30),
            )
        )
    with DbSession(database) as db, db.begin():
        db.delete(db.get(User, person_id))
    with DbSession(database) as db:
        assert db.scalar(select(func.count()).select_from(Session)) == 0
    with pytest.raises(IntegrityError), DbSession(database) as db, db.begin():
        db.add(
            Session(
                user_id=person_id,
                token_digest=b"t" * 32,
                csrf_digest=b"x" * 32,
                created_at=NOW,
                last_seen_at=NOW,
                expires_at=NOW + timedelta(days=7),
                absolute_expires_at=NOW + timedelta(days=30),
            )
        )


def test_challenge_resend_requires_invalidating_previous_and_attempt_limit(
    database: Engine,
) -> None:
    email = "person@example.test"
    with DbSession(database) as db, db.begin():
        db.add(challenge(email))
    with pytest.raises(IntegrityError), DbSession(database) as db, db.begin():
        db.add(challenge(email))
    with DbSession(database) as db, db.begin():
        current = db.scalars(select(EmailChallenge)).one()
        current.invalidated_at = NOW
        db.flush()
        db.add(challenge(email))
    with pytest.raises(IntegrityError), DbSession(database) as db, db.begin():
        current = db.scalars(
            select(EmailChallenge).where(EmailChallenge.invalidated_at.is_(None))
        ).one()
        current.attempts = 6


def test_short_digests_are_rejected_and_rate_buckets_survive_new_connection(
    database: Engine,
) -> None:
    with pytest.raises(IntegrityError), DbSession(database) as db, db.begin():
        bad = challenge("person@example.test")
        bad.code_digest = b"short"
        db.add(bad)
    with DbSession(database) as db, db.begin():
        db.add(
            RateLimitBucket(
                namespace="email_send",
                subject_digest=b"e" * 32,
                window_start=NOW,
                attempts=3,
                expires_at=NOW + timedelta(hours=1),
            )
        )
    database.dispose()
    with DbSession(database) as db:
        assert db.scalars(select(RateLimitBucket)).one().attempts == 3
