"""Explicit configuration; never infer production credentials or read a tracked .env."""

from email.utils import formataddr, parseaddr
from pathlib import Path
from typing import Self

from email_validator import EmailNotValidError, validate_email
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AION_", hide_input_in_errors=True)

    database_url: SecretStr | None = None
    database_url_file: Path | None = None
    auth_enabled: bool = False
    auth_origin: str = "https://aion.agape.engineering"
    auth_secrets_file: Path | None = None
    local_mail_capture: bool = False

    reminders_enabled: bool = False
    resend_webhook_secret_file: Path | None = None

    resend_enabled: bool = False
    resend_api_key_file: Path | None = None
    email_from: str = "Aion <aion@mail.agape.engineering>"
    email_reply_to: str = ""
    resend_allowed_recipients: list[str] = []

    @model_validator(mode="after")
    def validate_mail(self) -> Self:
        if self.reminders_enabled and (
            not self.auth_enabled or not (self.local_mail_capture or self.resend_enabled)
        ):
            raise ValueError("Reminders require configured authenticated mail delivery")
        if (
            self.reminders_enabled
            and self.resend_enabled
            and self.resend_webhook_secret_file is None
        ):
            raise ValueError("Real reminder delivery requires a webhook secret")
        if self.reminders_enabled and self.resend_enabled:
            try:
                from svix.webhooks import Webhook

                assert self.resend_webhook_secret_file
                secret = self.resend_webhook_secret_file.read_text().strip()
                if not secret.startswith("whsec_"):
                    raise ValueError
                Webhook(secret)
            except OSError, ValueError:
                raise ValueError("Reminder webhook secret is unavailable or invalid") from None
        if not self.resend_enabled:
            return self
        if self.local_mail_capture or not self.auth_enabled:
            raise ValueError("Resend requires enabled auth and disabled local capture")
        try:

            def mailbox(value: str) -> str:
                if "\r" in value or "\n" in value:
                    raise ValueError
                return validate_email(
                    value,
                    check_deliverability=False,
                    allow_smtputf8=False,
                    test_environment=True,
                ).normalized.lower()

            name, address = parseaddr(self.email_from, strict=True)
            self.email_from = formataddr((name, mailbox(address)))
            self.email_reply_to = mailbox(self.email_reply_to)
            self.resend_allowed_recipients = [mailbox(x) for x in self.resend_allowed_recipients]
            if not self.resend_allowed_recipients:
                raise ValueError
        except ValueError, EmailNotValidError:
            raise ValueError(
                "Resend requires valid sender, Reply-To and explicit test recipients"
            ) from None
        return self

    @model_validator(mode="after")
    def validate_database(self) -> Self:
        if (self.database_url is None) == (self.database_url_file is None):
            raise ValueError("Configure exactly one database URL source")
        if self.database_url_file is not None:
            try:
                raw = self.database_url_file.read_text().strip()
            except OSError:
                raise ValueError("Database secret file is unavailable") from None
            self.database_url = SecretStr(raw)
        assert self.database_url is not None
        try:
            url = make_url(self.database_url.get_secret_value())
        except ArgumentError:
            raise ValueError("Invalid database configuration") from None
        if (
            url.drivername != "postgresql+psycopg"
            or not url.host
            or not url.database
            or not url.username
            or not url.password
        ):
            raise ValueError("A complete PostgreSQL psycopg URL is required")
        return self
