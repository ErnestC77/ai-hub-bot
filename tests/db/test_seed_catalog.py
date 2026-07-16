import math
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelOptionKind, ModelProvider
from app.db.models import AiModel, CreditPackage, ModelOption, Setting
from app.db.seed import AI_MODELS, CREDIT_PACKAGES, MODEL_OPTIONS, SETTINGS_ROWS, apply_seed


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


def test_catalog_split_12_text_5_image_4_video():
    assert len(AI_MODELS) == 21
    by_category = {}
    for row in AI_MODELS:
        by_category.setdefault(row["category"], []).append(row)
    assert len(by_category[ModelCategory.text]) == 12
    assert len(by_category[ModelCategory.image]) == 5
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
        "nano_banana_pro": (345, 345),
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
        "nano_banana_pro": 0.15,  # дефолт 1K (2K по той же цене, 4K -- $0.30)
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


def test_nano_banana_pro_in_catalog():
    """Модель из дизайн-макета: у неё resolution=["1K","2K","4K"] -- ровно тот
    селектор, который рисовал дизайнер. Цена измерена живым fal 2026-07-15:
    1K=$0.15 -> 345 кредитов по формуле usd*2300."""
    by_code = {m["code"]: m for m in AI_MODELS}
    pro = by_code["nano_banana_pro"]
    assert pro["provider_model_id"] == "fal-ai/nano-banana-pro"
    assert pro["provider_model_id_edit"] == "fal-ai/nano-banana-pro/edit"
    assert pro["category"] == ModelCategory.image
    assert pro["cost_unit"] == CostUnit.image
    assert (pro["min_credits"], pro["recommended_credits"]) == (345, 345)
    # вчетверо дороже обычной ($0.15 против $0.0398) -- цена, а не вкус
    assert pro["recommended_credits"] > by_code["nano_banana"]["recommended_credits"] * 3


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
    assert models == 21
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


def test_edit_endpoints_for_image_models_that_have_them():
    """У flux-pro/kontext и nano-banana t2i и i2i -- разные маршруты fal.
    Голый fal-ai/flux-pro/kontext требует image_url (required по схеме),
    поэтому как t2i он падает; а /text-to-image не принимает image_url.
    """
    by_code = {m["code"]: m for m in AI_MODELS}
    assert by_code["flux_kontext_pro"]["provider_model_id_edit"] == "fal-ai/flux-pro/kontext"
    assert by_code["nano_banana"]["provider_model_id_edit"] == "fal-ai/nano-banana/edit"
    # у остальных развилки нет
    assert by_code["qwen_image"].get("provider_model_id_edit") is None
    assert by_code["seedream"].get("provider_model_id_edit") is None


async def test_edit_column_roundtrips_through_orm(session):
    await apply_seed(session)
    row = (
        await session.execute(select(AiModel).where(AiModel.code == "flux_kontext_pro"))
    ).scalar_one()
    assert row.provider_model_id_edit == "fal-ai/flux-pro/kontext"
    qwen = (
        await session.execute(select(AiModel).where(AiModel.code == "qwen_image"))
    ).scalar_one()
    assert qwen.provider_model_id_edit is None


def test_migration_values_match_seed_constants():
    """Миграция чинит существующие строки, сид -- чистую БД. Если они разъедутся,
    прод и тесты будут жить в разных каталогах. Здесь ловим расхождение.
    """
    from pathlib import Path

    path = Path("alembic/versions/a1b2c3d4e5f6_fix_fal_catalog_endpoints_and_prices.py")
    text = path.read_text(encoding="utf-8")
    by_code = {m["code"]: m for m in AI_MODELS}

    for code in ("wan_video", "kling_video", "veo_video", "seedream", "flux_kontext_pro"):
        assert by_code[code]["provider_model_id"] in text, f"{code}: эндпоинт из сида не найден в миграции"
    for code in ("wan_video", "kling_video", "veo_video"):
        assert str(by_code[code]["recommended_credits"]) in text, f"{code}: цена из сида не найдена в миграции"


def test_option_multipliers_follow_measured_provider_costs():
    """Множители выведены из замеров живого fal 2026-07-15, а не назначены:
      kling  10с $2.80 / 5с $1.40         -> 2.0
      veo    без звука $0.20/с / со звуком $0.40/с -> 0.5
      veo    4с / 8с                       -> 0.5;  6с / 8с -> 0.75
      wan    480p $0.04/с / 720p $0.08/с   -> 0.5;  580p $0.06 -> 0.75
      qwen   2048^2 = 4.19 МП / 1024^2 = 1.05 МП -> 4.0
    """
    by = {(o["model_code"], o["kind"], o["code"]): o for o in MODEL_OPTIONS}
    assert by[("kling_video", ModelOptionKind.duration, "10s")]["credits_multiplier"] == 2.0
    assert by[("veo_video", ModelOptionKind.audio, "off")]["credits_multiplier"] == 0.5
    assert by[("veo_video", ModelOptionKind.duration, "4s")]["credits_multiplier"] == 0.5
    assert by[("wan_video", ModelOptionKind.quality, "480p")]["credits_multiplier"] == 0.5
    assert by[("qwen_image", ModelOptionKind.quality, "2k")]["credits_multiplier"] == 4.0


def test_exactly_one_default_per_model_and_kind():
    """recommended_credits каталога -- цена ДЕФОЛТНОЙ комбинации. Если дефолтов
    два или ноль, эта величина теряет смысл."""
    seen = {}
    for o in MODEL_OPTIONS:
        if o.get("is_default"):
            key = (o["model_code"], o["kind"])
            assert key not in seen, f"два дефолта: {key}"
            seen[key] = o
    kinds = {(o["model_code"], o["kind"]) for o in MODEL_OPTIONS}
    assert set(seen) == kinds, f"без дефолта: {kinds - set(seen)}"


def test_default_option_multiplier_is_one():
    """Дефолт стоит ровно recommended_credits -- значит его множитель 1.0,
    иначе каталог и опции разъедутся."""
    for o in MODEL_OPTIONS:
        if o.get("is_default"):
            assert o["credits_multiplier"] == 1.0, o["model_code"]


def test_no_options_for_models_without_provider_knobs():
    """У flux-pro/kontext, nano-banana и kling нет ручки размера (только
    aspect_ratio) -- опций качества у них быть не должно. У Ovi нет и длительности.
    Нарисовать контрол, которого провайдер не понимает, хуже, чем не рисовать."""
    codes_with_quality = {o["model_code"] for o in MODEL_OPTIONS
                          if o["kind"] == ModelOptionKind.quality}
    assert "flux_kontext_pro" not in codes_with_quality
    assert "nano_banana" not in codes_with_quality
    assert "kling_video" not in codes_with_quality
    codes_with_duration = {o["model_code"] for o in MODEL_OPTIONS
                           if o["kind"] == ModelOptionKind.duration}
    assert "ovi_video" not in codes_with_duration


def test_veo_resolution_multipliers_match_measurements():
    """Измерено 3 генерациями veo 4с без звука: 720p $0.80, 1080p $0.80, 4k $1.60.
    1080p БЕСПЛАТЕН -- ровно как 720p; дорожает только 4K, вдвое. Угадать это было
    нельзя: доки о разнице 720p/1080p молчат, а «три градации = три цены» неверно."""
    by = {o["code"]: o for o in MODEL_OPTIONS
          if o["model_code"] == "veo_video" and o["kind"] == ModelOptionKind.quality}
    assert by["720p"]["credits_multiplier"] == 1.0
    assert by["1080p"]["credits_multiplier"] == 1.0
    assert by["4k"]["credits_multiplier"] == 2.0


def test_nano_banana_pro_resolution_multipliers_match_measurements():
    """Селектор 1K/2K/4K из дизайн-макета -- на модели, для которой он и создан.
    Измерено: 1K $0.15, 2K $0.15, 4K $0.30. 2K БЕСПЛАТЕН.

    Этот тест защищает от «здравого смысла»: 1K/2K/4K -> 1/2/4 выглядит очевидно
    и означало бы вдвое лишнего с пользователя за каждую генерацию в 2K.
    """
    by = {o["code"]: o for o in MODEL_OPTIONS
          if o["model_code"] == "nano_banana_pro" and o["kind"] == ModelOptionKind.quality}
    assert set(by) == {"1k", "2k", "4k"}
    assert by["1k"]["credits_multiplier"] == 1.0
    assert by["2k"]["credits_multiplier"] == 1.0
    assert by["4k"]["credits_multiplier"] == 2.0


def test_seedream_resolution_is_free():
    """Измерено: square_hd + auto_2K + auto_4K = ровно $0.09 на троих, т.е. $0.03
    за картинку независимо от разрешения (cost_unit=image -- плоский тариф).
    Множители 1.0: 2K и 4K достаются пользователю даром."""
    by = {o["code"]: o for o in MODEL_OPTIONS
          if o["model_code"] == "seedream" and o["kind"] == ModelOptionKind.quality}
    assert set(by) == {"1k", "2k", "4k"}
    assert all(o["credits_multiplier"] == 1.0 for o in by.values())


def test_unmeasured_options_are_absent():
    """НЕ заводим то, чего не мерили. Опция с выдуманным множителем хуже
    отсутствующей -- она молча ошибётся в деньгах. Ovi: цена плоская, но влияние
    resolution не измеряли; длительность у него не управляется вовсе."""
    ovi = {o["code"] for o in MODEL_OPTIONS if o["model_code"] == "ovi_video"}
    assert ovi == set(), "влияние resolution на цену ovi не измерено"


async def test_apply_seed_inserts_options_and_is_idempotent(session):
    await apply_seed(session)
    await apply_seed(session)
    count = (await session.execute(select(func.count()).select_from(ModelOption))).scalar_one()
    assert count == len(MODEL_OPTIONS)


def test_option_migration_matches_seed_constants():
    """Миграция сида опций (`d4e5f6a9b0c1` в исходном плане переименован в
    `bb51258925d4`, т.к. `d4e5f6a9b0c1` коллизировал с уже применёнными ревизиями
    после пересчёта плана) должна вставлять РОВНО те же строки, что MODEL_OPTIONS.
    Импортируем модуль миграции (а не читаем файл как текст) -- подстрока не
    отличает `_OPTIONS` от случайного совпадения в другой константе."""
    import importlib.util, json
    from pathlib import Path

    path = Path("alembic/versions/bb51258925d4_seed_model_options.py")
    spec_ = importlib.util.spec_from_file_location("seed_options_migration", path)
    mod = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(mod)

    from_migration = {
        (o["model_code"], o["kind"], o["code"]): (float(o["mult"]), json.loads(o["params"]), o["is_default"])
        for o in mod._OPTIONS
    }
    from_seed = {
        (o["model_code"], o["kind"].value, o["code"]):
            (float(o["credits_multiplier"]), o["provider_params"], o["is_default"])
        for o in MODEL_OPTIONS
    }
    assert from_migration == from_seed
