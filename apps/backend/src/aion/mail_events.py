"""Verified raw-body Resend events, minimal metadata, sticky delivery suppression."""

from email.utils import parseaddr
from typing import Any

from email_validator import EmailNotValidError
from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession
from starlette.concurrency import run_in_threadpool
from svix.webhooks import Webhook, WebhookVerificationError

from aion.auth import AuthError, AuthService, canonical_email, lock_email, service
from aion.models import EmailEvent, EmailSuppression, ReminderMail, User, VerificationMail
from aion.reminders import stop

router = APIRouter(prefix="/api/v1")
KINDS = {
    "email.sent",
    "email.delivered",
    "email.bounced",
    "email.complained",
    "email.suppressed",
    "email.failed",
    "email.delivery_delayed",
}


@router.post("/webhooks/resend", status_code=204)
async def resend_event(request: Request) -> Response:
    auth = service(request)
    path = auth.settings.resend_webhook_secret_file
    if path is None:
        raise AuthError(503, "webhook_unavailable")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 16384:
            raise AuthError(413, "request_too_large")
    try:
        verified: Any = Webhook(path.read_text().strip()).verify(bytes(data), dict(request.headers))
    except OSError, ValueError, WebhookVerificationError, UnicodeError:
        raise AuthError(400, "invalid_webhook") from None
    key = request.headers.get("svix-id", "")
    if not isinstance(verified, dict) or not key or len(key) > 128:
        raise AuthError(400, "invalid_webhook")
    kind, details = verified.get("type"), verified.get("data")
    if not isinstance(kind, str):
        raise AuthError(400, "invalid_webhook")
    if kind not in KINDS:
        return Response(status_code=204)
    if not isinstance(details, dict) or not isinstance(details.get("email_id"), str):
        raise AuthError(400, "invalid_webhook")
    provider_id = details["email_id"]
    if len(provider_id) > 64:
        raise AuthError(400, "invalid_webhook")
    recipients = details.get("to", [])
    if (
        not isinstance(recipients, list)
        or len(recipients) > 20
        or not all(isinstance(x, str) and len(x) <= 254 for x in recipients)
    ):
        raise AuthError(400, "invalid_webhook")
    sender = parseaddr(str(details.get("from", "")))[1].lower()
    return await run_in_threadpool(apply_event, auth, key, kind, provider_id, sender, recipients)


def apply_event(
    auth: AuthService, key: str, kind: str, provider_id: str, sender: str, recipients: list[str]
) -> Response:
    # Ignore other products using the same provider team; accept our signed sender or known ID.
    with DbSession(auth.engine) as db:
        known = db.scalar(
            select(ReminderMail.id).where(ReminderMail.provider_message_id == provider_id)
        ) or db.scalar(
            select(VerificationMail.id).where(VerificationMail.provider_message_id == provider_id)
        )
    ours = sender == parseaddr(auth.settings.email_from)[1].lower()
    if not known and not ours:
        return Response(status_code=204)
    suppress = kind in {"email.bounced", "email.complained", "email.suppressed"}
    emails = sorted({value.strip().lower() for value in recipients})
    if suppress:
        try:
            emails = sorted({canonical_email(value) for value in recipients})
        except EmailNotValidError:
            raise AuthError(400, "invalid_webhook") from None
        if not emails:
            raise AuthError(400, "invalid_webhook")
    now = auth.clock()
    with DbSession(auth.engine) as db, db.begin():
        # Stable recipient order prevents deadlocks on provider events with multiple recipients.
        for email in emails:
            lock_email(db, email, auth.keys)
        inserted = db.execute(
            insert(EmailEvent)
            .values(id=key, provider_message_id=provider_id, kind=kind, received_at=now)
            .on_conflict_do_nothing(index_elements=[EmailEvent.id])
            .returning(EmailEvent.id)
        ).scalar_one_or_none()
        if inserted is None:
            return Response(status_code=204)
        job = db.scalar(
            select(ReminderMail)
            .where(ReminderMail.provider_message_id == provider_id)
            .with_for_update()
        )
        if job:
            priority = {
                None: 0,
                "sent": 1,
                "delivery_delayed": 2,
                "delivered": 3,
                "failed": 4,
                "suppressed": 5,
                "bounced": 6,
                "complained": 7,
            }
            status = kind.removeprefix("email.")
            if priority[status] > priority[job.delivery_status]:
                job.delivery_status = status
        if suppress:
            reason = kind.removeprefix("email.")
            new_markers = []
            for email in emails:
                digest = auth.keys.digest("suppression", email)
                if not db.get(EmailSuppression, digest):
                    db.add(EmailSuppression(email_digest=digest, reason=reason, created_at=now))
                    new_markers.append(digest)
                user = db.scalar(select(User).where(User.email == email).with_for_update())
                if user:
                    stop(db, user.id)
                # Pending sign-in sends are also suppressed at dispatch, under the same lock.
            if auth.journal is not None and new_markers:
                db.flush()
                auth.journal.suppression(new_markers, reason, now)
    return Response(status_code=204)
