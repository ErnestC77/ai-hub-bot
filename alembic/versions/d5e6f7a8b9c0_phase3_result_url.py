"""phase3: add ai_requests.result_url (nullable String(1024)) -- durable storage
for the fal.ai generation result URL. Credits are already charged when the
webhook delivers the result, so the URL must survive Redis restarts/TTL.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_requests', sa.Column('result_url', sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column('ai_requests', 'result_url')
