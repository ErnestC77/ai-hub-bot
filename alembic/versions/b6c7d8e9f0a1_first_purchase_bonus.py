"""Бонус-кредиты на первую покупку пакета (+percent с капом).

Вместо «скидки» (меняла бы суммы YooKassa) первая покупка даёт надбавку
кредитами: bonus = min(credits * percent / 100, cap). Кап обязателен: без него
+30% на BUSINESS (70k кредитов) уводит пакет в минус по марже, а с капом START
получает ощутимые +300, крупные -- символические +1500.

Enum-значение first_purchase_bonus (не purchase!): бонус не должен второй раз
поднимать total_credits_purchased, это же поле служит признаком «первая
покупка уже была».

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-07-19 12:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b6c7d8e9f0a1'
down_revision: Union[str, None] = 'a5b6c7d8e9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SETTINGS = [
    {"key": "first_purchase_bonus_percent", "value": "30", "type": "int",
     "description": "Бонус-кредиты на первую покупку, % от пакета (0 = выключено)"},
    {"key": "first_purchase_bonus_cap", "value": "1500", "type": "int",
     "description": "Потолок бонуса первой покупки в кредитах (защита маржи крупных пакетов)"},
]


def upgrade() -> None:
    # credittxtype -- нативный Postgres enum; ADD VALUE только вне транзакции.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE credittxtype ADD VALUE IF NOT EXISTS 'first_purchase_bonus'")
    # Сид тоже вставит эти ключи (INSERT только отсутствующих); миграция нужна
    # для БД, где сид уже отработал до апдейта.
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
               "('first_purchase_bonus_percent', 'first_purchase_bonus_cap')")
    # Postgres не умеет удалять значение из enum -- first_purchase_bonus остаётся (безвредно).
