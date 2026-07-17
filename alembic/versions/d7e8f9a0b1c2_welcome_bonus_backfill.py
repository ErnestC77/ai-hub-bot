"""backfill: выдать welcome-бонус старым непокупавшим без бонуса.

Одноразовая data-миграция. Welcome-бонус начисляется только на ветке создания
строки в users (user_service), поэтому все, кто зарегистрировался ДО фичи,
остались с нулём. Догоняем их тем же начислением, что и новичков.

Идемпотентна и безопасна к повтору: обрабатываем только тех, у кого ещё нет
транзакции welcome_bonus. Второй прогон миграции никого не задваивает.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-07-17 14:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Размер берём из настроек -- та же величина, что дарится новичкам. Если
    # welcome_bonus_credits=0 (фича выключена), backfill тоже ничего не делает.
    amount = bind.execute(sa.text(
        "SELECT COALESCE((SELECT value::int FROM settings "
        "WHERE key = 'welcome_bonus_credits'), 0)"
    )).scalar_one()
    if amount <= 0:
        return

    # Кандидаты: не покупали и ещё не получали welcome_bonus. Строку аудита и
    # обновление баланса пишем в ОДНОМ операторе на пользователя, чтобы
    # balance_before/after были согласованы. FOR UPDATE не нужен: миграция
    # гоняется на старте одного контейнера до приёма трафика (entrypoint.sh).
    rows = bind.execute(sa.text(
        "SELECT u.id, u.credits_balance FROM users u "
        "WHERE u.total_credits_purchased = 0 "
        "AND NOT EXISTS (SELECT 1 FROM credit_transactions t "
        "                WHERE t.user_id = u.id AND t.type = 'welcome_bonus')"
    )).all()

    for user_id, balance in rows:
        bind.execute(
            sa.text(
                "INSERT INTO credit_transactions "
                "(user_id, type, amount, balance_before, balance_after, description) "
                "VALUES (:uid, 'welcome_bonus', :amt, :before, :after, 'welcome bonus (backfill)')"
            ),
            {"uid": user_id, "amt": amount, "before": balance, "after": balance + amount},
        )
        bind.execute(
            sa.text("UPDATE users SET credits_balance = credits_balance + :amt WHERE id = :uid"),
            {"amt": amount, "uid": user_id},
        )


def downgrade() -> None:
    # Откатываем ровно то, что начислили: снимаем баланс и убираем аудит-строки
    # backfill'а (по description -- обычные welcome-бонусы новичков не трогаем).
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT user_id, amount FROM credit_transactions "
        "WHERE type = 'welcome_bonus' AND description = 'welcome bonus (backfill)'"
    )).all()
    for user_id, amount in rows:
        bind.execute(
            sa.text("UPDATE users SET credits_balance = GREATEST(0, credits_balance - :amt) "
                    "WHERE id = :uid"),
            {"amt": amount, "uid": user_id},
        )
    bind.execute(sa.text(
        "DELETE FROM credit_transactions "
        "WHERE type = 'welcome_bonus' AND description = 'welcome bonus (backfill)'"
    ))
