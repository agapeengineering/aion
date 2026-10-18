from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from aion.config import Settings

SCHEMA_REVISION = "0002_verification"


def make_engine(settings: Settings) -> Engine:
    assert settings.database_url is not None
    url = make_url(settings.database_url.get_secret_value())
    existing_options = url.query.get("options", "")
    url = url.update_query_dict({"options": f"{existing_options} -c statement_timeout=3000"})
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=2,
        connect_args={"connect_timeout": 2},
        hide_parameters=True,
        echo=False,
    )


def is_ready(engine: Engine) -> bool:
    """Reachable database AND exact expected migration; never auto-create tables."""
    try:
        with engine.connect() as connection:
            revisions = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars()
            return list(revisions) == [SCHEMA_REVISION]
    except SQLAlchemyError:
        # A connection exception can contain a host, account or DSN. Do not log it.
        return False
