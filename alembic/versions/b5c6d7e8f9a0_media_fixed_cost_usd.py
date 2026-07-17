"""media fixed_cost_usd for cost telemetry

fixed_cost_usd у медиа-моделей был 0 -> provider_cost_usd в AIRequest всегда 0,
админ-дашборд маржи бесполезен (аудит pricing I3). Значения = recommended_credits
/ 1314 (обратный расчёт из цены -> провайдерская себестоимость консистентна с
прайсингом). Для video (cost_unit=second) -- цена за 5с.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-17
"""

from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None

_COSTS = {
    "qwen_image": 0.0221, "seedream": 0.0327, "flux_kontext_pro": 0.0441,
    "nano_banana": 0.0441, "nano_banana_pro": 0.1507, "ovi_video": 0.2177,
    "wan_video": 0.4056, "kling_video": 1.4003, "veo_video": 2.0006,
}


def upgrade() -> None:
    for code, cost in _COSTS.items():
        op.execute(f"UPDATE ai_models SET fixed_cost_usd = {cost} WHERE code = '{code}'")


def downgrade() -> None:
    for code in _COSTS:
        op.execute(f"UPDATE ai_models SET fixed_cost_usd = 0 WHERE code = '{code}'")
