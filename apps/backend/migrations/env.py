from alembic import context

from aion.config import Settings
from aion.database import make_engine
from aion.models import Base


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError(
        "Offline migration is not supported; use an explicit disposable PostgreSQL DB"
    )
elif (connection := context.config.attributes.get("connection")) is not None:
    migrate(connection)
else:
    engine = make_engine(Settings())
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
