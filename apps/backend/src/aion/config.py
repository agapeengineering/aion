"""Explicit configuration; never infer production credentials or read a tracked .env."""

from pathlib import Path
from typing import Self

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
