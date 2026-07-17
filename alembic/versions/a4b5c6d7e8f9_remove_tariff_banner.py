"""remove outdated 'Кредиты поверх тарифа' banner

Баннер вводил в заблуждение (тарифов/лимитов в продукте нет). Удалён из сида;
здесь снимается с живой БД. apply_seed идемпотентен по title и после удаления
из BANNERS его не пере-вставит.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-17
"""

from alembic import op

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM banners WHERE title = 'Кредиты поверх тарифа'")


def downgrade() -> None:
    # Восстановление опущено: баннер удалён намеренно как устаревший контент.
    pass
