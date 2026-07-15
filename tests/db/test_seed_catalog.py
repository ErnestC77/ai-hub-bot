import math
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider
from app.db.models import AiModel, CreditPackage, Setting
from app.db.seed import AI_MODELS, CREDIT_PACKAGES, SETTINGS_ROWS, apply_seed


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def test_settings_rows_with_spec_values():
    values = {row["key"]: row["value"] for row in SETTINGS_ROWS}
    assert values == {
        # pricing (фазы 1-4)
        "usd_to_rub_rate": "80",
        "rub_per_credit": "0.10",
        "provider_fee_multiplier": "1.15",
        "margin_multiplier": "2.5",
        "minimum_text_credits": "3",
        # antifraud (фаза 5)
        "daily_spend_limit_credits": "10000",
        "rate_limit_per_user_per_minute": "10",
        "rate_limit_per_model_per_minute": "60",
        "duplicate_cooldown_seconds": "5",
        "free_tier_credit_cap": "100",
    }
    assert all(row["type"] == "int" for row in SETTINGS_ROWS
               if row["key"] in {"daily_spend_limit_credits", "rate_limit_per_user_per_minute",
                                 "rate_limit_per_model_per_minute", "duplicate_cooldown_seconds",
                                 "free_tier_credit_cap"})


def test_five_packages_from_tz():
    by_code = {p["code"]: p for p in CREDIT_PACKAGES}
    assert set(by_code) == {"start", "basic", "plus", "pro", "business"}
    assert (by_code["start"]["credits"], by_code["start"]["price_rub"]) == (1000, 149)
    assert (by_code["basic"]["credits"], by_code["basic"]["price_rub"]) == (5000, 599)
    assert (by_code["plus"]["credits"], by_code["plus"]["price_rub"]) == (12000, 1290)
    assert (by_code["pro"]["credits"], by_code["pro"]["price_rub"]) == (30000, 2990)
    assert (by_code["business"]["credits"], by_code["business"]["price_rub"]) == (70000, 5990)
    assert by_code["start"]["price_stars"] == 75
    assert by_code["basic"]["price_stars"] == 300
    assert by_code["plus"]["price_stars"] == 645
    assert by_code["pro"]["price_stars"] == 1495
    assert by_code["business"]["price_stars"] == 2995


def test_twenty_models_split_12_text_4_image_4_video():
    assert len(AI_MODELS) == 20
    by_category = {}
    for row in AI_MODELS:
        by_category.setdefault(row["category"], []).append(row)
    assert len(by_category[ModelCategory.text]) == 12
    assert len(by_category[ModelCategory.image]) == 4
    assert len(by_category[ModelCategory.video]) == 4

    for row in by_category[ModelCategory.text]:
        assert row["provider"] == ModelProvider.openrouter
        assert row["cost_unit"] == CostUnit.tokens
    for row in by_category[ModelCategory.image] + by_category[ModelCategory.video]:
        assert row["provider"] == ModelProvider.fal


def test_model_codes_and_credit_floors_match_tz():
    """Медиа-цены = формула проекта: credits = usd * 2300
    (usd -> *80 руб -> *1.15 комиссия -> *2.5 маржа -> /0.10 руб за кредит).
    Себестоимость измерена живыми генерациями fal 2026-07-15, см. спек.

    recommended_credits -- цена ДЕФОЛТНОЙ комбинации параметров модели.
    min_credits -- цена самой дешёвой (пол не должен отрезать дешёвые опции).
    """
    by_code = {m["code"]: m for m in AI_MODELS}
    expected = {
        # code: (min_credits, recommended_credits)
        "deepseek_v3": (3, 3), "llama_3_1_8b": (3, 3), "qwen_plus": (3, 6), "mistral_large": (3, 6),
        "gpt_mini": (5, 6), "qwen_max": (10, 15), "grok": (10, 15),
        "gpt_premium": (20, 30), "gemini_flash": (20, 30), "gemini_pro": (30, 40),
        "claude_sonnet": (40, 50), "claude_opus": (70, 90),
        "qwen_image": (50, 50), "seedream": (75, 75), "flux_kontext_pro": (100, 100), "nano_banana": (100, 100),
        # ovi: $0.20 плоско -> 460, в сиде 500 (округление вверх, сходится)
        "ovi_video": (500, 500),
        # wan: 480p $0.04/с * 5.0625с ($0.2025 измерено) -> 466 = пол;
        #      720p (дефолт) $0.08/с * 5.0625с = $0.405 -> 932
        "wan_video": (466, 932),
        # kling: $1.40 за 5с (измерено) -> 3220; дешевле 5с не бывает, пол = цене
        "kling_video": (3220, 3220),
        # veo: дефолт 8с со звуком $0.40/с = $3.20 -> 7360;
        #      дешевле всего 4с без звука $0.20/с = $0.80 -> 1840 = пол
        "veo_video": (1840, 7360),
    }
    assert set(by_code) == set(expected)
    for code, (min_c, rec_c) in expected.items():
        assert by_code[code]["min_credits"] == min_c, code
        assert by_code[code]["recommended_credits"] == rec_c, code


def test_media_prices_follow_the_project_formula():
    """Страховка от 'поправлю число руками': каждая медиа-цена должна получаться
    из измеренной себестоимости той же формулой, что и текстовые."""
    CREDITS_PER_USD = 80 * 1.15 * 2.5 / 0.10  # = 2300
    by_code = {m["code"]: m for m in AI_MODELS}
    measured_usd = {          # измерено списанием с баланса fal 2026-07-15
        "qwen_image": 0.02,   # за 1.05 МП
        "ovi_video": 0.20,    # плоско за видео (по докам, не мерили)
        "wan_video": 0.405,   # 720p: $0.08/с * 5.0625с (480p измерен как $0.2025)
        "kling_video": 1.40,  # 5с
        "veo_video": 3.20,    # 8с со звуком: $0.40/с
    }
    for code, usd in measured_usd.items():
        expected = math.ceil(usd * CREDITS_PER_USD)
        actual = by_code[code]["recommended_credits"]
        # ovi/qwen округлены вверх до круглого числа при первичном сиде -- допускаем +10%
        assert actual >= expected, f"{code}: {actual} < {expected} -- продаём ниже формулы"
        assert actual <= expected * 1.1, f"{code}: {actual} сильно выше {expected}"


def test_media_cost_units_match_tz():
    by_code = {m["code"]: m for m in AI_MODELS}
    assert by_code["qwen_image"]["cost_unit"] == CostUnit.megapixel
    assert by_code["seedream"]["cost_unit"] == CostUnit.image
    assert by_code["flux_kontext_pro"]["cost_unit"] == CostUnit.image
    assert by_code["nano_banana"]["cost_unit"] == CostUnit.image
    assert by_code["ovi_video"]["cost_unit"] == CostUnit.video
    assert by_code["wan_video"]["cost_unit"] == CostUnit.second
    assert by_code["kling_video"]["cost_unit"] == CostUnit.second
    assert by_code["veo_video"]["cost_unit"] == CostUnit.second


async def test_apply_seed_inserts_and_is_idempotent(session):
    await apply_seed(session)
    await apply_seed(session)  # повторный прогон не должен дублировать строки

    models = (await session.execute(select(func.count()).select_from(AiModel))).scalar_one()
    packages = (await session.execute(select(func.count()).select_from(CreditPackage))).scalar_one()
    settings_count = (await session.execute(select(func.count()).select_from(Setting))).scalar_one()
    assert models == 20
    assert packages == 5
    assert settings_count == 10


def test_fallback_pairs_from_phase2_spec():
    by_code = {m["code"]: m for m in AI_MODELS}
    assert by_code["gpt_premium"]["fallback_model_code"] == "gemini_flash"
    assert by_code["claude_opus"]["fallback_model_code"] == "claude_sonnet"
    with_fallback = {m["code"] for m in AI_MODELS if m.get("fallback_model_code")}
    assert with_fallback == {"gpt_premium", "claude_opus"}


async def test_fallback_column_roundtrips_through_orm(session):
    await apply_seed(session)
    row = (
        await session.execute(select(AiModel).where(AiModel.code == "gpt_premium"))
    ).scalar_one()
    assert row.fallback_model_code == "gemini_flash"
    deepseek = (
        await session.execute(select(AiModel).where(AiModel.code == "deepseek_v3"))
    ).scalar_one()
    assert deepseek.fallback_model_code is None


def test_media_provider_model_ids_are_real_fal_endpoints():
    """Проверено 2026-07-15 запросом схемы fal (openapi.json?endpoint_id=...):
    200 = эндпоинт есть, 404 = нет. Старые id (wan/v2.2, kling-video/v2) очередь
    принимает, но воркер роняет с 'Path /v2.2 not found' -- это хуже честного 404.
    """
    by_code = {m["code"]: m for m in AI_MODELS}
    assert by_code["qwen_image"]["provider_model_id"] == "fal-ai/qwen-image"
    assert by_code["seedream"]["provider_model_id"] == "fal-ai/bytedance/seedream/v4/text-to-image"
    assert by_code["flux_kontext_pro"]["provider_model_id"] == "fal-ai/flux-pro/kontext/text-to-image"
    assert by_code["nano_banana"]["provider_model_id"] == "fal-ai/nano-banana"
    assert by_code["ovi_video"]["provider_model_id"] == "fal-ai/ovi"
    assert by_code["wan_video"]["provider_model_id"] == "fal-ai/wan/v2.2-a14b/text-to-video"
    assert by_code["kling_video"]["provider_model_id"] == "fal-ai/kling-video/v2/master/text-to-video"
    assert by_code["veo_video"]["provider_model_id"] == "fal-ai/veo3.1"


def test_no_deprecated_fal_endpoints():
    """fal пометил seedream/v3 и veo3 как 'no longer supported'. Оба ещё отвечают,
    но 2K/4K есть только у преемников -- см. спек, раздел 'Разрешения'."""
    ids = {m.get("provider_model_id", "") for m in AI_MODELS}
    assert not any("seedream/v3" in i for i in ids)
    assert not any(i == "fal-ai/veo3" for i in ids)
