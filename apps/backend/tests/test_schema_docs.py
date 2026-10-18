"""Verify that database documentation follows migrations and catches schema drift."""

import runpy
from pathlib import Path

import pytest
from sqlalchemy import text

EXPORTER = Path(__file__).resolve().parents[3] / "tools/export-database-diagram.py"
namespace = runpy.run_path(str(EXPORTER))
ROOT = namespace["TARGET"]
documents = namespace["documents"]
pytestmark = pytest.mark.integration


def test_migrated_schema_matches_committed_documentation(database):
    first = documents(database)
    assert first == documents(database)
    for name, value in first.items():
        assert value == (ROOT / name).read_text()
    assert " 1--1 " not in first["database-schema.md"]
    assert "mermaid.ink" not in first["database-schema.md"]
    assert "aion_test_" not in first["database-schema.dot"]
    assert "alembic_version {" not in first["database-schema.md"]


def test_reflected_database_change_updates_diagram(database):
    before = documents(database)
    with database.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN synthetic_schema_change INTEGER"))
    after = documents(database)
    assert before != after
    assert all("synthetic_schema_change" in value for value in after.values())


def test_check_rejects_stale_output_without_rewriting(monkeypatch, tmp_path):
    main = namespace["main"]
    monkeypatch.setitem(main.__globals__, "TARGET", tmp_path)
    monkeypatch.setattr("sys.argv", ["export-database-diagram.py", "--check"])
    stale = tmp_path / "database-schema.md"
    stale.write_text("stale schema documentation\n")
    assert main() == 1
    assert stale.read_text() == "stale schema documentation\n"
    assert not (tmp_path / "database-schema.dot").exists()


def test_temporary_schema_removed_after_failure(database):
    with (
        pytest.raises(RuntimeError, match="synthetic failure"),
        namespace["migrated_schema"]() as engine,
    ):
        with engine.connect() as connection:
            schema = connection.scalar(text("SELECT current_schema()"))
        raise RuntimeError("synthetic failure")
    with database.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM pg_namespace WHERE nspname = :schema"),
                {"schema": schema},
            )
            == 0
        )
