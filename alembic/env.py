"""
Alembic environment configuration for BARROW.AI.
Handles async migrations with proper connection management.
"""

import asyncio
from logging.config import fileConfig
from typing import Optional

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from alembic import context

# Import models to ensure they're registered with Base
from app.core.database import Base
from app.core.config import settings
from app.models.domain import (
    Conversation,
    Session,
    AdminUser,
    AuditLog,
    KnowledgeDocument,
)

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set sync URL for offline mode (SQL generation only)
# Online/async mode uses settings.database_url (asyncpg) directly — see run_async_migrations()
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

# Add model metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    
    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit SQL to the migration script.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations with a database connection.
    
    Args:
        connection: SQLAlchemy connection
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode with async engine.

    We build the engine directly from settings.database_url (asyncpg) instead
    of reading from alembic.ini, because alembic.ini stores the *sync* URL
    (psycopg2) used for offline SQL generation only.
    """
    connectable: Optional[AsyncEngine] = None

    try:
        connectable = create_async_engine(
            settings.database_url,  # asyncpg — required for async engine
            poolclass=pool.NullPool,
        )

        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

    finally:
        if connectable:
            await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    
    In this scenario we create an Engine and associate a connection with the context.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()