from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from aion.config import Settings

SYNTHETIC_URL = "postgresql+psycopg://synthetic:never-a-real-secret@127.0.0.1:1/aion"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AION_DATABASE_URL", raising=False)
    monkeypatch.delenv("AION_DATABASE_URL_FILE", raising=False)


def test_requires_one_explicit_source(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings()
    with pytest.raises(ValidationError):
        Settings(database_url=SecretStr(SYNTHETIC_URL), database_url_file=tmp_path / "missing")


def test_secret_file_load_and_redaction(tmp_path: Path) -> None:
    path = tmp_path / "database-url"
    path.write_text(SYNTHETIC_URL + "\n")
    settings = Settings(database_url_file=path)
    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == SYNTHETIC_URL
    assert "never-a-real-secret" not in repr(settings)
    assert "never-a-real-secret" not in settings.model_dump_json()


@pytest.mark.parametrize("url", ["sqlite:///aion.db", "garbage-secret", "postgresql://u:p@db/aion"])
def test_rejects_unsupported_or_malformed_dsn_without_echoing_input(url: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(database_url=SecretStr(url))
    assert url not in str(caught.value)


def test_missing_file_has_no_os_exception_payload(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="secret file is unavailable") as caught:
        Settings(database_url_file=tmp_path / "missing-private-file")
    assert "missing-private-file" not in str(caught.value)
