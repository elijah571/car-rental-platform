
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.core.database import Base
from app import models as _models

# Alembic configuration from alembic.ini
config = context.config

# Configure logging when a configuration file is available.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import model modules here so Alembic can discover their tables.
# Example later: from app.models import car, booking, payment

target_metadata = Base.metadata
version_table = "alembic_version"


def include_name(name, type_, parent_names):
    if type_ == "table":
        return name in target_metadata.tables or name == version_table
    return True


def run_migrations_offline() -> None:
    """Generate migrations without opening a database connection."""
    url = get_settings().database_url

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table=version_table,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations using an active database connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table=version_table,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect asynchronously to PostgreSQL for migrations."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_settings().database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"search_path": "public"}},
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
