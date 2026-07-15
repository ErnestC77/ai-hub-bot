"""add nano_banana_pro -- модель из дизайн-макета с настоящим селектором 1K/2K/4K.

fal-ai/nano-banana-pro (Gemini 3 Pro Image) существует, имеет /edit-маршрут и
resolution=["1K","2K","4K"] в схеме -- ровно тот селектор, который рисовал
дизайн-макет и который более ранний спек объявил нереализуемым внутри каталога.
Цена измерена живым fal 2026-07-15: 1K=$0.15 -> 345 кредитов (usd*2300).

Revision ID: e5f6a9b0c1d2
Revises: c3d4e5f6a9b0
Create Date: 2026-07-15 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a9b0c1d2'
down_revision: Union[str, None] = 'c3d4e5f6a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "INSERT INTO ai_models (provider, category, code, display_name, provider_model_id, "
        "provider_model_id_edit, tier, cost_unit, input_price_usd_per_1m_tokens, "
        "output_price_usd_per_1m_tokens, fixed_cost_usd, min_credits, recommended_credits, "
        "max_context_tokens, is_active, is_visible, sort_order) "
        "VALUES ('fal', 'image', 'nano_banana_pro', 'Nano Banana Pro', 'fal-ai/nano-banana-pro', "
        "'fal-ai/nano-banana-pro/edit', 'pro', 'image', 0, 0, 0, 345, 345, 4000, true, true, 165) "
        "ON CONFLICT (code) DO NOTHING"
    ))


def downgrade() -> None:
    op.execute("DELETE FROM ai_models WHERE code = 'nano_banana_pro'")
