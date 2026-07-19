"""Реферальный бонус 20 -> 50 обеим сторонам.

20 кредитов -- полфото, стимул слабый. 50 = ~1 фото + чаты (себестоимость нам
~3.5 ₽ за обе стороны) -- ощутимо, и рефералка начинает работать как канал.
UPDATE только со значения по умолчанию '20': если админ уже выставил своё
через /admin/settings -- не перетираем.

Revision ID: c8d9e0f1a2b3
Revises: b6c7d8e9f0a1
Create Date: 2026-07-19 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, None] = 'b6c7d8e9f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEYS = "('referral_bonus_referrer_credits', 'referral_bonus_referred_credits')"


def upgrade() -> None:
    op.execute(f"UPDATE settings SET value = '50' WHERE key IN {_KEYS} AND value = '20'")


def downgrade() -> None:
    op.execute(f"UPDATE settings SET value = '20' WHERE key IN {_KEYS} AND value = '50'")
