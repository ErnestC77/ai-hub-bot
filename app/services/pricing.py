"""Чистые функции расчёта кредитов (формулы 1:1 из ТЗ). Никаких DB-записей --
настройки передаются снаружи (см. app/services/settings_service.py)."""

import math
from dataclasses import dataclass

from app.db.enums import CostUnit
from app.db.models import AiModel

IMAGE_EDIT_MULTIPLIER = 1.5
IMAGE_EDIT_MIN_CREDITS = 100
VIDEO_MIN_CREDITS = 500
VIDEO_BASE_SECONDS = 5  # recommended_credits видео-моделей заданы "за 5 секунд"


@dataclass(frozen=True)
class PricingSettings:
    """Снимок бизнес-настроек из таблицы settings. Дефолты = стартовый сид
    (защита от пустой БД до первого сида)."""

    usd_to_rub_rate: float = 80.0
    rub_per_credit: float = 0.10
    provider_fee_multiplier: float = 1.15
    margin_multiplier: float = 2.5
    minimum_text_credits: int = 3


def calculate_text_credits(
    model: AiModel, input_tokens: int, output_tokens: int, *, settings: PricingSettings
) -> int:
    # Шаги 1-8 из ТЗ.
    input_cost_usd = input_tokens / 1_000_000 * float(model.input_price_usd_per_1m_tokens)
    output_cost_usd = output_tokens / 1_000_000 * float(model.output_price_usd_per_1m_tokens)
    api_cost_usd = input_cost_usd + output_cost_usd
    api_cost_rub = api_cost_usd * settings.usd_to_rub_rate
    gross_cost_rub = api_cost_rub * settings.provider_fee_multiplier
    user_price_rub = gross_cost_rub * settings.margin_multiplier
    credits = math.ceil(user_price_rub / settings.rub_per_credit)
    return max(credits, model.min_credits, settings.minimum_text_credits)


def calculate_image_credits(
    model: AiModel, quantity: int, megapixels: float, *, is_edit: bool = False
) -> int:
    if model.cost_unit == CostUnit.image:
        credits = quantity * model.recommended_credits
    elif model.cost_unit == CostUnit.megapixel:
        credits = math.ceil(quantity * megapixels * model.recommended_credits)
    else:
        raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для image")
    credits = max(credits, model.min_credits)
    if is_edit:
        credits = max(math.ceil(credits * IMAGE_EDIT_MULTIPLIER), IMAGE_EDIT_MIN_CREDITS)
    return credits


def calculate_video_credits(model: AiModel, duration_seconds: int) -> int:
    if model.cost_unit == CostUnit.second:
        credits = math.ceil(duration_seconds / VIDEO_BASE_SECONDS * model.recommended_credits)
    elif model.cost_unit == CostUnit.video:
        credits = model.recommended_credits
    else:
        raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для video")
    return max(credits, model.min_credits, VIDEO_MIN_CREDITS)
