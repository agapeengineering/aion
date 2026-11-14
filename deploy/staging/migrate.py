"""Apply the staged schema and its runtime grants in the same transaction."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError

from aion.config import Settings
from aion.database import make_engine


def main() -> None:
    engine = make_engine(Settings())
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(4522486924529524441)")
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            grants = Path(__file__).with_name("runtime-grants.sql").read_text()
            connection.exec_driver_sql(grants)
    except SQLAlchemyError as exc:
        original = getattr(exc, "orig", None)
        sqlstate = getattr(original, "sqlstate", None)
        raise SystemExit(
            f"Schema or runtime grants failed ({sqlstate or 'database error'})."
        ) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
