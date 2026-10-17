import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from aion.config import Settings
from aion.database import make_engine

ROOT = Path(__file__).resolve().parents[1]


def migration_config(engine: Engine) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = engine.connect()
    return config


def migrate(engine: Engine, target: str = "head", *, down: bool = False) -> None:
    config = migration_config(engine)
    try:
        if down:
            command.downgrade(config, target)
        else:
            command.upgrade(config, target)
    finally:
        config.attributes["connection"].close()


@pytest.fixture
def database_settings() -> Iterator[Settings]:
    """Only create/drop a random test schema; never downgrade a caller's database."""
    raw = os.environ.get("AION_TEST_DATABASE_URL")
    file = os.environ.get("AION_TEST_DATABASE_URL_FILE")
    if bool(raw) == bool(file):
        pytest.fail("Set exactly one explicit disposable AION_TEST_DATABASE_URL[_FILE]")
    if file:
        raw = Path(file).read_text().strip()
    assert raw is not None
    admin = make_engine(Settings(database_url=SecretStr(raw)))
    schema = "aion_test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = make_url(raw).update_query_dict({"options": f"-c search_path={schema}"})
    try:
        yield Settings(database_url=SecretStr(scoped_url.render_as_string(hide_password=False)))
    finally:
        assert schema.startswith("aion_test_") and len(schema) == 42
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def database(database_settings: Settings) -> Iterator[Engine]:
    engine = make_engine(database_settings)
    migrate(engine)
    try:
        yield engine
    finally:
        engine.dispose()
