"""Чистые функции расчёта кредитов (формулы 1:1 из ТЗ). Никаких DB-записей --
настройки передаются снаружи (см. app/services/settings_service.py)."""

import math
from dataclasses import dataclass

from app.db.enums import CostUnit
from app.db.models import AiModel

IMAGE_EDIT_MULTIPLIER = 1.5
IMAGE_EDIT_MIN_CREDITS = 100
VIDEO_MIN_CREDITS = 500


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
    model: AiModel, quantity: int, megapixels: float, *, is_edit: bool = False,
    options_multiplier: float = 1.0,
) -> int:
    if model.cost_unit == CostUnit.image:
        credits = quantity * model.recommended_credits
    elif model.cost_unit == CostUnit.megapixel:
        credits = math.ceil(quantity * megapixels * model.recommended_credits)
    else:
        raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для image")
    # Множитель опций -- ДО минимумов (см. ниже).
    credits = math.ceil(credits * options_multiplier)
    credits = max(credits, model.min_credits)
    if is_edit:
        credits = max(math.ceil(credits * IMAGE_EDIT_MULTIPLIER), IMAGE_EDIT_MIN_CREDITS)
    return credits


def calculate_video_credits(model: AiModel, *, options_multiplier: float = 1.0) -> int:
    """recommended_credits -- цена ДЕФОЛТНОЙ комбинации опций модели.
    Длительность больше не параметр формулы: её задаёт опция, и её же множитель
    выражает разницу в цене. Прежнее `duration/5` было неверным вдвойне --
    5 секунд не производит ни одна модель каталога (Kling умеет 5 или 10,
    Veo 4/6/8, Wan считает кадрами, Ovi не управляется), а у Wan и Ovi
    длительность вообще не уходила провайдеру: юзер платил за 15с и получал 5.
    """
    credits = math.ceil(model.recommended_credits * options_multiplier)
    return max(credits, model.min_credits, VIDEO_MIN_CREDITS)


def calculate_api_cost_usd(model: AiModel, input_tokens: int, output_tokens: int) -> float:
    """Реальная себестоимость запроса в USD -- те же цены модели, что и в
    calculate_text_credits (шаги 1-2 ТЗ), но без конвертации в рубли/кредиты
    и без применения provider_fee_multiplier/margin_multiplier (это НАША
    внутренняя себестоимость, не то, что платит пользователь)."""
    input_cost_usd = input_tokens / 1_000_000 * float(model.input_price_usd_per_1m_tokens)
    output_cost_usd = output_tokens / 1_000_000 * float(model.output_price_usd_per_1m_tokens)
    return input_cost_usd + output_cost_usd


def calculate_image_api_cost_usd(model: AiModel, quantity: int, megapixels: float) -> float:
    """Себестоимость image-генерации в USD -- структура 1:1 с
    calculate_image_credits, но fixed_cost_usd вместо recommended_credits."""
    if model.cost_unit == CostUnit.image:
        return quantity * float(model.fixed_cost_usd)
    if model.cost_unit == CostUnit.megapixel:
        return quantity * megapixels * float(model.fixed_cost_usd)
    raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для image")


def calculate_video_api_cost_usd(model: AiModel, duration_seconds: int) -> float:
    """Себестоимость video-генерации в USD -- реальная цена провайдера, не
    трогается этой задачей (в отличие от calculate_video_credits). fixed_cost_usd
    для cost_unit=second задан провайдером буквально "за 5 секунд" -- это факт
    о биллинге API, а не про кредитную формулу выше, поэтому здесь остаётся
    литералом 5, а не общей константой уровня модуля (прежняя такая константа
    удалена вместе с её больше-не-верным комментарием про recommended_credits)."""
    if model.cost_unit == CostUnit.second:
        return duration_seconds / 5 * float(model.fixed_cost_usd)
    if model.cost_unit == CostUnit.video:
        return float(model.fixed_cost_usd)
    raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для video")
