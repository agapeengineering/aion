"""PostgreSQL schedules and leased, sealed delivery; no backlog or silent payload mutation."""

import json
import random
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from aion.auth import AuthService
from aion.models import (
    EmailEvent,
    EmailSuppression,
    Profile,
    ReminderMail,
    ReminderPreference,
    User,
)
from aion.phrases import weekly_collection
from aion.reminder_content import render_reminder
from aion.schedules import next_occurrence
from aion.verification_mail import (
    Message,
    PermanentDeliveryError,
    RetryDeliveryError,
    Sender,
    delivery_lock,
)


def terminal(job: ReminderMail, status: str) -> None:
    job.status = "uncertain" if job.acceptance_unknown else status
    job.encrypted_payload = None
    job.lease_until = None


def schedule_due(auth: AuthService, now: datetime) -> int:
    if not auth.settings.reminders_enabled:
        return 0
    count = 0
    collection = weekly_collection()  # Invalid content fails closed; never use research drafts.
    with DbSession(auth.engine) as db, db.begin():
        prefs = list(
            db.scalars(
                select(ReminderPreference)
                .where(ReminderPreference.enabled.is_(True), ReminderPreference.next_due_at <= now)
                .order_by(ReminderPreference.next_due_at)
                .with_for_update(skip_locked=True)
                .limit(20)
            )
        )
        for pref in prefs:
            due = pref.next_due_at
            assert due
            day = due.astimezone(ZoneInfo(pref.timezone)).date()
            # Move straight to the future: missed weeks never become a delivery backlog.
            pref.next_due_at = next_occurrence(
                now, pref.timezone, pref.send_time, pref.frequency, pref.weekday
            )
            if now >= due + timedelta(hours=1):
                continue
            exists = db.scalar(
                select(ReminderMail.id).where(
                    ReminderMail.user_id == pref.user_id, ReminderMail.local_date == day
                )
            )
            if exists:
                continue
            user = db.get(User, pref.user_id)
            profile = db.get(Profile, pref.user_id)
            if not user or not profile or not profile.birth_date:
                continue
            if db.get(EmailSuppression, auth.keys.digest("suppression", user.email)):
                continue
            # An unfilled editorial week is skipped, never silently replaced or backfilled.
            # Advancing the schedule also prevents unavailable content starving other accounts.
            if pref.include_phrase and collection.for_date(day) is None:
                db.add(
                    ReminderMail(
                        user_id=user.id,
                        local_date=day,
                        due_at=due,
                        expires_at=due + timedelta(hours=1),
                        next_attempt_at=now,
                        preference_revision=pref.revision,
                        profile_revision=profile.revision,
                        status="cancelled",
                        delivery_status="content_unavailable",
                    )
                )
                continue
            try:
                token = auth.keys.seal.decrypt(pref.encrypted_token).decode()
            except InvalidToken, UnicodeDecodeError:
                # A lost/rotated key must never yield mail without a usable unsubscribe route.
                pref.enabled = False
                pref.next_due_at = None
                pref.revision += 1
                continue
            payload, phrase_id = render_reminder(
                profile,
                pref,
                due,
                collection,
                origin=auth.origin,
                email=user.email,
                sender=auth.settings.email_from,
                reply_to=auth.settings.email_reply_to or "support@example.test",
                token=token,
            )
            job = ReminderMail(
                id=uuid.uuid4(),
                user_id=user.id,
                local_date=day,
                due_at=due,
                expires_at=due + timedelta(hours=1),
                next_attempt_at=now,
                preference_revision=pref.revision,
                profile_revision=profile.revision,
                phrase_id=phrase_id,
                content_version=collection.collectionVersion if phrase_id else None,
                encrypted_payload=auth.keys.seal.encrypt(json.dumps(payload).encode()),
            )
            db.add(job)
            count += 1
    return count


def deliver_reminders(auth: AuthService, sender: Sender, now: datetime) -> int:
    if not auth.settings.reminders_enabled:
        return 0
    # A committed lease bounds crash recovery; SKIP LOCKED supports another worker.
    with DbSession(auth.engine) as db, db.begin():
        jobs = list(
            db.scalars(
                select(ReminderMail)
                .where(
                    ReminderMail.status == "pending",
                    ReminderMail.next_attempt_at <= now,
                    (ReminderMail.lease_until.is_(None) | (ReminderMail.lease_until <= now)),
                )
                .order_by(ReminderMail.next_attempt_at)
                .with_for_update(skip_locked=True)
                .limit(5)
            )
        )
        claimed = []
        for candidate in jobs:
            user = db.get(User, candidate.user_id)
            if user:
                candidate.lease_until = now + timedelta(seconds=30)
                claimed.append((candidate.id, user.email))
    sent = 0
    started = time.monotonic()
    for identifier, email in claimed:
        with delivery_lock(auth.engine, auth.keys, email) as connection:
            with DbSession(bind=connection) as db, db.begin():
                job = db.get(ReminderMail, identifier, with_for_update=True)
                if not job or job.status != "pending":
                    continue
                user = db.get(User, job.user_id, with_for_update=True)
                pref = db.get(ReminderPreference, job.user_id)
                profile = db.get(Profile, job.user_id)
                dispatch_now = now + timedelta(seconds=time.monotonic() - started)
                if job.next_attempt_at > dispatch_now:
                    continue
                if dispatch_now >= job.expires_at:
                    terminal(job, "expired")
                    continue
                if (
                    not user
                    or not pref
                    or not pref.enabled
                    or not profile
                    or not profile.birth_date
                    or (
                        pref.revision != job.preference_revision
                        or profile.revision != job.profile_revision
                        or db.get(EmailSuppression, auth.keys.digest("suppression", email))
                        is not None
                    )
                ):
                    terminal(job, "cancelled")
                    continue
                if job.phrase_id:
                    collection = weekly_collection()
                    phrase = collection.for_date(job.local_date)
                    if (
                        not phrase
                        or phrase.id != job.phrase_id
                        or collection.collectionVersion != job.content_version
                    ):
                        terminal(job, "cancelled")
                        continue
                if job.attempts >= 6 or not job.encrypted_payload:
                    terminal(job, "failed")
                    continue
                try:
                    payload = json.loads(auth.keys.seal.decrypt(job.encrypted_payload))
                    if payload.get("to") != [email]:
                        raise ValueError
                except InvalidToken, ValueError, KeyError, TypeError:
                    terminal(job, "failed")
                    continue
                language = pref.language
                prior_unknown = job.acceptance_unknown
                job.acceptance_unknown = True
                job.attempts += 1
            # Advisory lock spans this provider call and commit. Settings/reset/unsubscribe
            # share the barrier, so no stale private dispatch starts after their commit.
            outcome, provider_id, uncertain, delay = "accepted", None, False, 0.0
            try:
                provider_id = sender.send(
                    Message(email, "", language, payload), "reminder/" + str(identifier)
                )
            except PermanentDeliveryError, ValueError:
                outcome = "failed"
            except RetryDeliveryError as error:
                outcome, uncertain, delay = "retry", error.uncertain, error.retry_after
            except OSError:
                outcome, uncertain = "retry", True
            with DbSession(bind=connection) as db, db.begin():
                job = db.get(ReminderMail, identifier, with_for_update=True)
                assert job
                job.acceptance_unknown = prior_unknown or uncertain
                job.lease_until = None
                if outcome == "retry":
                    due = now + timedelta(
                        seconds=time.monotonic()
                        - started
                        + max(delay, min(60, 2**job.attempts) + random.uniform(0, 1))
                    )
                    if job.attempts >= 6 or due >= job.expires_at:
                        terminal(job, "failed")
                    else:
                        job.next_attempt_at = due
                elif outcome == "failed":
                    terminal(job, "failed")
                else:
                    job.status = "accepted" if provider_id else "sent"
                    job.provider_message_id = provider_id
                    job.encrypted_payload = None
                    job.acceptance_unknown = False
                    if provider_id:
                        # A webhook may arrive before this acceptance transaction.
                        kinds = set(
                            db.scalars(
                                select(EmailEvent.kind).where(
                                    EmailEvent.provider_message_id == provider_id
                                )
                            )
                        )
                        for kind in (
                            "email.complained",
                            "email.bounced",
                            "email.suppressed",
                            "email.failed",
                            "email.delivered",
                        ):
                            if kind in kinds:
                                job.delivery_status = kind.removeprefix("email.")
                                break
                    sent += 1
    return sent
