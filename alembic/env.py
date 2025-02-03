from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine
from alembic import context
import asyncio

# Добавьте эту строку, чтобы Alembic мог находить ваши модели
import sys
from os.path import abspath, dirname
sys.path.insert(0, dirname(dirname(abspath(__file__))))

# Импортируйте ваши модели (если используете SQLAlchemy)
# from your_app.models import Base

# Конфигурация Alembic
config = context.config

# Настройка логгера
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Укажите метаданные ваших моделей (если используете SQLAlchemy)
# target_metadata = Base.metadata
target_metadata = None

def run_migrations_offline():
    """Запуск миграций в оффлайн-режиме."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    """Запуск миграций в онлайн-режиме."""
    connectable = AsyncEngine(
        engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            future=True,
        )
    )

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure(
                connection=sync_conn, target_metadata=target_metadata
            )
        )

        async with connection.begin():
            await connection.run_sync(lambda conn: context.run_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()