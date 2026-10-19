"""Browser-bound email codes and opaque sessions. No provider or public deployment implied."""

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, case, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from aion.config import Settings
from aion.mail_content import verification_payload
from aion.models import EmailChallenge, Profile, RateLimitBucket, Session, User, VerificationMail
from aion.session_revocation import revoke

SESSION_COOKIE = "__Host-aion_session"
CHALLENGE_COOKIE = "__Host-aion_challenge"


class AuthError(Exception):
    def __init__(self, status: int, code: str, retry_after: int | None = None):
        self.status = status
        self.code = code
        self.retry_after = retry_after


class AuthKeys:
    def __init__(self, settings: Settings):
        try:
            if settings.auth_secrets_file is None:
                raise ValueError
            value = json.loads(settings.auth_secrets_file.read_text())
            self.mac = base64.urlsafe_b64decode(value["mac"])
            self.csrf = base64.urlsafe_b64decode(value["csrf"])
            if len(self.mac) != 32 or len(self.csrf) != 32 or self.mac == self.csrf:
                raise ValueError
            seal = base64.urlsafe_b64decode(value["seal"])
            if len(seal) != 32 or seal in {self.mac, self.csrf}:
                raise ValueError
            self.seal = Fernet(value["seal"].encode())
        except OSError, ValueError, KeyError, TypeError:
            raise ValueError("Authentication key configuration is unavailable or invalid") from None

    def digest(self, namespace: str, value: str) -> bytes:
        return hmac.digest(self.mac, (namespace + "\0" + value).encode(), "sha256")

    def csrf_token(self, token: str) -> str:
        return hmac.digest(self.csrf, token.encode(), "sha256").hex()


def token_digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def lock_email(db: DbSession, email: str, keys: AuthKeys) -> None:
    # A transaction-scoped lock serializes send/verify/delivery for one address.
    key = int.from_bytes(keys.digest("email_lock", email)[:8], signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def budget(
    db: DbSession, keys: AuthKeys, kind: str, subject: str, limit: int, now: datetime
) -> bool:
    start = now.replace(minute=0, second=0, microsecond=0)
    stmt = insert(RateLimitBucket).values(
        namespace=kind,
        subject_digest=keys.digest(kind, subject),
        window_start=start,
        attempts=1,
        expires_at=start + timedelta(hours=1),
    )
    count = db.execute(
        stmt.on_conflict_do_update(
            index_elements=["namespace", "subject_digest", "window_start"],
            set_={"attempts": RateLimitBucket.attempts + 1},
        ).returning(RateLimitBucket.attempts)
    ).scalar_one()
    return count <= limit


class ChallengeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    language: Literal["en", "es"] = "en"
    purpose: Literal["login"] = "login"


class VerifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^[0-9]{8}$")


class ChallengeResult(BaseModel):
    challenge_id: uuid.UUID
    expires_in: int = 600
    resend_after: int = 60


class Identity(BaseModel):
    id: uuid.UUID
    email: str


class LoginResult(BaseModel):
    user: Identity
    has_profile: bool = False


class CsrfResult(BaseModel):
    csrf_token: str


class AuthService:
    def __init__(self, engine: Engine, settings: Settings):
        origin = urlsplit(settings.auth_origin)
        if (
            origin.scheme != "https"
            or not origin.netloc
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username is not None
        ):
            raise ValueError("Authentication requires an exact HTTPS origin")
        if settings.local_mail_capture and origin.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Local mail capture requires a loopback HTTPS origin")
        self.settings = settings
        self.engine = engine
        self.origin = settings.auth_origin
        self.keys = AuthKeys(settings)
        self.clock: Callable[[], datetime] = utc_now

    def check_origin(self, request: Request) -> None:
        if request.headers.get("origin") != self.origin:
            raise AuthError(403, "origin_failed")

    def request_code(
        self, value: ChallengeInput, request: Request, *, reverify: bool = False
    ) -> tuple[uuid.UUID, str]:
        self.check_origin(request)
        try:
            address = validate_email(
                value.email.strip(),
                check_deliverability=False,
                allow_smtputf8=False,
                test_environment=True,
            ).ascii_email
            if address is None:
                raise EmailNotValidError("Unsupported address")
            email = address.lower()
        except EmailNotValidError:
            raise AuthError(422, "invalid_email") from None
        if self.settings.resend_enabled and email not in self.settings.resend_allowed_recipients:
            raise AuthError(422, "email_not_allowed")
        purpose = "reverify" if reverify else "login"
        now = self.clock()
        error: AuthError | None = None
        challenge_id, browser = uuid.uuid4(), secrets.token_urlsafe(32)
        ip = request.client.host if request.client else "unknown"
        with DbSession(self.engine) as db, db.begin():
            lock_email(db, email, self.keys)
            bound_session = None
            if reverify:
                identity, _ = self.session_in(db, request, write=True)
                if identity.email != email:
                    raise AuthError(409, "account_changed")
                bound_session = db.scalars(
                    select(Session).where(
                        Session.token_digest
                        == token_digest(request.cookies.get(SESSION_COOKIE, ""))
                    )
                ).one()
            if not budget(db, self.keys, "send_ip", ip, 20, now):
                error = AuthError(429, "rate_limited", 3600)
            else:
                previous = db.scalars(
                    select(EmailChallenge)
                    .where(EmailChallenge.email == email, EmailChallenge.purpose == purpose)
                    .order_by(EmailChallenge.created_at.desc())
                    .limit(1)
                ).first()
                cooldown = (
                    0
                    if previous is None
                    else (60 - int((now - previous.created_at).total_seconds()))
                )
                if cooldown > 0:
                    error = AuthError(429, "rate_limited", cooldown)
                elif not budget(db, self.keys, "send_email", email, 3, now):
                    error = AuthError(429, "rate_limited", 3600)
                else:
                    old_ids = select(EmailChallenge.id).where(
                        EmailChallenge.email == email, EmailChallenge.purpose == purpose
                    )
                    db.execute(
                        update(VerificationMail)
                        .where(
                            VerificationMail.challenge_id.in_(old_ids),
                            VerificationMail.status == "pending",
                        )
                        .values(
                            status=case(
                                (VerificationMail.acceptance_unknown, "uncertain"),
                                else_="cancelled",
                            ),
                            encrypted_payload=None,
                        )
                    )
                    db.execute(
                        update(EmailChallenge)
                        .where(
                            EmailChallenge.email == email,
                            EmailChallenge.purpose == purpose,
                            EmailChallenge.consumed_at.is_(None),
                            EmailChallenge.invalidated_at.is_(None),
                        )
                        .values(invalidated_at=now)
                    )
                    code = f"{secrets.randbelow(100_000_000):08d}"
                    expires = now + timedelta(minutes=10)
                    db.add(
                        EmailChallenge(
                            id=challenge_id,
                            email=email,
                            purpose=purpose,
                            user_id=bound_session.user_id if bound_session else None,
                            session_id=bound_session.id if bound_session else None,
                            code_digest=self.keys.digest("code", f"{challenge_id}:{code}"),
                            browser_digest=token_digest(browser),
                            attempts=0,
                            created_at=now,
                            expires_at=expires,
                        )
                    )
                    db.flush()
                    content: dict[str, object] = {
                        "email": email,
                        "code": code,
                        "language": value.language,
                        "purpose": purpose,
                    }
                    if self.settings.resend_enabled:
                        content["resend"] = verification_payload(
                            email,
                            code,
                            value.language,
                            self.settings.email_from,
                            self.settings.email_reply_to,
                            purpose=purpose,
                        )
                    payload = json.dumps(content)
                    db.add(
                        VerificationMail(
                            challenge_id=challenge_id,
                            encrypted_payload=self.keys.seal.encrypt(payload.encode()),
                            status="pending",
                            attempts=0,
                            next_attempt_at=now,
                            expires_at=expires,
                        )
                    )
        # Failures are raised after transaction exit so abuse counters are not rolled back.
        if error:
            raise error
        return challenge_id, browser

    def verify(
        self, value: VerifyInput, request: Request, *, reverify: bool = False
    ) -> tuple[Identity, str]:
        self.check_origin(request)
        now = self.clock()
        error: AuthError | None = AuthError(400, "verification_failed")
        identity: Identity | None = None
        token = request.cookies.get(SESSION_COOKIE, "") if reverify else secrets.token_urlsafe(32)
        ip = request.client.host if request.client else "unknown"
        browser = request.cookies.get(CHALLENGE_COOKIE, "")
        with DbSession(self.engine) as db, db.begin():
            bound_session = None
            if reverify:
                self.session_in(db, request, write=True)
                bound_session = db.scalars(
                    select(Session).where(Session.token_digest == token_digest(token))
                ).one()
            if not budget(db, self.keys, "verify_ip", ip, 100, now):
                error = AuthError(429, "rate_limited", 3600)
            else:
                challenge = db.get(EmailChallenge, value.challenge_id)
                if (
                    reverify
                    and challenge is not None
                    and (
                        bound_session is None
                        or challenge.session_id != bound_session.id
                        or challenge.user_id != bound_session.user_id
                    )
                ):
                    challenge = None
                if challenge is not None:
                    lock_email(db, challenge.email, self.keys)
                    db.refresh(challenge)
                    valid = (
                        challenge.purpose == ("reverify" if reverify else "login")
                        and (
                            not reverify
                            or (
                                bound_session is not None
                                and challenge.session_id == bound_session.id
                                and challenge.user_id == bound_session.user_id
                            )
                        )
                        and challenge.consumed_at is None
                        and challenge.invalidated_at is None
                        and challenge.expires_at > now
                        and challenge.attempts < 5
                        and hmac.compare_digest(challenge.browser_digest, token_digest(browser))
                    )
                    if valid:
                        if not budget(db, self.keys, "verify_email", challenge.email, 15, now):
                            error = AuthError(429, "rate_limited", 3600)
                        else:
                            challenge.attempts += 1
                            digest = self.keys.digest("code", f"{value.challenge_id}:{value.code}")
                            if hmac.compare_digest(digest, challenge.code_digest):
                                user = db.scalars(
                                    select(User).where(User.email == challenge.email)
                                ).first()
                                if user is None and not reverify:
                                    user = User(
                                        email=challenge.email, created_at=now, verified_at=now
                                    )
                                    db.add(user)
                                    db.flush()
                                challenge.consumed_at = now
                                db.execute(
                                    update(VerificationMail)
                                    .where(
                                        VerificationMail.challenge_id == challenge.id,
                                        VerificationMail.status == "pending",
                                    )
                                    .values(
                                        status=case(
                                            (VerificationMail.acceptance_unknown, "uncertain"),
                                            else_="cancelled",
                                        ),
                                        encrypted_payload=None,
                                    )
                                )
                                assert user is not None
                                if reverify:
                                    assert bound_session is not None
                                    bound_session.reverified_at = now
                                    token = secrets.token_urlsafe(32)
                                    bound_session.token_digest = token_digest(token)
                                    bound_session.csrf_digest = token_digest(
                                        self.keys.csrf_token(token)
                                    )
                                else:
                                    previous = request.cookies.get(SESSION_COOKIE)
                                    if previous:
                                        db.execute(
                                            update(Session)
                                            .where(
                                                Session.token_digest == token_digest(previous),
                                                Session.revoked_at.is_(None),
                                            )
                                            .values(revoked_at=now)
                                        )
                                    db.add(
                                        Session(
                                            user_id=user.id,
                                            token_digest=token_digest(token),
                                            csrf_digest=token_digest(self.keys.csrf_token(token)),
                                            created_at=now,
                                            last_seen_at=now,
                                            expires_at=now + timedelta(days=7),
                                            absolute_expires_at=now + timedelta(days=30),
                                        )
                                    )
                                identity, error = Identity(id=user.id, email=user.email), None
        if error:
            raise error
        assert identity is not None
        return identity, token

    def session(self, request: Request, *, logout: bool = False) -> tuple[Identity, str]:
        with DbSession(self.engine) as db, db.begin():
            return self.session_in(db, request, logout=logout)

    def session_in(
        self, db: DbSession, request: Request, *, write: bool = False, logout: bool = False
    ) -> tuple[Identity, str]:
        token = request.cookies.get(SESSION_COOKIE, "")
        now = self.clock()
        if write or logout:
            address = db.scalar(
                select(User.email)
                .join(Session, Session.user_id == User.id)
                .where(Session.token_digest == token_digest(token))
            )
            if address:
                lock_email(db, address, self.keys)
        session = db.scalars(
            select(Session).where(Session.token_digest == token_digest(token)).with_for_update()
        ).first()
        if (
            session is None
            or session.revoked_at is not None
            or session.expires_at <= now
            or session.absolute_expires_at <= now
        ):
            raise AuthError(401, "unauthenticated")
        if write or logout:
            self.check_origin(request)
            nonce = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(session.csrf_digest, token_digest(nonce)):
                raise AuthError(403, "csrf_failed")
        if logout:
            revoke(db, [session.id], now)
        else:
            session.last_seen_at = now
            session.expires_at = min(now + timedelta(days=7), session.absolute_expires_at)
        user = db.get(User, session.user_id)
        assert user is not None
        return Identity(id=user.id, email=user.email), self.keys.csrf_token(token)


def service(request: Request) -> AuthService:
    auth: AuthService | None = request.app.state.auth
    if auth is None:
        raise AuthError(503, "auth_unavailable")
    return auth


def set_cookie(response: JSONResponse, name: str, value: str, age: int) -> None:
    response.set_cookie(
        name, value, max_age=age, secure=True, httponly=True, samesite="lax", path="/"
    )


router = APIRouter(prefix="/api/v1")


@router.post("/auth/challenges", status_code=202, response_model=ChallengeResult)
def challenge_endpoint(value: ChallengeInput, request: Request) -> JSONResponse:
    challenge_id, browser = service(request).request_code(value, request)
    response = JSONResponse(
        status_code=202, content=ChallengeResult(challenge_id=challenge_id).model_dump(mode="json")
    )
    set_cookie(response, CHALLENGE_COOKIE, browser, 600)
    return response


@router.post("/auth/verify", response_model=LoginResult)
def verify_endpoint(value: VerifyInput, request: Request) -> JSONResponse:
    identity, token = service(request).verify(value, request)
    with DbSession(service(request).engine) as db:
        profile = db.get(Profile, identity.id)
        present = profile is not None and profile.birth_date is not None
    response = JSONResponse(
        content=LoginResult(user=identity, has_profile=present).model_dump(mode="json")
    )
    set_cookie(response, SESSION_COOKIE, token, 30 * 86400)
    response.delete_cookie(CHALLENGE_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response


@router.get("/me", response_model=Identity)
def me_endpoint(request: Request) -> Identity:
    return service(request).session(request)[0]


@router.get("/auth/csrf", response_model=CsrfResult)
def csrf_endpoint(request: Request) -> CsrfResult:
    return CsrfResult(csrf_token=service(request).session(request)[1])


@router.post("/auth/logout", status_code=204)
def logout_endpoint(request: Request) -> Response:
    service(request).session(request, logout=True)
    response = Response(status_code=204)
    for name in (SESSION_COOKIE, CHALLENGE_COOKIE):
        response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")
    return response
