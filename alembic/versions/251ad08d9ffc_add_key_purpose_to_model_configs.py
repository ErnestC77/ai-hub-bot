"""add key_purpose to model_configs

Revision ID: 251ad08d9ffc
Revises: f15b5096efc9
Create Date: 2026-07-06 11:03:27.840092

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '251ad08d9ffc'
down_revision: Union[str, None] = 'f15b5096efc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_KEY_PURPOSE_BY_MODEL_CODE = {
    "claude-3-5-sonnet-20241022": "premium",
    "dall-e-3": "image",
}


def upgrade() -> None:
    op.add_column('model_configs', sa.Column('key_purpose', sa.String(length=50), server_default='text', nullable=False))

    model_configs = sa.table(
        "model_configs",
        sa.column("model_code", sa.String),
        sa.column("key_purpose", sa.String),
    )
    connection = op.get_bind()
    for model_code, key_purpose in _KEY_PURPOSE_BY_MODEL_CODE.items():
        connection.execute(
            model_configs.update().where(model_configs.c.model_code == model_code).values(key_purpose=key_purpose)
        )


def downgrade() -> None:
    op.drop_column('model_configs', 'key_purpose')
