"""create_initial_tables

Revision ID: 5c5ae8f445b3
Revises: 
Create Date: 2025-02-01 15:28:45.221255

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c5ae8f445b3'
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
    print("Таблицы инициализированы.")


    # Добавляем уникальный индекс для tgid с обработкой конфликтов
    op.create_index(
        'idx_userss_tgid_unique',
        'userss',
        ['tgid'],
        unique=True,
        postgresql_where=sa.text('tgid IS NOT NULL')
    )


def downgrade() -> None:
    # Удаление таблицы userss
    op.drop_table('userss')