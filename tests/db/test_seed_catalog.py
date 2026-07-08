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


def test_five_settings_rows_with_spec_values():
    values = {row["key"]: row["value"] for row in SETTINGS_ROWS}
    assert values == {
        "usd_to_rub_rate": "80",
        "rub_per_credit": "0.10",
        "provider_fee_multiplier": "1.15",
        "margin_multiplier": "2.5",
        "minimum_text_credits": "3",
    }


def test_five_packages_from_tz():
    by_code = {p["code"]: p for p in CREDIT_PACKAGES}
    assert set(by_code) == {"start", "basic", "plus", "pro", "business"}
    assert (by_code["start"]["credits"], by_code["start"]["price_rub"]) == (1000, 149)
    assert (by_code["basic"]["credits"], by_code["basic"]["price_rub"]) == (5000, 599)
    assert (by_code["plus"]["credits"], by_code["plus"]["price_rub"]) == (12000, 1290)
    assert (by_code["pro"]["credits"], by_code["pro"]["price_rub"]) == (30000, 2990)
    assert (by_code["business"]["credits"], by_code["business"]["price_rub"]) == (70000, 5990)


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
    by_code = {m["code"]: m for m in AI_MODELS}
    expected = {
        # code: (min_credits, recommended_credits)
        "deepseek_v3": (3, 3), "llama_3_1_8b": (3, 3), "qwen_plus": (3, 6), "mistral_large": (3, 6),
        "gpt_mini": (5, 6), "qwen_max": (10, 15), "grok": (10, 15),
        "gpt_premium": (20, 30), "gemini_flash": (20, 30), "gemini_pro": (30, 40),
        "claude_sonnet": (40, 50), "claude_opus": (70, 90),
        "qwen_image": (50, 50), "seedream": (75, 75), "flux_kontext_pro": (100, 100), "nano_banana": (100, 100),
        "ovi_video": (500, 500), "wan_video": (600, 600), "kling_video": (850, 850), "veo_video": (4800, 4800),
    }
    assert set(by_code) == set(expected)
    for code, (min_c, rec_c) in expected.items():
        assert by_code[code]["min_credits"] == min_c, code
        assert by_code[code]["recommended_credits"] == rec_c, code


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
    assert settings_count == 5
