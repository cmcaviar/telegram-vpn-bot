"""create_initial_tables

Revision ID: 2612ab29d0e5
Revises: 5c5ae8f445b3
Create Date: 2025-02-03 06:36:19.143962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1bd5aba1af38'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создание таблицы userss
    op.create_table(
        'userss',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('tgid', sa.BigInteger, nullable=False, unique=True),
        sa.Column('subscription', sa.Text),
        sa.Column('banned', sa.Boolean, default=False),
        sa.Column('notion_oneday', sa.Boolean, default=True),
        sa.Column('username', sa.Text),
        sa.Column('fullname', sa.Text)
    )

    # Создание таблицы payments
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('tgid', sa.BigInteger, nullable=False),
        sa.Column('bill_id', sa.Text),
        sa.Column('amount', sa.BigInteger),
        sa.Column('time_to_add', sa.BigInteger),
        sa.Column('mesid', sa.Text)
    )

    # Создание таблицы static_profiles
    op.create_table(
        'static_profiles',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String)
    )

    print("Таблицы инициализированы.")

    # Добавляем уникальный индекс для tgid
    op.create_index(
        'idx_userss_tgid_unique',
        'userss',
        ['tgid'],
        unique=True,
        postgresql_where=sa.text('tgid IS NOT NULL')
    )


def downgrade() -> None:
    # Удаление таблиц
    op.drop_table('static_profiles')
    op.drop_table('payments')
    op.drop_table('userss')
