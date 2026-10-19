import base64
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from urllib.parse import urlsplit

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from svix.webhooks import Webhook
from test_auth import auth as auth
from test_auth import login
from test_profiles import DATA, headers

from aion.models import EmailEvent, EmailSuppression, ReminderMail, ReminderPreference, User
from aion.phrases import Collection, weekly_collection
from aion.reminder_delivery import deliver_reminders, schedule_due
from aion.schedules import next_occurrence
from aion.verification_mail import RetryDeliveryError, cleanup_expired, deliver_pending

pytestmark = pytest.mark.integration
PREF = {
    "enabled": True,
    "frequency": "weekly",
    "timezone": "UTC",
    "send_time": "09:00",
    "weekday": 6,
    "language": "en",
    "include_phrase": False,
    "consent": True,
    "notice_version": "2026-10-18",
}
DUE = datetime(2026, 10, 18, 9, tzinfo=UTC)


def prepare(auth):
    client, service, _, _ = auth
    login(auth)
    h = headers(client)
    assert client.put("/api/v1/profile", headers=h, json=DATA).status_code == 200
    service.settings.reminders_enabled = True
    service.settings.local_mail_capture = True
    return {**h, "If-Match": '"reminders-0"'}


def enroll(auth, **patch):
    h = prepare(auth)
    result = auth[0].put("/api/v1/reminder-preferences", headers=h, json={**PREF, **patch})
    assert result.status_code == 200, result.status_code
    return h, result.json()


class Sender:
    def __init__(self):
        self.sent = []

    def send(self, message, key):
        self.sent.append((message, key))
        return str(uuid.uuid4())


def test_explicit_consent_revision_owner_and_phrase_gate(auth):
    h = prepare(auth)
    client = auth[0]
    initial = client.get("/api/v1/reminder-preferences", headers=h).json()
    assert initial["revision"] == 0 and initial["preferences"] is None
    assert initial["available"] and not initial["phrase_available"]
    assert (
        client.put(
            "/api/v1/reminder-preferences", headers=h, json={**PREF, "consent": False}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/reminder-preferences", headers=h, json={**PREF, "include_phrase": True}
        ).status_code
        == 409
    )
    assert client.get("/api/v1/reminder-preferences", headers=h).json()["revision"] == 0
    saved = client.put("/api/v1/reminder-preferences", headers=h, json=PREF)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert datetime.fromisoformat(saved.json()["next_due_at"]) == DUE
    assert client.put("/api/v1/reminder-preferences", headers=h, json=PREF).status_code == 409
    assert (
        client.get(
            "/api/v1/reminder-preferences", headers={**h, "X-Aion-Account": str(uuid.uuid4())}
        ).status_code
        == 409
    )
    assert (
        client.put(
            "/api/v1/reminder-preferences", headers={**h, "X-CSRF-Token": "invalid"}, json=PREF
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/reminder-preferences", headers={**h, "Origin": "https://other.test"}, json=PREF
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"timezone": "Nowhere/Invalid"},
        {"send_time": "25:00"},
        {"weekday": True},
        {"frequency": "hourly"},
        {"enabled": "yes"},
        {"user_id": str(uuid.uuid4())},
    ],
)
def test_invalid_preferences_leave_no_enrollment(auth, patch):
    h = prepare(auth)
    assert (
        auth[0].put("/api/v1/reminder-preferences", headers=h, json={**PREF, **patch}).status_code
        == 422
    )
    assert auth[0].get("/api/v1/reminder-preferences", headers=h).json()["revision"] == 0


def test_requires_saved_profile_and_enabled_runtime(auth):
    client, service, _, _ = auth
    login(auth)
    h = {**headers(client), "If-Match": '"reminders-0"'}
    assert client.put("/api/v1/reminder-preferences", headers=h, json=PREF).status_code == 503
    service.settings.reminders_enabled = True
    assert client.put("/api/v1/reminder-preferences", headers=h, json=PREF).status_code == 409


def test_dated_snapshot_once_per_local_day_and_no_private_subject(auth):
    enroll(auth)
    service = auth[1]
    assert schedule_due(service, DUE - timedelta(seconds=1)) == 0
    assert schedule_due(service, DUE) == 1
    assert schedule_due(service, DUE) == 0
    sender = Sender()
    assert deliver_reminders(service, sender, DUE) == 1
    assert deliver_reminders(service, sender, DUE) == 0
    payload = sender.sent[0][0].provider_payload
    assert DATA["birthDate"] not in payload["text"] + payload["html"]
    assert "Weeks lived" in payload["text"] and "Weeks remaining" in payload["text"]
    assert "90" not in payload["subject"] and "2000" not in payload["subject"]
    assert payload["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    with DbSession(service.engine) as db:
        job = db.scalars(select(ReminderMail)).one()
        assert job.encrypted_payload is None and job.status == "accepted"
        assert db.get(ReminderPreference, job.user_id).next_due_at > DUE


def test_no_backlog_after_downtime(auth):
    enroll(auth)
    assert schedule_due(auth[1], DUE + timedelta(days=20)) == 0
    with DbSession(auth[1].engine) as db:
        assert db.scalar(select(func.count()).select_from(ReminderMail)) == 0
        assert db.scalars(select(ReminderPreference)).one().next_due_at > DUE + timedelta(days=20)


def test_profile_reset_disables_consent_and_cancels_jobs(auth):
    h, _ = enroll(auth)
    assert schedule_due(auth[1], DUE) == 1
    assert (
        auth[0].delete("/api/v1/profile", headers={**h, **headers(auth[0], 1)}).status_code == 200
    )
    assert deliver_reminders(auth[1], Sender(), DUE) == 0
    with DbSession(auth[1].engine) as db:
        pref = db.scalars(select(ReminderPreference)).one()
        assert not pref.enabled and pref.next_due_at is None
        job = db.scalars(select(ReminderMail)).one()
        assert job.status == "cancelled" and job.encrypted_payload is None


def test_hide_change_cancels_frozen_old_payload(auth):
    enroll(auth)
    schedule_due(auth[1], DUE)
    assert (
        auth[0]
        .put("/api/v1/profile", headers=headers(auth[0], 1), json={**DATA, "hideRemaining": True})
        .status_code
        == 200
    )
    assert deliver_reminders(auth[1], Sender(), DUE) == 0


def test_unsubscribe_get_is_read_only_post_is_idempotent(auth):
    h, _ = enroll(auth)
    schedule_due(auth[1], DUE)
    with DbSession(auth[1].engine) as db:
        job = db.scalars(select(ReminderMail)).one()
        payload = json.loads(auth[1].keys.seal.decrypt(job.encrypted_payload))
    path = urlsplit(payload["headers"]["List-Unsubscribe"][1:-1]).path
    client = auth[0]
    assert client.get(path).status_code == 200
    assert client.get("/api/v1/reminder-preferences", headers=h).json()["preferences"]["enabled"]
    # Capability scope permits standard one-click without cookies, session or CSRF.
    client.cookies.clear()
    assert (
        client.post(
            path, headers={"Origin": "https://scanner.test"}, data={"List-Unsubscribe": "One-Click"}
        ).status_code
        == 200
    )
    assert client.post(path).status_code == 200
    assert client.post("/api/v1/unsubscribe/invalid").status_code == 404
    assert deliver_reminders(auth[1], Sender(), DUE) == 0
    with DbSession(auth[1].engine) as db:
        assert db.scalars(select(ReminderPreference)).one().revision == 2


def test_frozen_retry_crash_recovery_and_one_hour_expiry(auth):
    enroll(auth)
    schedule_due(auth[1], DUE)
    calls = []

    class Crash:
        def send(self, message, key):
            calls.append((message.provider_payload, key))
            raise SystemExit("synthetic crash")

    with pytest.raises(SystemExit):
        deliver_reminders(auth[1], Crash(), DUE)
    assert deliver_reminders(auth[1], Sender(), DUE + timedelta(seconds=10)) == 0

    class Recover:
        def send(self, message, key):
            calls.append((message.provider_payload, key))
            raise RetryDeliveryError(uncertain=True)

    deliver_reminders(auth[1], Recover(), DUE + timedelta(seconds=31))
    assert calls[0] == calls[1]
    assert deliver_reminders(auth[1], Sender(), DUE + timedelta(hours=1)) == 0
    with DbSession(auth[1].engine) as db:
        job = db.scalars(select(ReminderMail)).one()
        assert job.status == "uncertain" and job.encrypted_payload is None


def test_concurrent_schedulers_and_workers_do_not_duplicate(auth):
    enroll(auth)
    with ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(lambda _: schedule_due(auth[1], DUE), range(2))) == 1
    sender = Sender()
    with ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(lambda _: deliver_reminders(auth[1], sender, DUE), range(2))) == 1
    assert len(sender.sent) == 1


def test_pause_waits_for_inflight_dispatch_then_prevents_new_dispatch(auth):
    h, _ = enroll(auth)
    schedule_due(auth[1], DUE)
    started, release = Event(), Event()

    class Slow:
        def send(self, message, key):
            started.set()
            assert release.wait(2)
            return str(uuid.uuid4())

    with ThreadPoolExecutor(2) as pool:
        sending = pool.submit(deliver_reminders, auth[1], Slow(), DUE)
        assert started.wait(2)
        paused = pool.submit(
            auth[0].put,
            "/api/v1/reminder-preferences",
            headers={**h, "If-Match": '"reminders-1"'},
            json={**PREF, "enabled": False, "consent": False},
        )
        assert not paused.done()
        release.set()
        assert sending.result() == 1
        assert paused.result().status_code == 200
    assert deliver_reminders(auth[1], Sender(), DUE + timedelta(minutes=1)) == 0


def sign_event(auth, tmp_path, event_id, kind, provider_id, **changes):
    secret = "whsec_" + base64.b64encode(b"s" * 32).decode()
    path = tmp_path / "webhook-secret"
    path.write_text(secret)
    auth[1].settings.resend_webhook_secret_file = path
    body = json.dumps(
        {
            "type": kind,
            "data": {
                "email_id": provider_id,
                "from": auth[1].settings.email_from,
                "to": ["person@example.test"],
                **changes,
            },
        }
    )
    now = datetime.now(UTC)
    return body, {
        "svix-id": event_id,
        "svix-timestamp": str(int(now.timestamp())),
        "svix-signature": Webhook(secret).sign(event_id, now, body),
    }


def test_verified_webhook_dedup_and_sticky_suppression(auth, tmp_path):
    enroll(auth)
    schedule_due(auth[1], DUE)
    sender = Sender()
    deliver_reminders(auth[1], sender, DUE)
    with DbSession(auth[1].engine) as db:
        identifier = db.scalars(select(ReminderMail)).one().provider_message_id
    body, h = sign_event(auth, tmp_path, "msg_test", "email.complained", identifier)
    assert auth[0].post("/api/v1/webhooks/resend", headers=h, content=body + " ").status_code == 400
    assert auth[0].post("/api/v1/webhooks/resend", headers=h, content=body).status_code == 204
    assert auth[0].post("/api/v1/webhooks/resend", headers=h, content=body).status_code == 204
    body, h = sign_event(auth, tmp_path, "msg_late", "email.delivered", identifier)
    assert auth[0].post("/api/v1/webhooks/resend", headers=h, content=body).status_code == 204
    with DbSession(auth[1].engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailEvent)) == 2
        assert db.scalar(select(func.count()).select_from(EmailSuppression)) == 1
        assert not db.scalars(select(ReminderPreference)).one().enabled
        assert db.scalars(select(ReminderMail)).one().delivery_status == "complained"
    auth[2][0] += timedelta(seconds=61)
    issue_value = auth[0].post("/api/v1/auth/challenges", json={"email": "person@example.test"})
    assert issue_value.status_code == 202
    assert deliver_pending(auth[1].engine, auth[1].keys, auth[3], auth[2][0]) == 0


def test_webhook_replay_window_and_other_product_isolation(auth, tmp_path):
    enroll(auth)
    body, h = sign_event(auth, tmp_path, "msg_old", "email.bounced", str(uuid.uuid4()))
    h["svix-timestamp"] = "1"
    assert auth[0].post("/api/v1/webhooks/resend", headers=h, content=body).status_code == 400
    body, h = sign_event(
        auth,
        tmp_path,
        "msg_other",
        "email.bounced",
        str(uuid.uuid4()),
        **{"from": "Other <other@example.test>"},
    )
    assert auth[0].post("/api/v1/webhooks/resend", headers=h, content=body).status_code == 204
    with DbSession(auth[1].engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailSuppression)) == 0


@pytest.mark.parametrize("unknown", [False, True])
def test_cleanup_purges_expired_payload_even_when_reminders_paused(auth, unknown):
    enroll(auth)
    assert schedule_due(auth[1], DUE) == 1
    with DbSession(auth[1].engine) as db, db.begin():
        job = db.scalars(select(ReminderMail)).one()
        job.acceptance_unknown = unknown
        job.lease_until = DUE + timedelta(minutes=30)
    auth[1].settings.reminders_enabled = False
    cleanup_expired(auth[1].engine, DUE + timedelta(hours=1))
    with DbSession(auth[1].engine) as db:
        job = db.scalars(select(ReminderMail)).one()
        assert job.encrypted_payload is None and job.lease_until is None
        assert job.status == ("uncertain" if unknown else "expired")


def test_metadata_cleanup_and_independent_suppression(auth, tmp_path):
    enroll(auth)
    body, h = sign_event(auth, tmp_path, "msg_known", "email.bounced", str(uuid.uuid4()))
    assert auth[0].post("/api/v1/webhooks/resend", headers=h, content=body).status_code == 204
    with DbSession(auth[1].engine) as db, db.begin():
        db.delete(db.scalars(select(User)).one())
    cleanup_expired(auth[1].engine, auth[2][0] + timedelta(days=31))
    with DbSession(auth[1].engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailEvent)) == 0
        assert db.scalar(select(func.count()).select_from(EmailSuppression)) == 1


@pytest.mark.parametrize(
    "zone,start,expected",
    [
        ("America/New_York", "2026-03-08T00:00:00+00:00", "2026-03-08T07:00:00+00:00"),
        ("America/New_York", "2026-11-01T00:00:00+00:00", "2026-11-01T07:30:00+00:00"),
    ],
)
def test_dst_schedule(zone, start, expected):
    # Gap at 02:30 resolves to 03:00; fall 02:30 is after the fold.
    result = next_occurrence(datetime.fromisoformat(start), zone, "02:30", "daily", 6)
    assert result == datetime.fromisoformat(expected)


def test_fold_never_uses_second_occurrence():
    first = next_occurrence(
        datetime(2026, 11, 1, 0, tzinfo=UTC), "America/New_York", "01:30", "daily", 6
    )
    assert first == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    after = next_occurrence(
        datetime(2026, 11, 1, 6, tzinfo=UTC), "America/New_York", "01:30", "daily", 6
    )
    assert after == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)


def test_weekly_bank_is_anchored_without_automatic_wraparound():
    assert weekly_collection().sequence == []
    sample = {
        "id": "sample-1",
        "author": "Example author",
        "work": "Example work",
        "location": "Section 1",
        "original_language": "en",
        "original": "Synthetic original.",
        "source_url": "https://example.test/source",
        "rights": "Synthetic test content",
        "approved": True,
        "en": {
            "text": "Synthetic passage.",
            "translator": "Original",
            "source": "https://example.test/source",
            "rights": "Synthetic",
            "approved": True,
        },
        "es": {
            "text": "Pasaje sintético.",
            "translator": "Test translation",
            "source": "https://example.test/source",
            "rights": "Synthetic",
            "approved": True,
        },
    }
    bank = Collection.model_validate(
        {
            "version": 1,
            "collectionVersion": "test",
            "anchorSunday": "2026-10-18",
            "sequence": ["sample-1"],
            "phrases": [sample],
        }
    )
    assert bank.for_date(datetime(2026, 10, 18).date()).id == "sample-1"
    assert bank.for_date(datetime(2026, 10, 24).date()).id == "sample-1"
    assert bank.for_date(datetime(2026, 10, 25).date()) is None
    sample["es"]["approved"] = False
    with pytest.raises(ValueError):
        Collection.model_validate(
            {
                "version": 1,
                "collectionVersion": "test",
                "anchorSunday": "2026-10-18",
                "sequence": ["sample-1"],
                "phrases": [sample],
            }
        )


def synthetic_bank():
    translation = {
        "text": "Synthetic reflection.",
        "translator": "Test translator",
        "source": "Test edition",
        "rights": "Synthetic test text",
        "approved": True,
    }
    entry = {
        "id": "AION-TEST-001",
        "author": "Test author",
        "work": "Test work",
        "location": "Section 1",
        "original_language": "en",
        "original": "Synthetic original.",
        "source_url": "https://example.test/source",
        "rights": "Synthetic test text",
        "approved": True,
        "en": translation,
        "es": {**translation, "text": "Reflexión sintética."},
    }
    return Collection.model_validate(
        {
            "version": 1,
            "collectionVersion": "test-1",
            "anchorSunday": "2026-10-18",
            "sequence": [entry["id"]],
            "phrases": [entry],
        }
    )


def test_approved_weekly_phrase_and_attribution_are_frozen(auth, monkeypatch):
    bank = synthetic_bank()
    monkeypatch.setattr("aion.reminders.weekly_collection", lambda: bank)
    monkeypatch.setattr("aion.reminder_delivery.weekly_collection", lambda: bank)
    enroll(auth, include_phrase=True)
    assert schedule_due(auth[1], DUE) == 1
    sender = Sender()
    assert deliver_reminders(auth[1], sender, DUE) == 1
    text = sender.sent[0][0].provider_payload["text"]
    assert "Synthetic reflection." in text and "Test author" in text and "Test translator" in text
    with DbSession(auth[1].engine) as db:
        job = db.scalars(select(ReminderMail)).one()
        assert job.phrase_id == "AION-TEST-001" and job.content_version == "test-1"


def test_content_revision_cancels_previously_queued_phrase(auth, monkeypatch):
    bank = synthetic_bank()
    monkeypatch.setattr("aion.reminders.weekly_collection", lambda: bank)
    monkeypatch.setattr("aion.reminder_delivery.weekly_collection", lambda: bank)
    enroll(auth, include_phrase=True)
    schedule_due(auth[1], DUE)
    bank.collectionVersion = "test-2"
    assert deliver_reminders(auth[1], Sender(), DUE) == 0


def test_missing_published_week_is_skipped_without_starving_other_accounts(auth, monkeypatch):
    bank = synthetic_bank()
    monkeypatch.setattr("aion.reminders.weekly_collection", lambda: bank)
    monkeypatch.setattr("aion.reminder_delivery.weekly_collection", lambda: bank)
    enroll(auth, include_phrase=True)
    bank.sequence = []
    assert schedule_due(auth[1], DUE) == 0
    with DbSession(auth[1].engine) as db:
        assert db.scalars(select(ReminderPreference)).one().next_due_at > DUE
        assert db.scalars(select(ReminderMail)).one().delivery_status == "content_unavailable"


@pytest.mark.parametrize("timezone", ["UTC", "America/Los_Angeles", "Asia/Tokyo"])
@pytest.mark.parametrize("hidden", [False, True])
def test_reminder_rendering_localized_date_hide_preference_and_horizon(timezone, hidden):
    from aion.models import Profile
    from aion.reminder_content import render_reminder

    profile = Profile(
        birth_date=datetime(2000, 1, 1).date(), lifespan_years=1, hide_remaining=hidden
    )
    pref = ReminderPreference(timezone=timezone, language="en", include_phrase=False)
    payload, identifier = render_reminder(
        profile,
        pref,
        DUE,
        synthetic_bank(),
        origin="https://aion.test",
        email="person@example.test",
        sender="Aion <sender@example.test>",
        reply_to="support@example.test",
        token="synthetic-token",
    )
    assert identifier is None
    assert ("Weeks remaining: 0" in payload["text"]) is (not hidden)
    assert "Weeks lived:" in payload["text"] and "Your life continues" in payload["text"]
    assert "2000-01-01" not in payload["text"] + payload["html"]
    assert "1" not in payload["subject"]


def test_lost_unsubscribe_key_fails_closed_without_blocking_worker(auth):
    enroll(auth)
    with DbSession(auth[1].engine) as db, db.begin():
        pref = db.scalars(select(ReminderPreference)).one()
        pref.encrypted_token = b"unreadable-synthetic-token"
    assert schedule_due(auth[1], DUE) == 0
    with DbSession(auth[1].engine) as db:
        pref = db.scalars(select(ReminderPreference)).one()
        assert not pref.enabled and pref.next_due_at is None and pref.revision == 2


def test_signed_malformed_event_type_is_rejected(auth, tmp_path):
    prepare(auth)
    body, h = sign_event(auth, tmp_path, "msg_malformed", [], str(uuid.uuid4()))
    assert auth[0].post("/api/v1/webhooks/resend", headers=h, content=body).status_code == 400
