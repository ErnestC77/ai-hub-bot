"""add piapi schema: video category, piapi provider, model_configs piapi columns, ai_requests.provider_task_id

Revision ID: a1f2c3d4e5f6
Revises: 749f76e9eaca
Create Date: 2026-07-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1f2c3d4e5f6'
down_revision: Union[str, None] = '749f76e9eaca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in Postgres.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE modelcategory ADD VALUE IF NOT EXISTS 'video'")
        op.execute("ALTER TYPE modelprovider ADD VALUE IF NOT EXISTS 'piapi'")

    op.add_column('model_configs', sa.Column('piapi_model', sa.String(length=64), nullable=True))
    op.add_column('model_configs', sa.Column('piapi_task_type', sa.String(length=64), nullable=True))
    op.add_column('model_configs', sa.Column('piapi_extra_input', sa.JSON(), nullable=True))
    op.add_column('model_configs', sa.Column('duration_seconds', sa.Integer(), nullable=True))
    op.add_column('ai_requests', sa.Column('provider_task_id', sa.String(length=128), nullable=True))
    op.create_index('ix_ai_requests_provider_task_id', 'ai_requests', ['provider_task_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_ai_requests_provider_task_id', table_name='ai_requests')
    op.drop_column('ai_requests', 'provider_task_id')
    op.drop_column('model_configs', 'duration_seconds')
    op.drop_column('model_configs', 'piapi_extra_input')
    op.drop_column('model_configs', 'piapi_task_type')
    op.drop_column('model_configs', 'piapi_model')
    # Postgres has no ALTER TYPE ... DROP VALUE -- enum values from upgrade() are left in place.
