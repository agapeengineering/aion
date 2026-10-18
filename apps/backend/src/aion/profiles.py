"""Session-owned profiles with monotonic reset markers and idempotent conditional writes."""

import hmac
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator
from sqlalchemy.orm import Session as DbSession

from aion.auth import AuthError, service
from aion.calendar import calculate, parse_date
from aion.models import Profile, ProfileMutation, User


class ProfileData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(ge=1, le=1)
    birthDate: StrictStr
    lifespanYears: StrictInt = Field(gt=0, le=9007199254740991)
    language: Literal["en", "es"]
    unit: Literal["years", "months", "weeks", "days", "hours", "minutes", "seconds"]
    hideRemaining: StrictBool

    @model_validator(mode="after")
    def calendar_range(self) -> Self:
        # Devices may be a calendar day ahead of UTC; the client still validates
        # against its exact local clock. Never reinterpret a date as a timestamp.
        reference = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
        if "error" in calculate(
            {
                "birthDate": self.birthDate,
                "lifespanYears": self.lifespanYears,
                "clock": {"date": reference, "time": "00:00:00"},
            }
        ):
            raise ValueError("Invalid calendar inputs")
        return self


class ProfileSnapshot(BaseModel):
    user_id: uuid.UUID
    revision: int
    profile: ProfileData | None


class ProfileConflict(BaseModel):
    error: dict[str, str]
    current: ProfileSnapshot


def snapshot(user_id: uuid.UUID, profile: Profile | None) -> ProfileSnapshot:
    data = None
    if profile is not None and profile.birth_date is not None:
        data = ProfileData.model_validate(
            {
                "version": 1,
                "birthDate": profile.birth_date.isoformat(),
                "lifespanYears": profile.lifespan_years,
                "language": profile.language,
                "unit": profile.unit,
                "hideRemaining": profile.hide_remaining,
            }
        )
    return ProfileSnapshot(
        user_id=user_id, revision=profile.revision if profile else 0, profile=data
    )


def response(value: ProfileSnapshot, *, conflict: str | None = None) -> JSONResponse:
    content = value.model_dump(mode="json")
    if conflict:
        content = {"error": {"code": conflict}, "current": content}
    return JSONResponse(
        status_code=409 if conflict else 200,
        content=content,
        headers={"ETag": f'"profile-{value.revision}"'},
    )


router = APIRouter(prefix="/api/v1")
Owner = Annotated[uuid.UUID, Header(alias="X-Aion-Account")]
Match = Annotated[str, Header(alias="If-Match")]
Operation = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]


@router.get("/profile", response_model=ProfileSnapshot)
def get_profile(request: Request, owner: Owner) -> JSONResponse:
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        identity, _ = auth.session_in(db, request)
        if identity.id != owner:
            raise AuthError(409, "account_changed")
        return response(snapshot(identity.id, db.get(Profile, identity.id)))


def mutate(
    request: Request, owner: uuid.UUID, match: str, operation: uuid.UUID, value: ProfileData | None
) -> JSONResponse:
    found = re.fullmatch(r'"profile-([0-9]+)"', match)
    if not found or len(found[1]) > 16:
        raise AuthError(422, "invalid_revision")
    base = int(found[1])
    auth = service(request)
    with DbSession(auth.engine) as db, db.begin():
        identity, _ = auth.session_in(db, request, write=True)
        if identity.id != owner:
            raise AuthError(409, "account_changed")
        # All sessions of an owner serialize here, including an initial create.
        db.get(User, identity.id, with_for_update=True)
        row = db.get(Profile, identity.id)
        current = snapshot(identity.id, row)
        canonical = json.dumps(
            {"base": base, "value": value.model_dump() if value else None},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = auth.keys.digest("profile_mutation", canonical)
        previous = db.get(ProfileMutation, (identity.id, operation))
        if previous:
            if not hmac.compare_digest(previous.payload_digest, digest):
                return response(current, conflict="idempotency_conflict")
            if previous.result_revision != current.revision:
                return response(current, conflict="profile_conflict")
            return response(current)
        if base != current.revision:
            return response(current, conflict="profile_conflict")
        if current.revision >= 9007199254740990:
            raise AuthError(409, "revision_exhausted")
        if row is None:
            row = Profile(user_id=identity.id, revision=1)
            db.add(row)
        else:
            row.revision += 1
        row.birth_date = parse_date(value.birthDate) if value else None
        row.lifespan_years = value.lifespanYears if value else None
        row.language = value.language if value else None
        row.unit = value.unit if value else None
        row.hide_remaining = value.hideRemaining if value else None
        db.add(
            ProfileMutation(
                user_id=identity.id,
                operation_id=operation,
                payload_digest=digest,
                result_revision=row.revision,
                created_at=auth.clock(),
            )
        )
        db.flush()
        return response(snapshot(identity.id, row))


@router.put("/profile", response_model=ProfileSnapshot, responses={409: {"model": ProfileConflict}})
def put_profile(
    value: ProfileData, request: Request, owner: Owner, match: Match, operation: Operation
) -> JSONResponse:
    return mutate(request, owner, match, operation, value)


@router.delete(
    "/profile", response_model=ProfileSnapshot, responses={409: {"model": ProfileConflict}}
)
def reset_profile(
    request: Request, owner: Owner, match: Match, operation: Operation
) -> JSONResponse:
    # No reminder tables exist yet. Future reminder enrollment must join this same
    # reset transaction to disable consent/cancel jobs before reminders are enabled.
    return mutate(request, owner, match, operation, None)
