import logging

import pytest
from conftest import migrate
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text

from aion.config import Settings
from aion.main import create_app

UNREACHABLE = Settings(
    database_url=SecretStr("postgresql+psycopg://synthetic:never-a-real-secret@127.0.0.1:1/aion")
)


def test_liveness_survives_database_failure_without_leaking_details(caplog) -> None:
    with TestClient(create_app(UNREACHABLE)) as client:
        assert client.get("/api/v1/health/live").json() == {"status": "ok"}
        with caplog.at_level(logging.WARNING):
            r = client.get("/api/v1/health/ready")
        assert r.status_code == 503
        assert r.json() == {"status": "unavailable"}
        assert r.headers["cache-control"] == "no-store"
    assert "never-a-real-secret" not in caplog.text
    assert "psycopg" not in caplog.text


@pytest.mark.parametrize(
    "path", ["/api/v1/auth/verify", "/api/v1/unknown", "/docs", "/openapi.json"]
)
def test_unimplemented_paths_are_json_404_not_spa_or_fake_auth(path: str) -> None:
    with TestClient(create_app(UNREACHABLE)) as client:
        r = client.get(path)
        assert r.status_code == 404
        assert r.json() == {"error": {"code": "not_found"}}
        assert r.headers["cache-control"] == "no-store"


def test_health_rejects_writes() -> None:
    with TestClient(create_app(UNREACHABLE)) as client:
        response = client.post("/api/v1/health/live")
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"


@pytest.mark.integration
def test_readiness_checks_migration_and_detects_revision_drift(database_settings: Settings) -> None:
    with TestClient(create_app(database_settings)) as client:
        engine: Engine = client.app.state.engine
        assert client.get("/api/v1/health/ready").status_code == 503
        migrate(engine)
        assert client.get("/api/v1/health/ready").status_code == 200
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'unexpected'"))
        assert client.get("/api/v1/health/ready").status_code == 503
        assert client.get("/api/v1/health/live").status_code == 200
