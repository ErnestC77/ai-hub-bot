"""phase4: credit_packages.price_stars (Telegram Stars price, PLACEHOLDER rate
~= price_rub / 2, admin-editable in phase 5) + drop dead payments.tariff_id
(tariffs table was removed in phase 1; the FK constraint on this column was
already dropped by the phase-1 migration, so a plain DROP COLUMN suffices).

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Spec table (phase 4): PLACEHOLDER Stars prices for the 5 seeded packages.
_PRICE_STARS = {"start": 75, "basic": 300, "plus": 645, "pro": 1495, "business": 2995}


def upgrade() -> None:
    op.add_column(
        'credit_packages',
        sa.Column('price_stars', sa.Integer(), nullable=False, server_default='0'),
    )
    # Existing rows were seeded before this column existed -- backfill them.
    # (app/db/seed.py only inserts MISSING codes, so it would leave 0 here.)
    for code, stars in _PRICE_STARS.items():
        op.execute(
            sa.text("UPDATE credit_packages SET price_stars = :stars WHERE code = :code")
            .bindparams(stars=stars, code=code)
        )
    op.drop_column('payments', 'tariff_id')


def downgrade() -> None:
    op.add_column('payments', sa.Column('tariff_id', sa.Integer(), nullable=True))
    op.drop_column('credit_packages', 'price_stars')
