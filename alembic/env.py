import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from alembic import context
import os

# Подключаем конфиг логирования Alembic
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Загружаем URL базы из alembic.ini
DATABASE_URL = config.get_main_option("sqlalchemy.url")

# Создаём асинхронный движок (если у тебя PostgreSQL с asyncpg)
connectable = create_async_engine(DATABASE_URL, future=True)

async def run_migrations_online():
    """Асинхронный запуск миграций."""
    async with connectable.connect() as connection:
        await connection.run_sync(do_migrations)

def do_migrations(connection):
    """Настройка Alembic."""
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_migrations_online())