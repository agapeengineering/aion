"""Explicit online enrollment and scanner-safe, capability-scoped unsubscribe."""

import re
import secrets
import uuid
from datetime import datetime
from html import escape
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import case, select, update
from sqlalchemy.orm import Session as DbSession

from aion.auth import AuthError, AuthService, lock_email, service, token_digest
from aion.models import EmailSuppression, Profile, ReminderMail, ReminderPreference, User
from aion.phrases import weekly_collection
from aion.profiles import Match, Owner
from aion.schedules import next_occurrence

NOTICE = "2026-10-18"
router = APIRouter(prefix="/api/v1")


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool
    frequency: Literal["daily", "weekly"] = "weekly"
    timezone: str = Field(max_length=64)
    send_time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    weekday: int = Field(ge=0, le=6, strict=True)
    language: Literal["en", "es"]
    include_phrase: StrictBool = True
    consent: StrictBool = False
    notice_version: Literal["2026-10-18"] = "2026-10-18"

    @model_validator(mode="after")
    def zone(self) -> Preferences:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError, ValueError:
            raise ValueError("Unknown timezone") from None
        return self


class ReminderSnapshot(BaseModel):
    user_id: uuid.UUID
    revision: int
    preferences: Preferences | None
    next_due_at: datetime | None
    suppressed: bool
    available: bool
    phrase_available: bool


def stop(db: DbSession, user_id: uuid.UUID) -> None:
    pref = db.get(ReminderPreference, user_id)
    if pref and pref.enabled:
        pref.enabled, pref.next_due_at, pref.revision = False, None, pref.revision + 1
    db.execute(
        update(ReminderMail)
        .where(ReminderMail.user_id == user_id, ReminderMail.status == "pending")
        .values(
            status=case((ReminderMail.acceptance_unknown, "uncertain"), else_="cancelled"),
            encrypted_payload=None,
            lease_until=None,
        )
    )


def state(db: DbSession, auth: AuthService, user: User) -> ReminderSnapshot:
    p = db.get(ReminderPreference, user.id)
    blocked = db.get(EmailSuppression, auth.keys.digest("suppression", user.email)) is not None
    due = p.next_due_at if p else None
    # Availability refers to the next scheduled week, never the unapproved research draft.
    collection = weekly_collection()
    day = due.astimezone(ZoneInfo(p.timezone)).date() if due and p else auth.clock().date()
    return ReminderSnapshot(
        user_id=user.id,
        revision=p.revision if p else 0,
        preferences=Preferences.model_validate(
            {
                "enabled": p.enabled,
                "frequency": p.frequency,
                "timezone": p.timezone,
                "send_time": p.send_time,
                "weekday": p.weekday,
                "language": p.language,
                "include_phrase": p.include_phrase,
                "notice_version": p.notice_version,
            }
        )
        if p
        else None,
        next_due_at=due,
        suppressed=blocked,
        available=auth.settings.reminders_enabled,
        phrase_available=collection.for_date(day) is not None,
    )


def owned(
    db: DbSession, auth: AuthService, request: Request, owner: uuid.UUID, write: bool = False
) -> User:
    identity, _ = auth.session_in(db, request, write=write)
    if identity.id != owner:
        raise AuthError(409, "account_changed")
    user = db.get(User, identity.id)
    assert user
    if write:
        lock_email(db, user.email, auth.keys)
        db.refresh(user, with_for_update=True)
    return user


@router.get("/reminder-preferences", response_model=ReminderSnapshot)
def get_preferences(request: Request, owner: Owner) -> ReminderSnapshot:
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        return state(db, auth, owned(db, auth, request, owner))


@router.put("/reminder-preferences", response_model=ReminderSnapshot)
def put_preferences(
    value: Preferences, request: Request, owner: Owner, match: Match
) -> JSONResponse:
    auth = service(request)
    found = re.fullmatch(r'"reminders-([0-9]{1,16})"', match)
    if not found:
        raise AuthError(422, "invalid_revision")
    with DbSession(auth.engine) as db, db.begin():
        user = owned(db, auth, request, owner, True)
        pref = db.get(ReminderPreference, user.id)
        if int(found[1]) != (pref.revision if pref else 0):
            return JSONResponse(
                status_code=409,
                content={
                    "error": {"code": "reminder_conflict"},
                    "current": state(db, auth, user).model_dump(mode="json"),
                },
            )
        if value.enabled:
            if not auth.settings.reminders_enabled:
                raise AuthError(503, "reminders_unavailable")
            profile = db.get(Profile, user.id)
            if not profile or not profile.birth_date:
                raise AuthError(409, "profile_required")
            if db.get(EmailSuppression, auth.keys.digest("suppression", user.email)):
                raise AuthError(409, "delivery_suppressed")
            if not value.consent:
                raise AuthError(422, "consent_required")
        was_enabled = pref.enabled if pref else False
        if pref is None:
            token = secrets.token_urlsafe(32)
            pref = ReminderPreference(
                user_id=user.id,
                revision=0,
                unsubscribe_digest=token_digest(token),
                encrypted_token=auth.keys.seal.encrypt(token.encode()),
            )
            db.add(pref)
        pref.revision += 1
        for key in (
            "enabled",
            "frequency",
            "timezone",
            "send_time",
            "weekday",
            "language",
            "include_phrase",
            "notice_version",
        ):
            setattr(pref, key, getattr(value, key))
        if value.enabled:
            pref.consent_at = auth.clock()
            pref.next_due_at = next_occurrence(
                auth.clock(), value.timezone, value.send_time, value.frequency, value.weekday
            )
            if not was_enabled:
                token = secrets.token_urlsafe(32)
                pref.unsubscribe_digest = token_digest(token)
                pref.encrypted_token = auth.keys.seal.encrypt(token.encode())
            if (
                value.include_phrase
                and weekly_collection().for_date(
                    pref.next_due_at.astimezone(ZoneInfo(value.timezone)).date()
                )
                is None
            ):
                raise AuthError(409, "phrase_not_ready")
        else:
            pref.next_due_at = None
        db.execute(
            update(ReminderMail)
            .where(ReminderMail.user_id == user.id, ReminderMail.status == "pending")
            .values(
                status=case((ReminderMail.acceptance_unknown, "uncertain"), else_="cancelled"),
                encrypted_payload=None,
                lease_until=None,
            )
        )
        db.flush()
        result = state(db, auth, user)
        return JSONResponse(
            content=result.model_dump(mode="json"), headers={"ETag": f'"reminders-{pref.revision}"'}
        )


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_page(token: str, request: Request) -> HTMLResponse:
    # GET never changes consent: inbox scanners follow these links.
    if len(token) != 43:
        raise AuthError(404, "not_found")
    auth = service(request)
    with DbSession(auth.engine) as db:
        pref = db.scalar(
            select(ReminderPreference).where(
                ReminderPreference.unsubscribe_digest == token_digest(token)
            )
        )
        if not pref:
            raise AuthError(404, "not_found")
        es = pref.language == "es"
    title = "Cancelar recordatorios" if es else "Unsubscribe from reminders"
    message = (
        "Confirma para dejar de recibir recordatorios de Aion. Tu cuenta y calendario se conservan."
        if es
        else "Confirm to stop Aion reminders. Your account and calendar are preserved."
    )
    return HTMLResponse(
        f'''<!doctype html>
<html lang="{"es" if es else "en"}">
<head>
<meta name="viewport" content="width=device-width">
<title>Aion — {title}</title>
</head>
<body
style="background:#faf6ee;color:#1a1a1a;font:16px/1.6 Arial;padding:24px;">
<main
style="max-width:480px;margin:60px auto;">
<p>aion.</p>
<h1>{title}</h1>
<p>{message}</p>
<form method="post" action="{escape(request.url.path)}">
<button style="padding:14px 20px;">{title}</button>
</form>
</main>
</body>
</html>''',
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; "
                "form-action 'self'; frame-ancestors 'none'"
            )
        },
    )


@router.post("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, request: Request) -> HTMLResponse:
    auth = service(request)
    if len(token) != 43:
        raise AuthError(404, "not_found")
    # Look up owner first, then acquire the same per-email dispatch barrier as workers.
    with DbSession(auth.engine) as db:
        pref = db.scalar(
            select(ReminderPreference).where(
                ReminderPreference.unsubscribe_digest == token_digest(token)
            )
        )
        user = db.get(User, pref.user_id) if pref else None
        if not pref or not user:
            raise AuthError(404, "not_found")
        email, owner = user.email, user.id
    with DbSession(auth.engine) as db, db.begin():
        lock_email(db, email, auth.keys)
        db.get(User, owner, with_for_update=True)
        pref = db.get(ReminderPreference, owner)
        if not pref or pref.unsubscribe_digest != token_digest(token):
            raise AuthError(404, "not_found")
        es = pref.language == "es"
        stop(db, owner)
    message = "Los recordatorios están desactivados." if es else "Reminders are now off."
    return HTMLResponse(
        f'''<!doctype html>
<html lang="{"es" if es else "en"}">
<head>
<title>Aion</title>
<meta name="viewport" content="width=device-width">
</head>
<body>
<main>
<h1>{message}</h1>
</main>
</body>
</html>'''
    )
