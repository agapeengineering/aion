import json
import uuid

import pytest
from pydantic import SecretStr, ValidationError

from aion.config import Settings
from aion.mail_content import verification_payload
from aion.resend_mail import ProviderResponse, ResendSender, retry_seconds
from aion.verification_mail import (
    Message,
    PermanentDeliveryError,
    RetryDeliveryError,
)

SYNTHETIC_URL = "postgresql+psycopg://synthetic:never-real@127.0.0.1:1/aion"
RECIPIENT = "recipient@example.test"
PROVIDER_ID = str(uuid.uuid4())


def config(tmp_path, **updates):
    key = tmp_path / "key"
    key.write_text("re_synthetic_not_a_real_key")
    return Settings(
        database_url=SecretStr(SYNTHETIC_URL),
        auth_enabled=True,
        resend_enabled=True,
        resend_api_key_file=key,
        email_reply_to="support@example.test",
        resend_allowed_recipients=[RECIPIENT],
        **updates,
    )


def message():
    return Message(
        RECIPIENT,
        "12345678",
        "en",
        verification_payload(
            RECIPIENT,
            "12345678",
            "en",
            "Aion <aion@example.test>",
            "support@example.test",
        ),
    )


def test_provider_request_and_frozen_retry_payload(tmp_path):
    settings = config(tmp_path)
    requests = []
    responses = iter(
        [
            ProviderResponse(429, {"Retry-After": "17"}, b"{}"),
            ProviderResponse(200, {}, json.dumps({"id": PROVIDER_ID}).encode()),
        ]
    )

    def transport(secret, payload, key):
        requests.append((secret, payload.copy(), key))
        return next(responses)

    sender = ResendSender(settings, transport)
    value = message()
    with pytest.raises(RetryDeliveryError) as caught:
        sender.send(value, "logical-key")
    assert caught.value.retry_after == 17 and not caught.value.uncertain
    settings.email_from = "Changed <changed@example.test>"
    assert sender.send(value, "logical-key") == PROVIDER_ID
    assert requests[0] == requests[1]
    assert requests[0][1]["reply_to"] == "support@example.test"
    assert "re_synthetic" not in repr(sender)


@pytest.mark.parametrize("status", [400, 401, 403, 422, 302, 409])
def test_permanent_provider_errors_are_sanitized(tmp_path, status):
    sender = ResendSender(
        config(tmp_path), lambda *_: ProviderResponse(status, {}, b"private details")
    )
    with pytest.raises(PermanentDeliveryError) as caught:
        sender.send(message(), "same-key")
    assert "private details" not in str(caught.value)


@pytest.mark.parametrize(
    "status,body",
    [(503, b"private details"), (200, b"bad-json"), (200, b"{}"), (200, b'{"id":42}')],
)
def test_ambiguous_provider_response_is_retryable_and_uncertain(tmp_path, status, body):
    sender = ResendSender(config(tmp_path), lambda *_: ProviderResponse(status, {}, body))
    with pytest.raises(RetryDeliveryError) as caught:
        sender.send(message(), "same-key")
    assert caught.value.uncertain


def test_disallowed_recipient_never_reaches_transport(tmp_path):
    calls = []
    sender = ResendSender(config(tmp_path), lambda *args: calls.append(args))
    value = message()
    value.email = "someone-else@example.test"
    with pytest.raises(PermanentDeliveryError):
        sender.send(value, "same-key")
    assert not calls


def test_fail_closed_configuration_and_secret_file_errors(tmp_path):
    settings = config(tmp_path)
    settings.resend_api_key_file = tmp_path / "private-missing-key"
    with pytest.raises(ValueError) as caught:
        ResendSender(settings)
    assert "private-missing-key" not in str(caught.value)
    for change in [
        dict(local_mail_capture=True),
        dict(auth_enabled=False),
        dict(email_reply_to=""),
        dict(resend_allowed_recipients=[]),
    ]:
        data = settings.model_dump()
        data.update(change)
        with pytest.raises(ValidationError):
            Settings(**data)


@pytest.mark.parametrize(
    "value,expected", [("12", 12), ("-2", 0), ("nan", 0), ("bad", 0), ("9999999", 86400)]
)
def test_retry_after_is_bounded(value, expected):
    assert retry_seconds({"Retry-After": value}) == expected


def test_transport_uses_fixed_https_idempotency_header_and_no_redirect(monkeypatch):
    import urllib.error

    from aion.resend_mail import NoRedirect, post_email

    requests = []

    class Response:
        code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            assert limit == 65537
            return json.dumps({"id": PROVIDER_ID}).encode()

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert timeout == 5
            return Response()

    def build(*handlers):
        assert isinstance(handlers[0], NoRedirect)
        assert handlers[0].redirect_request(None) is None
        return Opener()

    monkeypatch.setattr("urllib.request.build_opener", build)
    response = post_email("re_synthetic_not_a_real_key", message().provider_payload, "job-id")
    assert response.status == 200
    assert requests[0].full_url == "https://api.resend.com/emails"
    assert requests[0].get_header("Idempotency-key") == "aion-verification/job-id"

    class Offline:
        def open(self, *args, **kwargs):
            raise urllib.error.URLError("private provider details")

    monkeypatch.setattr("urllib.request.build_opener", lambda *_: Offline())
    with pytest.raises(RetryDeliveryError) as caught:
        post_email("re_synthetic_not_a_real_key", message().provider_payload, "job-id")
    assert caught.value.uncertain and "private provider" not in str(caught.value)
