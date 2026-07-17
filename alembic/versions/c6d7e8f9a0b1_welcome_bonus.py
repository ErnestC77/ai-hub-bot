"""welcome-бонус новичкам: free_tier_allowed у моделей, enum-значение, настройки.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-07-17 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SETTINGS = [
    {"key": "welcome_bonus_credits", "value": "220", "type": "int",
     "description": "Кредиты новому пользователю при первом входе (0 = выключено)"},
]


def upgrade() -> None:
    # До первой покупки фото-генерация разрешена только на моделях с этим флагом
    # (см. antifraud_service.check_tier_allowed). Флаг, а не «самая дешёвая по
    # min_credits»: цены правятся из админки, и вычисляемое правило молча
    # переносило бы бесплатный тариф на другую модель при переоценке каталога.
    op.add_column("ai_models", sa.Column("free_tier_allowed", sa.Boolean(), nullable=False,
                                         server_default=sa.false()))
    op.execute("UPDATE ai_models SET free_tier_allowed = true WHERE code = 'qwen_image'")

    # credittxtype -- нативный Postgres enum; ADD VALUE только вне транзакции.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE credittxtype ADD VALUE IF NOT EXISTS 'welcome_bonus'")

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

    # Потолок free-трат должен вмещать подарок, иначе бонус молча недодаёт:
    # при cap=100 из 220 подаренных тратится 100 (3 фото вместо 5). Поднимаем
    # ТОЛЬКО нетронутый дефолт фазы 5 -- если админ уже подобрал своё значение,
    # это его решение, и затирать его миграцией нельзя.
    op.execute("UPDATE settings SET value = '220' "
               "WHERE key = 'free_tier_credit_cap' AND value = '100'")


def downgrade() -> None:
    op.execute("UPDATE settings SET value = '100' "
               "WHERE key = 'free_tier_credit_cap' AND value = '220'")
    op.execute("DELETE FROM settings WHERE key = 'welcome_bonus_credits'")
    op.drop_column("ai_models", "free_tier_allowed")
    # Postgres не умеет удалять значение из enum -- welcome_bonus остаётся (безвредно).
