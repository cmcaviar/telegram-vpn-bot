"""
Создание таблицы users
"""

from yoyo import step

__depends__ = {}

steps = [
    # Создание таблицы userss
    step(
        """
        CREATE TABLE IF NOT EXISTS userss (
            id SERIAL PRIMARY KEY,
            tgid BIGINT NOT NULL UNIQUE,
            subscription TEXT,
            banned BOOLEAN DEFAULT FALSE,
            notion_oneday BOOLEAN DEFAULT TRUE,
            username TEXT,
            fullname TEXT
        );
        """,
        "DROP TABLE userss;"
    ),

    # Создание таблицы payments
    step(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            tgid BIGINT NOT NULL,
            bill_id TEXT,
            amount BIGINT,
            time_to_add BIGINT,
            mesid TEXT
        );
        """,
        "DROP TABLE payments;"
    ),

    # Создание таблицы static_profiles
    step(
        """
        CREATE TABLE IF NOT EXISTS static_profiles (
            id SERIAL PRIMARY KEY,
            name VARCHAR
        );
        """,
        "DROP TABLE static_profiles;"
    ),

    # Создание уникального индекса для tgid в userss
    step(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_userss_tgid_unique
        ON userss (tgid)
        WHERE tgid IS NOT NULL;
        """,
        "DROP INDEX IF EXISTS idx_userss_tgid_unique;"
    )
]
