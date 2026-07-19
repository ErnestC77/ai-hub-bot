"""users.acquisition_source — источник привлечения (рекламные метки).

Deep-link `t.me/bot?start=ads_X` (или `?startapp=ads_X` у Mini App) пишет метку
в момент СОЗДАНИЯ пользователя; дальше не перезаписывается. `ref_*`-ссылки
нормализуются в "referral". NULL = органика. Индекс — под GROUP BY в
админ-отчёте «Источники» (старты/платящие/выручка по метке).

Revision ID: a5b6c7d8e9f0
Revises: f9a0b1c2d3e4
Create Date: 2026-07-19 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, None] = 'f9a0b1c2d3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('acquisition_source', sa.String(length=64), nullable=True))
    op.create_index('ix_users_acquisition_source', 'users', ['acquisition_source'])


def downgrade() -> None:
    op.drop_index('ix_users_acquisition_source', table_name='users')
    op.drop_column('users', 'acquisition_source')
