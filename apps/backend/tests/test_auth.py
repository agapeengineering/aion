import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from starlette.requests import Request

from aion.auth import CHALLENGE_COOKIE, SESSION_COOKIE, AuthError, VerifyInput
from aion.main import create_app
from aion.models import EmailChallenge, Session, User, VerificationMail
from aion.verification_mail import Message, cleanup_expired, deliver_pending

pytestmark = pytest.mark.integration
ORIGIN = "https://aion.test"


class Inbox:
    def __init__(self):
        self.messages = {}

    def send(self, message: Message, key: str) -> None:
        self.messages[key] = message


@pytest.fixture
def auth(database, database_settings, tmp_path: Path):
    import secrets

    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                name: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                for name in ["mac", "csrf", "seal"]
            }
        )
    )
    settings = database_settings.model_copy(
        update={
            "auth_enabled": True,
            "auth_origin": ORIGIN,
            "auth_secrets_file": path,
        }
    )
    app = create_app(settings)
    now = [datetime(2026, 10, 17, 12, tzinfo=UTC)]
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        app.state.auth.clock = lambda: now[0]
        yield client, app.state.auth, now, Inbox()


def issue(auth, email="person@example.test", language="en"):
    client, service, now, inbox = auth
    response = client.post("/api/v1/auth/challenges", json={"email": email, "language": language})
    assert response.status_code == 202
    assert set(response.json()) == {"challenge_id", "expires_in", "resend_after"}
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 1
    code = list(inbox.messages.values())[-1].code
    return {"challenge_id": response.json()["challenge_id"], "code": code}


def login(auth, email="person@example.test"):
    value = issue(auth, email)
    response = auth[0].post("/api/v1/auth/verify", json=value)
    assert response.status_code == 200
    return response


def test_signup_only_after_verification_and_sealed_payload_is_purged(auth):
    client, service, now, inbox = auth
    response = client.post("/api/v1/auth/challenges", json={"email": "person@example.test"})
    with DbSession(service.engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalars(select(VerificationMail)).one().encrypted_payload is not None
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 1
    code = list(inbox.messages.values())[0].code
    result = client.post(
        "/api/v1/auth/verify",
        json={
            "challenge_id": response.json()["challenge_id"],
            "code": code,
        },
    )
    assert result.status_code == 200 and result.json()["has_profile"] is False
    assert client.get("/api/v1/me").json()["email"] == "person@example.test"
    assert "Secure" in result.headers["set-cookie"]
    assert "HttpOnly" in result.headers["set-cookie"]
    assert "SameSite=lax" in result.headers["set-cookie"]
    assert result.headers["cache-control"] == "no-store"
    with DbSession(service.engine) as db:
        assert db.scalars(select(VerificationMail)).one().encrypted_payload is None
        assert (
            db.scalars(select(Session)).one().token_digest
            != client.cookies[SESSION_COOKIE].encode()
        )
    assert client.cookies[SESSION_COOKIE] not in result.text
    assert code not in result.text


def test_existing_identity_normalization_and_session_rotation(auth):
    first = login(auth, " Person@EXAMPLE.test ")
    old_cookie = auth[0].cookies[SESSION_COOKIE]
    auth[2][0] += timedelta(seconds=61)
    second = login(auth)
    assert first.json()["user"] == second.json()["user"]
    assert auth[0].cookies[SESSION_COOKIE] != old_cookie
    with DbSession(auth[1].engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert (
            db.scalar(
                select(func.count()).select_from(Session).where(Session.revoked_at.is_not(None))
            )
            == 1
        )


def test_wrong_code_attempts_commit_and_correct_code_cannot_bypass_five(auth):
    value = issue(auth)
    wrong = dict(value, code=f"{(int(value['code']) + 1) % 100000000:08d}")
    for _ in range(5):
        assert auth[0].post("/api/v1/auth/verify", json=wrong).status_code == 400
    with DbSession(auth[1].engine) as db:
        assert db.scalars(select(EmailChallenge)).one().attempts == 5
    assert auth[0].post("/api/v1/auth/verify", json=value).status_code == 400


def test_expired_code_and_replay_are_rejected(auth):
    value = issue(auth)
    auth[2][0] += timedelta(seconds=601)
    assert auth[0].post("/api/v1/auth/verify", json=value).status_code == 400
    value = issue(auth)
    cookie = auth[0].cookies[CHALLENGE_COOKIE]
    assert auth[0].post("/api/v1/auth/verify", json=value).status_code == 200
    assert (
        auth[0]
        .post("/api/v1/auth/verify", json=value, headers={"Cookie": f"{CHALLENGE_COOKIE}={cookie}"})
        .status_code
        == 400
    )


def test_wrong_browser_cannot_verify_or_consume_victims_attempts(auth):
    value = issue(auth)
    bad = auth[0].post(
        "/api/v1/auth/verify",
        json=value,
        headers={"Cookie": f"{CHALLENGE_COOKIE}=different-browser"},
    )
    assert bad.status_code == 400
    with DbSession(auth[1].engine) as db:
        assert db.scalars(select(EmailChallenge)).one().attempts == 0
    assert auth[0].post("/api/v1/auth/verify", json=value).status_code == 200


def test_resend_cooldown_invalidation_and_email_budget(auth):
    first = issue(auth)
    limited = auth[0].post("/api/v1/auth/challenges", json={"email": "person@example.test"})
    assert limited.status_code == 429 and limited.headers["retry-after"] == "60"
    for _ in range(2):
        auth[2][0] += timedelta(seconds=61)
        current = issue(auth)
    auth[2][0] += timedelta(seconds=61)
    assert (
        auth[0].post("/api/v1/auth/challenges", json={"email": "person@example.test"}).status_code
        == 429
    )
    assert auth[0].post("/api/v1/auth/verify", json=first).status_code == 400
    assert auth[0].post("/api/v1/auth/verify", json=current).status_code == 200


def test_ip_send_budget_is_shared_between_different_addresses(auth):
    for i in range(20):
        assert (
            auth[0]
            .post("/api/v1/auth/challenges", json={"email": f"person{i}@example.test"})
            .status_code
            == 202
        )
    assert (
        auth[0].post("/api/v1/auth/challenges", json={"email": "another@example.test"}).status_code
        == 429
    )


def test_origin_validation_and_unsupported_purpose(auth):
    for origin in ["", "https://attacker.example", "null"]:
        assert (
            auth[0]
            .post(
                "/api/v1/auth/challenges",
                json={"email": "person@example.test"},
                headers={"Origin": origin},
            )
            .status_code
            == 403
        )
    assert (
        auth[0]
        .post(
            "/api/v1/auth/challenges", json={"email": "person@example.test", "purpose": "reverify"}
        )
        .status_code
        == 422
    )


def test_csrf_is_stable_bound_to_session_and_logout_revokes_it(auth):
    login(auth)
    client = auth[0]
    old_cookie = client.cookies[SESSION_COOKIE]
    nonce = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert client.get("/api/v1/auth/csrf").json()["csrf_token"] == nonce
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "https://attacker.example", "X-CSRF-Token": nonce},
        ).status_code
        == 403
    )
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": nonce}).status_code == 204
    assert client.get("/api/v1/me").status_code == 401
    assert (
        client.get("/api/v1/me", headers={"Cookie": f"{SESSION_COOKIE}={old_cookie}"}).status_code
        == 401
    )


@pytest.mark.parametrize("days", [7, 31])
def test_session_idle_or_absolute_expiry(auth, days):
    login(auth)
    auth[2][0] += timedelta(days=days)
    assert auth[0].get("/api/v1/me").status_code == 401


def test_concurrent_verification_consumes_once_and_creates_one_session(auth):
    value = issue(auth)
    browser = auth[0].cookies[CHALLENGE_COOKIE]
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"origin", ORIGIN.encode()),
                (b"cookie", f"{CHALLENGE_COOKIE}={browser}".encode()),
            ],
            "client": ("127.0.0.1", 1234),
        }
    )

    def verify(_):
        try:
            auth[1].verify(VerifyInput(**value), request)
            return 200
        except AuthError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(verify, range(2))) == [200, 400]
    with DbSession(auth[1].engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Session)) == 1


def test_expired_outbox_is_not_delivered_and_payload_is_removed(auth):
    client, service, now, inbox = auth
    assert (
        client.post("/api/v1/auth/challenges", json={"email": "person@example.test"}).status_code
        == 202
    )
    now[0] += timedelta(minutes=11)
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 0
    cleanup_expired(service.engine, now[0] + timedelta(days=2))
    assert not inbox.messages
    with DbSession(service.engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailChallenge)) == 0


def test_transient_delivery_failure_retries_same_logical_message(auth):
    client, service, now, inbox = auth
    client.post("/api/v1/auth/challenges", json={"email": "person@example.test"})

    class Offline:
        def send(self, message, key):
            raise OSError("simulated outage")

    assert deliver_pending(service.engine, service.keys, Offline(), now[0]) == 0
    now[0] += timedelta(seconds=5)
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 1
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 0
    assert len(inbox.messages) == 1


def test_absolute_expiry_even_when_session_remains_active(auth):
    client, _, now, _ = auth
    login(auth)
    for _ in range(4):
        now[0] += timedelta(days=6)
        assert client.get("/api/v1/me").status_code == 200
    now[0] += timedelta(days=6, seconds=1)
    assert client.get("/api/v1/me").status_code == 401


def test_csrf_nonce_cannot_revoke_another_identity(auth):
    client, _, _, _ = auth
    login(auth, "first@example.test")
    first_token = client.cookies[SESSION_COOKIE]
    first_nonce = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    client.cookies.clear()
    login(auth, "second@example.test")
    assert (
        client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": first_nonce}).status_code == 403
    )
    assert client.get("/api/v1/me").json()["email"] == "second@example.test"
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, first_token)
    assert client.get("/api/v1/me").json()["email"] == "first@example.test"


def test_resend_outbox_freezes_payload_and_tracks_provider_acceptance(auth, tmp_path):
    import uuid

    from aion.resend_mail import ProviderResponse, ResendSender

    client, service, now, _ = auth
    service.settings.resend_enabled = True
    service.settings.resend_allowed_recipients = ["person@example.test"]
    service.settings.email_reply_to = "support@example.test"
    key = tmp_path / "resend-key"
    key.write_text("re_synthetic_not_a_real_key")
    service.settings.resend_api_key_file = key
    assert (
        client.post("/api/v1/auth/challenges", json={"email": "person@example.test"}).status_code
        == 202
    )
    assert (
        client.post("/api/v1/auth/challenges", json={"email": "blocked@example.test"}).json()[
            "error"
        ]["code"]
        == "email_not_allowed"
    )
    requests = []
    provider_id = str(uuid.uuid4())

    def transport(secret, payload, logical_key):
        requests.append((payload, logical_key))
        if len(requests) == 1:
            return ProviderResponse(429, {"Retry-After": "20"}, b"{}")
        return ProviderResponse(200, {}, json.dumps({"id": provider_id}).encode())

    sender = ResendSender(service.settings, transport)
    assert deliver_pending(service.engine, service.keys, sender, now[0]) == 0
    service.settings.email_reply_to = "changed@example.test"
    now[0] += timedelta(seconds=21)
    assert deliver_pending(service.engine, service.keys, sender, now[0]) == 1
    assert requests[0] == requests[1]
    assert requests[1][0]["reply_to"] == "support@example.test"
    with DbSession(service.engine) as db:
        job = db.scalars(select(VerificationMail)).one()
        assert job.status == "accepted" and job.provider_message_id == provider_id
        assert job.attempts == 2 and not job.acceptance_unknown
        assert job.encrypted_payload is None


def test_delivery_crash_persists_uncertainty_and_expiry_never_resends(auth):
    client, service, now, inbox = auth
    client.post("/api/v1/auth/challenges", json={"email": "person@example.test"})

    class Crash:
        def send(self, message, key):
            raise SystemExit("simulated crash after unknown provider acceptance")

    with pytest.raises(SystemExit):
        deliver_pending(service.engine, service.keys, Crash(), now[0])
    with DbSession(service.engine) as db:
        job = db.scalars(select(VerificationMail)).one()
        assert job.status == "pending" and job.attempts == 1 and job.acceptance_unknown
    now[0] += timedelta(minutes=11)
    cleanup_expired(service.engine, now[0])
    assert deliver_pending(service.engine, service.keys, inbox, now[0]) == 0
    with DbSession(service.engine) as db:
        job = db.scalars(select(VerificationMail)).one()
        assert job.status == "uncertain" and job.encrypted_payload is None
    assert not inbox.messages


def test_provider_acceptance_after_crash_reuses_one_logical_send(auth):
    import uuid

    client, service, now, _ = auth
    client.post("/api/v1/auth/challenges", json={"email": "person@example.test"})
    accepted = {}
    calls = []

    class Provider:
        def send(self, message, key):
            calls.append(key)
            if key not in accepted:
                accepted[key] = str(uuid.uuid4())
                raise SystemExit("simulated crash after provider accepted")
            return accepted[key]

    with pytest.raises(SystemExit):
        deliver_pending(service.engine, service.keys, Provider(), now[0])
    assert deliver_pending(service.engine, service.keys, Provider(), now[0]) == 1
    assert len(accepted) == 1 and len(calls) == 2 and calls[0] == calls[1]
    with DbSession(service.engine) as db:
        job = db.scalars(select(VerificationMail)).one()
        assert job.status == "accepted" and job.provider_message_id == accepted[calls[0]]
        assert job.encrypted_payload is None and not job.acceptance_unknown


def test_concurrent_delivery_workers_dispatch_only_once(auth):
    import time

    client, service, now, _ = auth
    client.post("/api/v1/auth/challenges", json={"email": "person@example.test"})
    calls = []

    class Provider:
        def send(self, message, key):
            calls.append(key)
            time.sleep(0.1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: deliver_pending(service.engine, service.keys, Provider(), now[0]),
                range(2),
            )
        )
    assert sum(results) == 1 and len(calls) == 1
