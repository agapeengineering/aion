"""Explicit configuration; never infer production credentials or read a tracked .env."""

import re
from email.utils import formataddr, parseaddr
from pathlib import Path
from typing import Annotated, Self

from email_validator import EmailNotValidError, validate_email
from pydantic import Field, PrivateAttr, SecretStr, model_validator
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
    recovery_journal_socket: Path | None = None
    recovery_journal_epoch_file: Path | None = None
    _recovery_journal_epoch: str | None = PrivateAttr(default=None)

    reminders_enabled: bool = False
    resend_webhook_secret_file: Path | None = None

    resend_enabled: bool = False
    resend_public_accounts: bool = False
    resend_daily_limit: Annotated[int, Field(ge=1, lt=2_147_483_647)] | None = None
    resend_api_key_file: Path | None = None
    email_from: str = "Aion <aion@mail.agape.engineering>"
    email_reply_to: str = ""
    resend_allowed_recipients: list[str] = []

    def resend_recipient_allowed(self, email: str) -> bool:
        return self.resend_public_accounts or email in self.resend_allowed_recipients

    @property
    def recovery_journal_epoch(self) -> str | None:
        return self._recovery_journal_epoch

    @model_validator(mode="after")
    def validate_mail(self) -> Self:
        if (self.recovery_journal_socket is None) != (self.recovery_journal_epoch_file is None):
            raise ValueError("Configure both the recovery journal socket and epoch file")
        if self.recovery_journal_epoch_file is not None:
            try:
                epoch = self.recovery_journal_epoch_file.read_text(encoding="ascii").strip()
                if not re.fullmatch(r"[0-9a-f]{32}", epoch):
                    raise ValueError
            except OSError, ValueError:
                raise ValueError("Recovery journal epoch file is unavailable or invalid") from None
            self._recovery_journal_epoch = epoch
        if self.resend_public_accounts:
            if (
                not self.resend_enabled
                or self.auth_origin != "https://aion.agape.engineering"
                or self.reminders_enabled
                or self.resend_allowed_recipients
            ):
                raise ValueError(
                    "Public account mail requires canonical transactional configuration"
                )
            if self.recovery_journal_socket is None or self.resend_daily_limit is None:
                raise ValueError(
                    "Public account mail requires the recovery journal and a daily limit"
                )
        if self.reminders_enabled and (
            not self.auth_enabled or not (self.local_mail_capture or self.resend_enabled)
        ):
            raise ValueError("Reminders require configured authenticated mail delivery")
        if self.resend_enabled and (self.reminders_enabled or self.resend_public_accounts):
            if self.resend_webhook_secret_file is None:
                raise ValueError("This mail configuration requires a webhook secret")
            try:
                from svix.webhooks import Webhook

                secret = self.resend_webhook_secret_file.read_text().strip()
                if not secret.startswith("whsec_"):
                    raise ValueError
                Webhook(secret)
            except OSError, ValueError:
                raise ValueError("Mail webhook secret is unavailable or invalid") from None
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
            sender = mailbox(address)
            if self.resend_public_accounts and sender.rsplit("@", 1)[1] != "mail.agape.engineering":
                raise ValueError
            self.email_from = formataddr((name, sender))
            self.email_reply_to = mailbox(self.email_reply_to)
            self.resend_allowed_recipients = [mailbox(x) for x in self.resend_allowed_recipients]
            if not self.resend_public_accounts and not self.resend_allowed_recipients:
                raise ValueError
        except ValueError, EmailNotValidError:
            raise ValueError("Resend requires valid sender, Reply-To and recipient scope") from None
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
