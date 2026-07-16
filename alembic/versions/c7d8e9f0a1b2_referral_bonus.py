"""referral bonus: колонка bonus_credits, enum-значение, настройки.

Revision ID: c7d8e9f0a1b2
Revises: bb51258925d4
Create Date: 2026-07-16 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'bb51258925d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SETTINGS = [
    {"key": "referral_bonus_referrer_credits", "value": "20", "type": "int",
     "description": "Бонус пригласившему за друга, сделавшего первый запрос"},
    {"key": "referral_bonus_referred_credits", "value": "20", "type": "int",
     "description": "Бонус приглашённому после его первого запроса"},
]


def upgrade() -> None:
    op.add_column("referrals", sa.Column("bonus_credits", sa.Integer(), nullable=False,
                                         server_default="0"))
    # credittxtype -- нативный Postgres enum; ADD VALUE только вне транзакции.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE credittxtype ADD VALUE IF NOT EXISTS 'referral_bonus'")
    # Сид тоже вставит эти ключи (INSERT только отсутствующих), поэтому конфликта нет;
    # миграция нужна для БД, где сид уже отработал до апдейта.
    settings = sa.table(
        "settings",
        sa.column("key", sa.String), sa.column("value", sa.String),
        sa.column("type", sa.String), sa.column("description", sa.String),
    )
    for row in _SETTINGS:
        op.execute(
            settings.insert().from_select(
                ["key", "value", "type", "description"],
                sa.select(
                    sa.literal(row["key"]), sa.literal(row["value"]),
                    sa.literal(row["type"]), sa.literal(row["description"]),
                ).where(~sa.exists().where(settings.c.key == row["key"]))
            )
        )


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key IN "
               "('referral_bonus_referrer_credits', 'referral_bonus_referred_credits')")
    op.drop_column("referrals", "bonus_credits")
    # Postgres не умеет удалять значение из enum -- referral_bonus остаётся (безвредно).
