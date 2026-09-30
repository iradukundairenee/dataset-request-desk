from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db import Base

import app.models  # noqa: F401  (registers the tables on Base.metadata)

config = context.config
if config.config_file_name is not None:
    # Keep loggers the app already set up (e.g. the JSON request logger in tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# URL priority: `-x url=...` on the command line, then a URL set in code
# (the tests do this to migrate the test DB), then DATABASE_URL.
url = (
    context.get_x_argument(as_dictionary=True).get("url")
    or config.get_main_option("sqlalchemy.url")
    or settings.database_url
)
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
