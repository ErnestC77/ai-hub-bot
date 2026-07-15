"""add model_options -- опции качества/длительности/звука, задаваемые моделью.

Наборы значений диктует провайдер и они несводимы между моделями, поэтому
provider_params -- JSONB, а не колонки. Частичный уникальный индекс гарантирует
ровно один дефолт на (модель, вид): без него «дефолтная комбинация», от которой
считается recommended_credits, была бы неоднозначной.

Revision ID: c3d4e5f6a9b0
Revises: b2c3d4e5f6a8
Create Date: 2026-07-15 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d4e5f6a9b0'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'model_options',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.Enum('quality', 'duration', 'audio', name='modeloptionkind'), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('label', sa.String(length=64), nullable=False),
        sa.Column('provider_params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('credits_multiplier', sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['model_id'], ['ai_models.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_id', 'kind', 'code', name='uq_model_option_code'),
    )
    op.create_index(op.f('ix_model_options_model_id'), 'model_options', ['model_id'])
    # По нему читает GET /api/models.
    op.create_index('ix_model_options_lookup', 'model_options', ['model_id', 'kind', 'sort_order'])
    # Ровно один дефолт на (модель, вид) -- констрейнтом, а не соглашением.
    op.execute(
        "CREATE UNIQUE INDEX uq_model_option_default ON model_options (model_id, kind) "
        "WHERE is_default"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_model_option_default")
    op.drop_index('ix_model_options_lookup', table_name='model_options')
    op.drop_index(op.f('ix_model_options_model_id'), table_name='model_options')
    op.drop_table('model_options')
    sa.Enum(name='modeloptionkind').drop(op.get_bind(), checkfirst=True)
