"""phase2: add ai_models.fallback_model_code (nullable, no FK --
validated at the service layer, see phase 2 spec).

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_models', sa.Column('fallback_model_code', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('ai_models', 'fallback_model_code')
