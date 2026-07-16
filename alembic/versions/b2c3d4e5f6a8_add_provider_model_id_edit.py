"""add ai_models.provider_model_id_edit -- отдельный маршрут image-to-image.

У flux-pro/kontext и nano-banana t2i и i2i -- разные эндпоинты fal.
Одна строка каталога не может нести оба, отсюда колонка.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_models', sa.Column('provider_model_id_edit', sa.String(length=128), nullable=True))
    op.execute(
        sa.text("UPDATE ai_models SET provider_model_id_edit = :v WHERE code = 'flux_kontext_pro'")
        .bindparams(v="fal-ai/flux-pro/kontext")
    )
    op.execute(
        sa.text("UPDATE ai_models SET provider_model_id_edit = :v WHERE code = 'nano_banana'")
        .bindparams(v="fal-ai/nano-banana/edit")
    )


def downgrade() -> None:
    op.drop_column('ai_models', 'provider_model_id_edit')
