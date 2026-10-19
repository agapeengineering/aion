"""Bounded HTTPS Resend adapter. No global SDK credentials, response bodies or secret logging."""

import json
import math
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from aion.config import Settings
from aion.verification_mail import Message, PermanentDeliveryError, RetryDeliveryError


@dataclass(repr=False)
class ProviderResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def post_email(key: str, payload: dict[str, object], idempotency_key: str) -> ProviderResponse:
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Idempotency-Key": (
                f"aion-reminder/{idempotency_key.removeprefix('reminder/')}"
                if idempotency_key.startswith("reminder/")
                else f"aion-verification/{idempotency_key}"
            ),
            "User-Agent": "Aion/0.1",
        },
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(NoRedirect())
        try:
            response = opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(65537)
            if len(body) > 65536:
                raise RetryDeliveryError(uncertain=True)
            return ProviderResponse(response.code, dict(response.headers), body)
    except urllib.error.URLError, OSError, TimeoutError:
        raise RetryDeliveryError(uncertain=True) from None


def retry_seconds(headers: Mapping[str, str]) -> float:
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), "0")
    try:
        seconds = float(value)
        if not math.isfinite(seconds):
            raise ValueError
        return max(0, min(86400, seconds))
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
            return max(0, min(86400, (moment - datetime.now(UTC)).total_seconds()))
        except ValueError, TypeError, OverflowError:
            return 0


class ResendSender:
    def __init__(
        self,
        settings: Settings,
        transport: Callable[[str, dict[str, object], str], ProviderResponse] = post_email,
    ):
        if not settings.resend_enabled or settings.resend_api_key_file is None:
            raise ValueError("Resend key file is required in the worker")
        try:
            key = settings.resend_api_key_file.read_text().strip()
            if (
                not key.startswith("re_")
                or not 10 <= len(key) <= 512
                or any(x.isspace() for x in key)
            ):
                raise ValueError
        except OSError, ValueError:
            raise ValueError("Resend key configuration is unavailable or invalid") from None
        self._key = key
        self.allowed = frozenset(settings.resend_allowed_recipients)
        self.transport = transport

    def send(self, message: Message, key: str) -> str:
        payload = message.provider_payload
        if message.email not in self.allowed or not payload or payload.get("to") != [message.email]:
            raise PermanentDeliveryError
        # The entire request body was sealed at enqueue, including sender/template/Reply-To.
        response = self.transport(self._key, payload, key)
        if response.status == 429 or response.status >= 500:
            raise RetryDeliveryError(
                retry_seconds(response.headers), uncertain=response.status >= 500
            )
        if response.status == 409:
            # concurrent_idempotent_requests is transient; changed payload/key conflicts are not.
            try:
                conflict = json.loads(response.body).get("name")
            except ValueError, AttributeError:
                conflict = None
            if conflict == "concurrent_idempotent_requests":
                raise RetryDeliveryError(1)
        if response.status != 200:
            raise PermanentDeliveryError
        try:
            identifier = json.loads(response.body)["id"]
            if not isinstance(identifier, str):
                raise ValueError
            uuid.UUID(identifier)
        except ValueError, TypeError, KeyError:
            raise RetryDeliveryError(uncertain=True) from None
        return str(identifier)
