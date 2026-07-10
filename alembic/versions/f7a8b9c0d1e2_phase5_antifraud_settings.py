"""phase5: seed 5 antifraud settings rows (daily spend limit, per-user and
per-model rate limits, duplicate cooldown, free tier cap). No schema changes:
rate-limit / daily-spend / dedup counters live in Redis; the free-tier cap
reuses existing users columns (total_credits_purchased / total_credits_spent).

Deploy order (entrypoint.sh): `alembic upgrade head` runs BEFORE
`python -m app.db.seed`, and the seed only inserts missing keys, so this
bulk_insert cannot hit a duplicate-key conflict.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_settings_table = sa.table(
    'settings',
    sa.column('key', sa.String),
    sa.column('value', sa.String),
    sa.column('type', sa.String),
    sa.column('description', sa.String),
)

# Ровно те же 5 строк, что в app/db/seed.py (сид фазы 5).
_ANTIFRAUD_ROWS = [
    {"key": "daily_spend_limit_credits", "value": "10000", "type": "int",
     "description": "Дневной лимит трат на пользователя"},
    {"key": "rate_limit_per_user_per_minute", "value": "10", "type": "int",
     "description": "Rate limit запросов на пользователя"},
    {"key": "rate_limit_per_model_per_minute", "value": "60", "type": "int",
     "description": "Rate limit запросов на модель (глобально)"},
    {"key": "duplicate_cooldown_seconds", "value": "5", "type": "int",
     "description": "Окно блокировки повторного идентичного запроса"},
    {"key": "free_tier_credit_cap", "value": "100", "type": "int",
     "description": "Максимум бесплатных кредитов для непокупавших пользователей"},
]


def upgrade() -> None:
    op.bulk_insert(_settings_table, _ANTIFRAUD_ROWS)


def downgrade() -> None:
    for row in _ANTIFRAUD_ROWS:
        op.execute(
            sa.text("DELETE FROM settings WHERE key = :key").bindparams(key=row["key"])
        )
