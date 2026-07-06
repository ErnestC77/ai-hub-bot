"""add banners table

Revision ID: 749f76e9eaca
Revises: daeb47a355de
Create Date: 2026-07-06 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '749f76e9eaca'
down_revision: Union[str, None] = 'daeb47a355de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'banners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('subtitle', sa.String(length=200), nullable=True),
        sa.Column('badge_text', sa.String(length=50), nullable=True),
        sa.Column('cta_text', sa.String(length=50), nullable=False),
        sa.Column('image_url', sa.String(length=500), nullable=False),
        sa.Column('action_type', sa.String(length=20), nullable=False),
        sa.Column('action_value', sa.String(length=500), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('banners')
