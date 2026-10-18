import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from test_auth import auth as auth
from test_auth import login

from aion.auth import SESSION_COOKIE
from aion.models import Profile, ProfileMutation
from aion.verification_mail import cleanup_expired

pytestmark = pytest.mark.integration
DATA = {
    "version": 1,
    "birthDate": "2000-02-29",
    "lifespanYears": 90,
    "language": "en",
    "unit": "weeks",
    "hideRemaining": False,
}


def headers(client, revision=0, operation=None, owner=None):
    return {
        "X-Aion-Account": owner or client.get("/api/v1/me").json()["id"],
        "If-Match": f'"profile-{revision}"',
        "Idempotency-Key": str(operation or uuid.uuid4()),
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"],
    }


def test_explicit_create_versioned_update_and_reset_tombstone(auth):
    client, service, _, _ = auth
    login(auth)
    h = headers(client)
    initial = client.get("/api/v1/profile", headers=h)
    assert initial.status_code == 200 and initial.json()["profile"] is None
    assert initial.json()["revision"] == 0
    assert client.put("/api/v1/profile", headers=h, json=DATA).json()["revision"] == 1
    updated = client.put(
        "/api/v1/profile", headers=headers(client, 1), json={**DATA, "lifespanYears": 95}
    )
    assert updated.json()["profile"]["lifespanYears"] == 95
    reset_headers = headers(client, 2)
    deleted = client.delete("/api/v1/profile", headers=reset_headers)
    assert deleted.json()["revision"] == 3 and deleted.json()["profile"] is None
    assert client.delete("/api/v1/profile", headers=reset_headers).json()["revision"] == 3
    stale = client.put("/api/v1/profile", headers=headers(client, 0), json=DATA)
    assert stale.status_code == 409 and stale.json()["current"]["profile"] is None
    with DbSession(service.engine) as db:
        assert db.scalar(select(func.count()).select_from(Profile)) == 1
        assert db.scalar(select(func.count()).select_from(ProfileMutation)) == 3


def test_idempotent_retry_cannot_overwrite_a_newer_edit(auth):
    client = auth[0]
    login(auth)
    original = headers(client)
    assert client.put("/api/v1/profile", headers=original, json=DATA).status_code == 200
    assert client.put("/api/v1/profile", headers=original, json=DATA).json()["revision"] == 1
    assert (
        client.put("/api/v1/profile", headers=original, json={**DATA, "unit": "days"}).status_code
        == 409
    )
    assert (
        client.put(
            "/api/v1/profile", headers=headers(client, 1), json={**DATA, "unit": "days"}
        ).status_code
        == 200
    )
    retry = client.put("/api/v1/profile", headers=original, json=DATA)
    assert retry.status_code == 409 and retry.json()["current"]["profile"]["unit"] == "days"


def test_identity_binding_and_csrf_prevent_wrong_account_upload(auth):
    client = auth[0]
    login(auth, "first@example.test")
    first = headers(client)
    assert client.put("/api/v1/profile", headers=first, json=DATA).status_code == 200
    client.cookies.clear()
    login(auth, "second@example.test")
    second = headers(client)
    assert client.get("/api/v1/profile", headers=second).json()["profile"] is None
    assert (
        client.put(
            "/api/v1/profile",
            headers={**second, "X-Aion-Account": first["X-Aion-Account"]},
            json=DATA,
        ).status_code
        == 409
    )
    assert (
        client.put(
            "/api/v1/profile", headers={**second, "X-CSRF-Token": first["X-CSRF-Token"]}, json=DATA
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/profile", headers={**second, "Origin": "https://other.test"}, json=DATA
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/profile", headers=second, json={**DATA, "user_id": first["X-Aion-Account"]}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"version": 2},
        {"version": True},
        {"birthDate": "2000-02-30"},
        {"birthDate": "9999-12-31"},
        {"lifespanYears": True},
        {"lifespanYears": "90"},
        {"lifespanYears": 10000},
        {"language": "xx"},
        {"unit": "ticks"},
        {"hideRemaining": "false"},
    ],
)
def test_invalid_profile_never_overwrites(auth, patch):
    client = auth[0]
    login(auth)
    assert (
        client.put("/api/v1/profile", headers=headers(client), json={**DATA, **patch}).status_code
        == 422
    )
    assert client.get("/api/v1/profile", headers=headers(client)).json()["revision"] == 0


def test_concurrent_create_has_one_winner(auth):
    client = auth[0]
    login(auth)
    h = headers(client)

    def put(_):
        return client.put(
            "/api/v1/profile", headers={**h, "Idempotency-Key": str(uuid.uuid4())}, json=DATA
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(put, range(2))) == [200, 409]


def test_expired_and_revoked_sessions_cannot_write(auth):
    client = auth[0]
    login(auth)
    h = headers(client)
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 204
    assert client.put("/api/v1/profile", headers=h, json=DATA).status_code == 401


def test_expired_operation_metadata_never_makes_old_revision_writable(auth):
    client, service, now, _ = auth
    login(auth)
    original = headers(client)
    assert client.put("/api/v1/profile", headers=original, json=DATA).status_code == 200
    with DbSession(service.engine) as db, db.begin():
        db.scalars(select(ProfileMutation)).one().created_at = now[0] - timedelta(days=31)
    cleanup_expired(service.engine, now[0])
    with DbSession(service.engine) as db:
        assert db.scalar(select(func.count()).select_from(ProfileMutation)) == 0
    assert client.put("/api/v1/profile", headers=original, json=DATA).status_code == 409
    assert client.get("/api/v1/profile", headers=headers(client)).json()["revision"] == 1


def test_independently_verified_sessions_share_profile_and_conflict_on_stale_write(auth):
    client, _, now, _ = auth
    login(auth)
    first_cookie = client.cookies[SESSION_COOKIE]
    first = headers(client)
    assert client.put("/api/v1/profile", headers=first, json=DATA).status_code == 200
    client.cookies.clear()
    now[0] += timedelta(seconds=61)
    assert login(auth).json()["has_profile"] is True
    assert client.cookies[SESSION_COOKIE] != first_cookie
    second = headers(client, 1)
    assert (
        client.put("/api/v1/profile", headers=second, json={**DATA, "lifespanYears": 95}).json()[
            "revision"
        ]
        == 2
    )
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, first_cookie, domain="aion.test", path="/")
    assert client.get("/api/v1/profile", headers=first).json()["profile"]["lifespanYears"] == 95
    assert (
        client.put(
            "/api/v1/profile", headers={**first, "If-Match": '"profile-1"'}, json=DATA
        ).status_code
        == 409
    )
