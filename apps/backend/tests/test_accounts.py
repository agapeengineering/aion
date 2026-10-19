import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from test_auth import auth as auth
from test_auth import login
from test_profiles import DATA, headers
from test_reminders import DUE, Sender, enroll

from aion.auth import CHALLENGE_COOKIE, SESSION_COOKIE
from aion.models import (
    DeletionLedger,
    EmailChallenge,
    EmailSuppression,
    Profile,
    ProfileMutation,
    ReminderMail,
    ReminderPreference,
    Session,
    User,
    VerificationMail,
)
from aion.reminder_delivery import deliver_reminders, schedule_due
from aion.verification_mail import deliver_pending

pytestmark = pytest.mark.integration


def reverify(auth, language="en"):
    client, service, now, inbox = auth
    h = headers(client)
    sent = client.post("/api/v1/auth/reverify/challenges", headers=h, json={"language": language})
    assert sent.status_code == 202, sent.status_code
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 1
    message = list(inbox.messages.values())[-1]
    assert message.purpose == "reverify" and message.language == language
    value = {"challenge_id": sent.json()["challenge_id"], "code": message.code}
    old = client.cookies[SESSION_COOKIE]
    result = client.post("/api/v1/auth/reverify", headers=h, json=value)
    assert result.status_code == 200
    assert client.cookies[SESSION_COOKIE] != old
    return headers(client), value


def test_export_requires_fresh_session_verification_and_excludes_secrets(auth):
    client, service, now, _ = auth
    login(auth)
    h = headers(client)
    assert client.put("/api/v1/profile", headers=h, json=DATA).status_code == 200
    assert client.get("/api/v1/account/export", headers=h).status_code == 403
    h, value = reverify(auth, "es")
    assert client.post("/api/v1/auth/reverify", headers=h, json=value).status_code == 400
    result = client.get("/api/v1/account/export", headers=h)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert "attachment" in result.headers["content-disposition"]
    data = result.json()
    assert data["version"] == 1 and data["calendar"]["profile"] == DATA
    assert set(data) == {"version", "exported_at", "account", "calendar", "reminder_preferences"}
    for secret in ["token_digest", "csrf", "code_digest", "encrypted", "unsubscribe"]:
        assert secret not in result.text
    assert (
        client.get(
            "/api/v1/account/export", headers={**h, "X-Aion-Account": str(uuid.uuid4())}
        ).status_code
        == 409
    )
    now[0] += timedelta(minutes=10)
    assert client.get("/api/v1/account/export", headers=h).status_code == 403
    assert (
        client.request(
            "DELETE", "/api/v1/account", headers=h, json={"confirmation": "delete"}
        ).status_code
        == 403
    )


def test_reverification_bound_to_browser_session_and_cannot_login(auth):
    client, service, now, inbox = auth
    login(auth)
    original_cookies = dict(client.cookies)
    h = headers(client)
    sent = client.post("/api/v1/auth/reverify/challenges", headers=h, json={})
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 1
    value = {
        "challenge_id": sent.json()["challenge_id"],
        "code": list(inbox.messages.values())[-1].code,
    }
    binding = client.cookies[CHALLENGE_COOKIE]
    assert client.post("/api/v1/auth/verify", json=value).status_code == 400
    # A different session for the same owner cannot consume the code even with its browser binding.
    client.cookies.clear()
    now[0] += timedelta(seconds=61)
    login(auth)
    client.cookies.set(CHALLENGE_COOKIE, binding, domain="aion.test", path="/")
    assert (
        client.post("/api/v1/auth/reverify", headers=headers(client), json=value).status_code == 400
    )
    client.cookies.clear()
    for key, val in {**original_cookies, CHALLENGE_COOKIE: binding}.items():
        client.cookies.set(key, val, domain="aion.test", path="/")
    assert (
        client.post("/api/v1/auth/reverify", headers=headers(client), json=value).status_code == 200
    )


def test_sensitive_writes_require_owner_csrf_and_confirmation(auth):
    client = auth[0]
    login(auth)
    h, _ = reverify(auth)
    for path, method, body in [
        ("/auth/reverify/challenges", "POST", {}),
        ("/sessions", "DELETE", None),
        ("/account", "DELETE", {"confirmation": "delete"}),
    ]:
        assert (
            client.request(
                method, "/api/v1" + path, headers={**h, "X-CSRF-Token": "wrong"}, json=body
            ).status_code
            == 403
        )
        assert (
            client.request(
                method, "/api/v1" + path, headers={**h, "Origin": "https://wrong.test"}, json=body
            ).status_code
            == 403
        )
        assert (
            client.request(
                method,
                "/api/v1" + path,
                headers={**h, "X-Aion-Account": str(uuid.uuid4())},
                json=body,
            ).status_code
            == 409
        )
    assert (
        client.request(
            "DELETE", "/api/v1/account", headers=h, json={"confirmation": "yes"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/reverify/challenges", headers=h, json={"email": "other@example.test"}
        ).status_code
        == 422
    )


def test_session_listing_scoping_revocation_and_revoke_all(auth):
    client, _, now, _ = auth
    login(auth, "other@example.test")
    other_h = headers(client)
    other_id = client.get("/api/v1/sessions", headers=other_h).json()["sessions"][0]["id"]
    client.cookies.clear()
    login(auth)
    first = dict(client.cookies)
    h = headers(client)
    first_id = client.get("/api/v1/sessions", headers=h).json()["sessions"][0]["id"]
    assert client.delete(f"/api/v1/sessions/{other_id}", headers=h).status_code == 404
    assert client.delete(f"/api/v1/sessions/{uuid.uuid4()}", headers=h).status_code == 404
    client.cookies.clear()
    now[0] += timedelta(seconds=61)
    login(auth)
    h = headers(client)
    rows = client.get("/api/v1/sessions", headers=h).json()["sessions"]
    assert len(rows) == 2 and sum(r["current"] for r in rows) == 1
    assert all(
        set(r) == {"id", "created_at", "last_seen_at", "expires_at", "current"} for r in rows
    )
    assert client.delete(f"/api/v1/sessions/{first_id}", headers=h).status_code == 204
    active = dict(client.cookies)
    client.cookies.clear()
    for k, v in first.items():
        client.cookies.set(k, v, domain="aion.test", path="/")
    assert client.get("/api/v1/me").status_code == 401
    client.cookies.clear()
    for k, v in active.items():
        client.cookies.set(k, v, domain="aion.test", path="/")
    assert client.delete("/api/v1/sessions", headers=h).status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert client.get("/api/v1/me").status_code == 401


def test_delete_removes_active_private_data_pending_login_and_stale_cookie(auth):
    enroll(auth)
    client, service, now, _ = auth
    h, _ = reverify(auth)
    # A login challenge pending on another browser must not recreate an account after deletion.
    now[0] += timedelta(seconds=61)
    sent = client.post("/api/v1/auth/challenges", json={"email": "person@example.test"})
    assert sent.status_code == 202
    assert schedule_due(service, DUE) == 1
    cookies = dict(client.cookies)
    result = client.request("DELETE", "/api/v1/account", headers=h, json={"confirmation": "delete"})
    assert result.status_code == 204 and SESSION_COOKIE not in client.cookies
    with DbSession(service.engine) as db:
        for model in [
            User,
            Profile,
            Session,
            EmailChallenge,
            VerificationMail,
            ProfileMutation,
            ReminderPreference,
            ReminderMail,
        ]:
            assert db.scalar(select(func.count()).select_from(model)) == 0
        ledger = db.scalars(select(DeletionLedger)).one()
        assert str(ledger.user_id) == h["X-Aion-Account"] and len(ledger.email_digest) == 32
    for k, v in cookies.items():
        client.cookies.set(k, v, domain="aion.test", path="/")
    assert client.get("/api/v1/me").status_code == 401
    assert deliver_reminders(service, Sender(), DUE) == 0


def test_delete_serializes_with_in_flight_reminder_and_preserves_suppression(auth):
    enroll(auth)
    h, _ = reverify(auth)
    assert schedule_due(auth[1], DUE) == 1
    started, release = Event(), Event()

    class SlowSender(Sender):
        def send(self, message, key):
            started.set()
            assert release.wait(3)
            return super().send(message, key)

    with DbSession(auth[1].engine) as db, db.begin():
        db.add(EmailSuppression(email_digest=b"x" * 32, reason="bounced", created_at=auth[2][0]))
    with ThreadPoolExecutor(2) as pool:
        sending = pool.submit(deliver_reminders, auth[1], SlowSender(), DUE)
        assert started.wait(2)
        deleting = pool.submit(
            auth[0].request, "DELETE", "/api/v1/account", headers=h, json={"confirmation": "delete"}
        )
        assert not deleting.done()
        release.set()
        assert sending.result() == 1 and deleting.result().status_code == 204
    assert deliver_reminders(auth[1], Sender(), DUE + timedelta(minutes=1)) == 0
    with DbSession(auth[1].engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailSuppression)) == 1


def test_revoked_session_cancels_queued_reverification(auth):
    client, service, now, inbox = auth
    login(auth)
    h = headers(client)
    response = client.post("/api/v1/auth/reverify/challenges", headers=h, json={})
    assert response.status_code == 202
    assert client.delete("/api/v1/sessions", headers=h).status_code == 204
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 0
    with DbSession(service.engine) as db:
        rows = list(db.scalars(select(VerificationMail)))
        assert all(row.encrypted_payload is None for row in rows)


def test_delete_then_new_signup_does_not_restore_profile_or_reuse_identity(auth):
    client, service, now, _ = auth
    login(auth)
    assert client.put("/api/v1/profile", headers=headers(client), json=DATA).status_code == 200
    h, _ = reverify(auth)
    old_owner = h["X-Aion-Account"]
    assert (
        client.request(
            "DELETE", "/api/v1/account", headers=h, json={"confirmation": "delete"}
        ).status_code
        == 204
    )
    now[0] += timedelta(seconds=61)
    result = login(auth)
    assert str(result.json()["user"]["id"]) != old_owner
    assert result.json()["has_profile"] is False
    with DbSession(service.engine) as db:
        assert db.scalar(select(func.count()).select_from(DeletionLedger)) == 1


def test_deletion_failure_rolls_back_identity_challenges_and_marker(auth):
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError

    client, service, _, _ = auth
    login(auth)
    h, _ = reverify(auth)

    def fail_user_delete(connection, cursor, statement, parameters, context, many):
        if statement.startswith("DELETE FROM users"):
            raise SQLAlchemyError("synthetic deletion fault")

    event.listen(service.engine, "before_cursor_execute", fail_user_delete)
    try:
        result = client.request(
            "DELETE", "/api/v1/account", headers=h, json={"confirmation": "delete"}
        )
        assert result.status_code == 503
    finally:
        event.remove(service.engine, "before_cursor_execute", fail_user_delete)
    assert client.get("/api/v1/me").status_code == 200
    with DbSession(service.engine) as db:
        assert db.scalar(select(func.count()).select_from(DeletionLedger)) == 0
        assert db.scalar(select(func.count()).select_from(EmailChallenge)) == 2


@pytest.mark.parametrize("operation", ["logout", "current", "all"])
def test_revocation_atomically_cancels_confirmation_and_clears_binding_cookie(auth, operation):
    client, service, now, inbox = auth
    login(auth)
    h = headers(client)
    session_id = client.get("/api/v1/sessions", headers=h).json()["sessions"][0]["id"]
    assert client.post("/api/v1/auth/reverify/challenges", headers=h, json={}).status_code == 202
    assert CHALLENGE_COOKIE in client.cookies
    if operation == "logout":
        result = client.post("/api/v1/auth/logout", headers=h)
    else:
        path = "/api/v1/sessions" + (f"/{session_id}" if operation == "current" else "")
        result = client.delete(path, headers=h)
    assert result.status_code == 204
    assert SESSION_COOKIE not in client.cookies and CHALLENGE_COOKIE not in client.cookies
    with DbSession(service.engine) as db:
        challenge = db.scalar(select(EmailChallenge).where(EmailChallenge.purpose == "reverify"))
        assert challenge.invalidated_at == now[0]
        job = db.scalar(
            select(VerificationMail).where(VerificationMail.challenge_id == challenge.id)
        )
        assert job.encrypted_payload is None and job.status == "cancelled"
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 0


def test_repeated_revocation_preserves_original_retention_deadline(auth):
    from aion.verification_mail import cleanup_expired

    client, service, now, _ = auth
    login(auth)
    h = headers(client)
    identifier = uuid.uuid4()
    original = now[0] - timedelta(days=1)
    with DbSession(service.engine) as db, db.begin():
        db.add(
            Session(
                id=identifier,
                user_id=uuid.UUID(h["X-Aion-Account"]),
                token_digest=b"r" * 32,
                csrf_digest=b"c" * 32,
                created_at=now[0] - timedelta(days=2),
                last_seen_at=original,
                expires_at=now[0] + timedelta(days=1),
                absolute_expires_at=now[0] + timedelta(days=28),
                revoked_at=original,
            )
        )
    for _ in range(2):
        assert client.delete(f"/api/v1/sessions/{identifier}", headers=h).status_code == 204
    assert client.delete("/api/v1/sessions", headers=h).status_code == 204
    with DbSession(service.engine) as db:
        assert db.get(Session, identifier).revoked_at == original
    cleanup_expired(service.engine, now[0] + timedelta(days=6))
    with DbSession(service.engine) as db:
        assert db.get(Session, identifier) is None


def test_logout_waits_for_confirmation_dispatch_barrier(auth):
    from sqlalchemy import event

    client, service, now, _ = auth
    login(auth)
    h = headers(client)
    assert client.post("/api/v1/auth/reverify/challenges", headers=h, json={}).status_code == 202
    sending, release, locking = Event(), Event(), Event()

    class SlowSender(Sender):
        def send(self, message, key):
            sending.set()
            assert release.wait(3)
            return super().send(message, key)

    def before_sql(connection, cursor, statement, parameters, context, many):
        if "pg_advisory_xact_lock" in statement:
            locking.set()

    with ThreadPoolExecutor(2) as pool:
        delivering = pool.submit(
            deliver_pending, service.engine, service.keys, SlowSender(), now[0]
        )
        assert sending.wait(2)
        event.listen(service.engine, "before_cursor_execute", before_sql)
        try:
            logout = pool.submit(client.post, "/api/v1/auth/logout", headers=h)
            assert locking.wait(2)
            assert not logout.done()
        finally:
            release.set()
            event.remove(service.engine, "before_cursor_execute", before_sql)
        assert delivering.result() == 1 and logout.result().status_code == 204


def test_relative_confirmation_lifetime_tracks_server_remaining_window(auth):
    client, _, now, _ = auth
    login(auth)
    h, _ = reverify(auth)
    data = client.get("/api/v1/sessions", headers=h).json()
    assert data["reverified_for"] == 600
    now[0] += timedelta(seconds=305)
    assert client.get("/api/v1/sessions", headers=h).json()["reverified_for"] == 295
    now[0] += timedelta(seconds=295)
    data = client.get("/api/v1/sessions", headers=h).json()
    assert data["reverified_for"] == 0 and data["reverified_until"] is None
    assert client.get("/api/v1/account/export", headers=h).status_code == 403
