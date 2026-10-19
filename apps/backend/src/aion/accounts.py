"""Owned sessions, session-bound reverification, export and irreversible account removal."""

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from aion.auth import (
    CHALLENGE_COOKIE,
    SESSION_COOKIE,
    AuthError,
    AuthService,
    ChallengeInput,
    ChallengeResult,
    VerifyInput,
    service,
    set_cookie,
    token_digest,
)
from aion.models import DeletionLedger, EmailChallenge, Profile, ReminderPreference, Session, User
from aion.profiles import Owner, ProfileSnapshot, snapshot
from aion.reminders import stop
from aion.session_revocation import revoke

router = APIRouter(prefix="/api/v1")


class ReverifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["en", "es"] = "en"


class VerifiedResult(BaseModel):
    reverified_until: datetime
    reverified_for: int = Field(ge=0, le=600)


class SessionItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool


class SessionList(BaseModel):
    user_id: uuid.UUID
    reverified_until: datetime | None
    reverified_for: int = Field(ge=0, le=600)
    sessions: list[SessionItem]


class DeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["delete"]


class ExportIdentity(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime
    verified_at: datetime


class ExportReminder(BaseModel):
    enabled: bool
    frequency: Literal["daily", "weekly"]
    timezone: str
    send_time: str
    weekday: int
    language: Literal["en", "es"]
    include_phrase: bool
    consent_at: datetime | None
    notice_version: str


class AccountExport(BaseModel):
    version: Literal[1] = 1
    exported_at: datetime
    account: ExportIdentity
    calendar: ProfileSnapshot
    reminder_preferences: ExportReminder | None


def owned(
    db: DbSession, auth: AuthService, request: Request, owner: uuid.UUID, *, write: bool = False
) -> tuple[User, Session]:
    identity, _ = auth.session_in(db, request, write=write)
    if identity.id != owner:
        raise AuthError(409, "account_changed")
    user = db.get(User, owner)
    assert user
    session = db.scalars(
        select(Session).where(
            Session.token_digest == token_digest(request.cookies.get(SESSION_COOKIE, ""))
        )
    ).one()
    return user, session


def verification_remaining(session: Session, now: datetime) -> int:
    if session.reverified_at is None or session.reverified_at > now:
        return 0
    return max(
        0, min(600, int((session.reverified_at + timedelta(minutes=10) - now).total_seconds()))
    )


def recent(auth: AuthService, session: Session) -> None:
    now = auth.clock()
    if session.reverified_at is None or not (
        now - timedelta(minutes=10) < session.reverified_at <= now
    ):
        raise AuthError(403, "reverification_required")


def clear_cookies(response: Response) -> Response:
    for name in (SESSION_COOKIE, CHALLENGE_COOKIE):
        response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")
    return response


@router.post("/auth/reverify/challenges", status_code=202, response_model=ChallengeResult)
def request_reverification(value: ReverifyInput, request: Request, owner: Owner) -> JSONResponse:
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        user, _ = owned(db, auth, request, owner, write=True)
        email = user.email
    identifier, browser = auth.request_code(
        ChallengeInput(email=email, language=value.language), request, reverify=True
    )
    response = JSONResponse(
        status_code=202, content=ChallengeResult(challenge_id=identifier).model_dump(mode="json")
    )
    set_cookie(response, CHALLENGE_COOKIE, browser, 600)
    return response


@router.post("/auth/reverify", response_model=VerifiedResult)
def verify_again(value: VerifyInput, request: Request, owner: Owner) -> JSONResponse:
    auth = service(request)
    # Check expected owner before code consumption; the service rechecks the active session.
    with DbSession(auth.engine) as db, db.begin():
        owned(db, auth, request, owner, write=True)
    _, token = auth.verify(value, request, reverify=True)
    with DbSession(auth.engine) as db:
        current = db.scalar(
            select(Session).where(
                Session.token_digest == token_digest(token), Session.user_id == owner
            )
        )
        if current is None:
            raise AuthError(401, "unauthenticated")
        assert current.reverified_at
        result = VerifiedResult(
            reverified_until=current.reverified_at + timedelta(minutes=10),
            reverified_for=verification_remaining(current, auth.clock()),
        )
    response = JSONResponse(content=result.model_dump(mode="json"))
    set_cookie(response, SESSION_COOKIE, token, 30 * 86400)
    response.delete_cookie(CHALLENGE_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response


@router.get("/sessions", response_model=SessionList)
def sessions(request: Request, owner: Owner) -> SessionList:
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        _, current = owned(db, auth, request, owner)
        rows = db.scalars(
            select(Session)
            .where(
                Session.user_id == owner,
                Session.revoked_at.is_(None),
                Session.expires_at > auth.clock(),
                Session.absolute_expires_at > auth.clock(),
            )
            .order_by(Session.created_at.desc(), Session.id)
        )
        remaining = verification_remaining(current, auth.clock())
        return SessionList(
            user_id=owner,
            reverified_for=remaining,
            reverified_until=(current.reverified_at + timedelta(minutes=10))
            if remaining and current.reverified_at
            else None,
            sessions=[
                SessionItem(
                    id=row.id,
                    created_at=row.created_at,
                    last_seen_at=row.last_seen_at,
                    expires_at=row.expires_at,
                    current=row.id == current.id,
                )
                for row in rows
            ],
        )


@router.delete("/sessions/{identifier}", status_code=204)
def revoke_session(identifier: uuid.UUID, request: Request, owner: Owner) -> Response:
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        _, current = owned(db, auth, request, owner, write=True)
        target = db.scalar(
            select(Session).where(Session.id == identifier, Session.user_id == owner)
        )
        if target is None:
            raise AuthError(404, "not_found")
        revoke(db, [target.id], auth.clock())
        current_revoked = identifier == current.id
    response = Response(status_code=204)
    return clear_cookies(response) if current_revoked else response


@router.delete("/sessions", status_code=204)
def revoke_all(request: Request, owner: Owner) -> Response:
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        owned(db, auth, request, owner, write=True)
        identifiers = list(db.scalars(select(Session.id).where(Session.user_id == owner)))
        revoke(db, identifiers, auth.clock())
    return clear_cookies(Response(status_code=204))


@router.get("/account/export", response_model=AccountExport)
def export_account(request: Request, owner: Owner) -> JSONResponse:
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        user, current = owned(db, auth, request, owner)
        recent(auth, current)
        pref = db.get(ReminderPreference, owner)
        # Explicit whitelist excludes credential digests, outbox bodies and unsubscribe tokens.
        preferences = (
            None
            if pref is None
            else {
                "enabled": pref.enabled,
                "frequency": pref.frequency,
                "timezone": pref.timezone,
                "send_time": pref.send_time,
                "weekday": pref.weekday,
                "language": pref.language,
                "include_phrase": pref.include_phrase,
                "consent_at": pref.consent_at.isoformat() if pref.consent_at else None,
                "notice_version": pref.notice_version,
            }
        )
        result = {
            "version": 1,
            "exported_at": auth.clock().isoformat(),
            "account": {
                "id": str(user.id),
                "email": user.email,
                "created_at": user.created_at.isoformat(),
                "verified_at": user.verified_at.isoformat(),
            },
            "calendar": snapshot(user.id, db.get(Profile, user.id)).model_dump(mode="json"),
            "reminder_preferences": preferences,
        }
    return JSONResponse(
        content=AccountExport.model_validate(result).model_dump(mode="json"),
        headers={"Content-Disposition": 'attachment; filename="aion-account.json"'},
    )


@router.delete("/account", status_code=204)
def delete_account(value: DeleteInput, request: Request, owner: Owner) -> Response:
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        user, current = owned(db, auth, request, owner, write=True)
        recent(auth, current)
        # session_in(write=True) holds the shared delivery barrier through commit.
        stop(db, user.id)
        db.add(
            DeletionLedger(
                user_id=user.id,
                email_digest=auth.keys.digest("suppression", user.email),
                deleted_at=auth.clock(),
            )
        )
        # Login challenges have no owner FK. Remove them by the verified canonical address too.
        db.execute(delete(EmailChallenge).where(EmailChallenge.email == user.email))
        db.delete(user)
    return clear_cookies(Response(status_code=204))
