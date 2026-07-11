import pytest

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.pricing import (
    PricingSettings,
    calculate_api_cost_usd,
    calculate_image_api_cost_usd,
    calculate_image_credits,
    calculate_text_credits,
    calculate_video_api_cost_usd,
    calculate_video_credits,
)

SETTINGS = PricingSettings()  # дефолты = стартовые settings из ТЗ


def _text_model(input_price: float, output_price: float, min_credits: int) -> AiModel:
    return AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text, code="m",
        display_name="M", provider_model_id="x/m", tier=ModelTier.standard,
        input_price_usd_per_1m_tokens=input_price, output_price_usd_per_1m_tokens=output_price,
        cost_unit=CostUnit.tokens, min_credits=min_credits, recommended_credits=min_credits,
    )


def _media_model(cost_unit: CostUnit, recommended: int, min_credits: int,
                 category: ModelCategory = ModelCategory.image,
                 fixed_cost_usd: float = 0.0) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=category, code="m",
        display_name="M", provider_model_id="fal-ai/m", tier=ModelTier.standard,
        input_price_usd_per_1m_tokens=0, output_price_usd_per_1m_tokens=0,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
        fixed_cost_usd=fixed_cost_usd,
    )


# --- calculate_text_credits: формула шагов 1-8 из ТЗ ---

def test_text_formula_steps_1_to_8():
    # apiCostUsd = 2000/1e6*3 + 1000/1e6*15 = 0.021; rub = 0.021*80 = 1.68;
    # gross = 1.68*1.15 = 1.932; user = 1.932*2.5 = 4.83; ceil(4.83/0.10) = 49.
    model = _text_model(input_price=3.0, output_price=15.0, min_credits=5)
    assert calculate_text_credits(model, 2000, 1000, settings=SETTINGS) == 49


def test_text_ceil_rounds_up():
    # apiCostUsd = 1043/1e6*10 = 0.01043; user = 0.01043*80*1.15*2.5 = 2.39890 rub;
    # /0.10 = 23.989 -> ceil = 24.
    model = _text_model(input_price=10.0, output_price=0.0, min_credits=1)
    assert calculate_text_credits(model, 1043, 0, settings=SETTINGS) == 24


def test_text_model_min_credits_floor():
    # Сырые credits = 1, но model.min_credits = 5 форсирует минимум.
    model = _text_model(input_price=0.1, output_price=0.0, min_credits=5)
    assert calculate_text_credits(model, 100, 0, settings=SETTINGS) == 5


def test_text_global_minimum_text_credits_floor():
    # Нулевая цена -> 0 кредитов, но глобальный minimum_text_credits = 3.
    model = _text_model(input_price=0.0, output_price=0.0, min_credits=1)
    assert calculate_text_credits(model, 500, 500, settings=SETTINGS) == 3


def test_text_uses_settings_overrides():
    model = _text_model(input_price=3.0, output_price=15.0, min_credits=5)
    doubled = PricingSettings(usd_to_rub_rate=160.0)
    # Тот же расчёт, но курс x2: 4.83*2 = 9.66 rub -> ceil(96.6) = 97.
    assert calculate_text_credits(model, 2000, 1000, settings=doubled) == 97


# --- calculate_image_credits ---

def test_image_cost_unit_image_multiplies_quantity():
    model = _media_model(CostUnit.image, recommended=75, min_credits=75)
    assert calculate_image_credits(model, quantity=2, megapixels=1.0) == 150


def test_image_cost_unit_megapixel_ceils():
    # 1 * 1.25 MP * 50 = 62.5 -> ceil = 63 (1.25 точно представимо в float).
    model = _media_model(CostUnit.megapixel, recommended=50, min_credits=50)
    assert calculate_image_credits(model, quantity=1, megapixels=1.25) == 63


def test_image_megapixel_respects_model_min_credits():
    # 1 * 0.5 MP * 50 = 25 < min_credits 50 -> 50.
    model = _media_model(CostUnit.megapixel, recommended=50, min_credits=50)
    assert calculate_image_credits(model, quantity=1, megapixels=0.5) == 50


def test_image_edit_multiplier_with_minimum_100():
    # base 50 -> x1.5 = 75 -> но минимум image edit = 100.
    model = _media_model(CostUnit.image, recommended=50, min_credits=50)
    assert calculate_image_credits(model, quantity=1, megapixels=1.0, is_edit=True) == 100


def test_image_edit_multiplier_above_minimum():
    # base 100 -> x1.5 = 150 > 100.
    model = _media_model(CostUnit.image, recommended=100, min_credits=100)
    assert calculate_image_credits(model, quantity=1, megapixels=1.0, is_edit=True) == 150


def test_image_rejects_non_image_cost_unit():
    model = _media_model(CostUnit.tokens, recommended=50, min_credits=50)
    with pytest.raises(ValueError):
        calculate_image_credits(model, quantity=1, megapixels=1.0)


# --- calculate_video_credits ---

def test_video_cost_unit_second_scales_by_duration():
    # ceil(7/5 * 600) = ceil(840.0) = 840.
    model = _media_model(CostUnit.second, recommended=600, min_credits=600, category=ModelCategory.video)
    assert calculate_video_credits(model, duration_seconds=7) == 840


def test_video_short_duration_floors_to_model_min():
    # ceil(3/5 * 600) = 360 < min_credits 600 -> 600.
    model = _media_model(CostUnit.second, recommended=600, min_credits=600, category=ModelCategory.video)
    assert calculate_video_credits(model, duration_seconds=3) == 600


def test_video_cost_unit_video_is_flat():
    model = _media_model(CostUnit.video, recommended=500, min_credits=500, category=ModelCategory.video)
    assert calculate_video_credits(model, duration_seconds=30) == 500


def test_video_global_minimum_500():
    # recommended 300, min_credits 0 -> глобальный минимум видео 500.
    model = _media_model(CostUnit.video, recommended=300, min_credits=0, category=ModelCategory.video)
    assert calculate_video_credits(model, duration_seconds=5) == 500


def test_video_rejects_non_video_cost_unit():
    model = _media_model(CostUnit.image, recommended=500, min_credits=500, category=ModelCategory.video)
    with pytest.raises(ValueError):
        calculate_video_credits(model, duration_seconds=5)


# --- calculate_api_cost_usd (text, фаза 6) ---

def test_api_cost_usd_sums_input_and_output():
    # 2000/1e6*3 + 1000/1e6*15 = 0.006 + 0.015 = 0.021 -- шаги 1-2 ТЗ, без RUB/кредитов.
    model = _text_model(input_price=3.0, output_price=15.0, min_credits=5)
    assert calculate_api_cost_usd(model, 2000, 1000) == pytest.approx(0.021)


def test_api_cost_usd_zero_tokens_is_zero():
    model = _text_model(input_price=3.0, output_price=15.0, min_credits=5)
    assert calculate_api_cost_usd(model, 0, 0) == 0.0


def test_api_cost_usd_ignores_min_credits_and_multipliers():
    # min_credits=50 НЕ влияет: это НАША себестоимость, не цена пользователя.
    model = _text_model(input_price=0.1, output_price=0.0, min_credits=50)
    assert calculate_api_cost_usd(model, 100, 0) == pytest.approx(0.00001)


# --- calculate_image_api_cost_usd (фаза 6) ---

def test_image_api_cost_unit_image_multiplies_quantity():
    model = _media_model(CostUnit.image, recommended=75, min_credits=75, fixed_cost_usd=0.04)
    assert calculate_image_api_cost_usd(model, quantity=2, megapixels=1.0) == pytest.approx(0.08)


def test_image_api_cost_unit_megapixel_scales_without_ceil():
    # 1 * 1.25 MP * 0.05 = 0.0625 -- себестоимость не округляется (в отличие от кредитов).
    model = _media_model(CostUnit.megapixel, recommended=50, min_credits=50, fixed_cost_usd=0.05)
    assert calculate_image_api_cost_usd(model, quantity=1, megapixels=1.25) == pytest.approx(0.0625)


def test_image_api_cost_ignores_min_credits():
    # min_credits-пол существует только для кредитов, не для USD-себестоимости.
    model = _media_model(CostUnit.megapixel, recommended=50, min_credits=50, fixed_cost_usd=0.05)
    assert calculate_image_api_cost_usd(model, quantity=1, megapixels=0.5) == pytest.approx(0.025)


def test_image_api_cost_rejects_non_image_cost_unit():
    model = _media_model(CostUnit.tokens, recommended=50, min_credits=50, fixed_cost_usd=0.05)
    with pytest.raises(ValueError):
        calculate_image_api_cost_usd(model, quantity=1, megapixels=1.0)


# --- calculate_video_api_cost_usd (фаза 6) ---

def test_video_api_cost_unit_second_scales_by_duration():
    # 7/5 * 0.5 = 0.7 -- fixed_cost_usd задан "за VIDEO_BASE_SECONDS", как recommended_credits.
    model = _media_model(CostUnit.second, recommended=600, min_credits=600,
                         category=ModelCategory.video, fixed_cost_usd=0.5)
    assert calculate_video_api_cost_usd(model, duration_seconds=7) == pytest.approx(0.7)


def test_video_api_cost_unit_video_is_flat():
    model = _media_model(CostUnit.video, recommended=500, min_credits=500,
                         category=ModelCategory.video, fixed_cost_usd=1.2)
    assert calculate_video_api_cost_usd(model, duration_seconds=30) == pytest.approx(1.2)


def test_video_api_cost_rejects_non_video_cost_unit():
    model = _media_model(CostUnit.image, recommended=500, min_credits=500,
                         category=ModelCategory.video, fixed_cost_usd=1.2)
    with pytest.raises(ValueError):
        calculate_video_api_cost_usd(model, duration_seconds=5)
