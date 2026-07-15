# Выверка каталога fal.ai — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Починить каталог медиа-моделей: два эндпоинта, которые гарантированно падают, две депрекированные модели, перепутанную семантику t2i/i2i и три модели, продающиеся ниже задуманной маржи.

**Architecture:** Каталог живёт в двух местах — константы `AI_MODELS` в `app/db/seed.py` (для чистой БД) и строки в таблице `ai_models` (для существующей). `apply_seed` **идемпотентен по коду модели и не обновляет существующие строки**, поэтому каждая правка каталога = правка константы + data-миграция Alembic. Оба должны меняться синхронно, иначе прод и тесты разъедутся.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (async), Alembic, pytest (+ `sqlite+aiosqlite` in-memory в тестах), PostgreSQL в проде.

**Спек:** `docs/superpowers/specs/2026-07-15-generation-quality-design.md` (этап 1).

## Global Constraints

- **Голова миграций — `f7a8b9c0d1e2`** (phase5 antifraud). Новая миграция ставит `down_revision = 'f7a8b9c0d1e2'`.
- **Формула цены проекта:** `credits = usd × usd_to_rub_rate(80) × provider_fee_multiplier(1.15) × margin_multiplier(2.5) / rub_per_credit(0.10)`, что сворачивается в **`credits = usd × 2300`**. Контроль: `qwen_image` $0.02 → 46 (в сиде 50), `ovi_video` $0.20 → 460 (в сиде 500). Эти две модели уже посчитаны по формуле — их не трогаем.
- **Все цены fal измерены живыми генерациями 2026-07-15**, не взяты со страницы: Kling 5 с = $1.40, Veo = $0.40/с со звуком и $0.20/с без, Wan 480p = $0.04/с, qwen_image = $0.02/МП. Не выдумывать новых чисел: любое новое — только замером.
- **`min_credits` ≤ цена самой дешёвой комбинации параметров модели.** Иначе пол отрежет дешёвые опции на этапе 2.
- Комментарии и docstring — на русском, как в остальном `app/`.
- Не трогать `app/services/pricing.py`, `app/services/media_generation_service.py`, фронт — это этапы 3–6 второго плана.

---

### Task 1: Починить эндпоинты и уйти с депрекированных моделей

Пять из восьми медиа-моделей указывают не туда. Проверено живыми вызовами: `fal-ai/wan/v2.2` и `fal-ai/kling-video/v2` **не 404 при отправке** — очередь принимает запрос, выдаёт `request_id`, а воркер возвращает `{"detail":"Path /v2.2 not found"}`. Приложение — это `fal-ai/wan`, а `/v2.2-a14b/text-to-video` — маршрут внутри него.

**Files:**
- Modify: `app/db/seed.py:96-129` (блок `AI_MODELS`, секции IMAGE и VIDEO)
- Test: `tests/db/test_seed_catalog.py`

**Interfaces:**
- Consumes: ничего (первая задача).
- Produces: константа `AI_MODELS` с полем `provider_model_id`, значения которого проверены схемой fal. Task 3 переносит эти же значения в data-миграцию — числа и строки обязаны совпасть дословно.

- [ ] **Step 1: Написать падающий тест на реальные эндпоинты**

Добавить в конец `tests/db/test_seed_catalog.py`:

```python
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
```

- [ ] **Step 2: Прогнать тест и убедиться, что падает**

Run: `python -m pytest tests/db/test_seed_catalog.py::test_media_provider_model_ids_are_real_fal_endpoints -v`
Expected: FAIL — `AssertionError` на `seedream` (в сиде `fal-ai/bytedance/seedream/v3/text-to-image`).

- [ ] **Step 3: Исправить эндпоинты в сиде**

В `app/db/seed.py` заменить блок IMAGE + VIDEO (строки 96–129) на:

```python
    # --- IMAGE (fal.ai), 4 модели ---
    # provider_model_id проверены 2026-07-15 по схеме fal (openapi.json?endpoint_id=...).
    dict(**_MEDIA, category=ModelCategory.image, code="qwen_image", display_name="Qwen Image",
         tier=ModelTier.economy, cost_unit=CostUnit.megapixel,
         provider_model_id="fal-ai/qwen-image",
         min_credits=50, recommended_credits=50, sort_order=130),
    # v3 депрекирован fal; 2K/4K (image_size=auto_2K/auto_4K) есть только у v4.
    dict(**_MEDIA, category=ModelCategory.image, code="seedream", display_name="Seedream",
         tier=ModelTier.standard, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/bytedance/seedream/v4/text-to-image",
         min_credits=75, recommended_credits=75, sort_order=140),
    # Голый fal-ai/flux-pro/kontext -- это image-to-image, у него image_url обязателен
    # (required: ["prompt","image_url"]). Для text-to-image нужен отдельный маршрут.
    dict(**_MEDIA, category=ModelCategory.image, code="flux_kontext_pro", display_name="Flux Kontext Pro",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/flux-pro/kontext/text-to-image",
         min_credits=100, recommended_credits=100, sort_order=150),
    dict(**_MEDIA, category=ModelCategory.image, code="nano_banana", display_name="Nano Banana",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/nano-banana",
         min_credits=100, recommended_credits=100, sort_order=160),
    # --- VIDEO (fal.ai), 4 модели (recommended_credits -- цена за дефолтную комбинацию модели) ---
    dict(**_MEDIA, category=ModelCategory.video, code="ovi_video", display_name="Ovi Video",
         tier=ModelTier.economy, cost_unit=CostUnit.video,
         provider_model_id="fal-ai/ovi",
         min_credits=500, recommended_credits=500, sort_order=170),
    # Приложение -- fal-ai/wan, а v2.2-a14b/text-to-video -- маршрут внутри него.
    # Заявленный ранее fal-ai/wan/v2.2 очередь принимает, но воркер отдаёт
    # {"detail":"Path /v2.2 not found"} -- уже после резервирования кредитов.
    dict(**_MEDIA, category=ModelCategory.video, code="wan_video", display_name="Wan Video",
         tier=ModelTier.standard, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/wan/v2.2-a14b/text-to-video",
         min_credits=600, recommended_credits=600, sort_order=180),
    # Аналогично: приложение fal-ai/kling-video, маршрут v2/master/text-to-video.
    dict(**_MEDIA, category=ModelCategory.video, code="kling_video", display_name="Kling Video",
         tier=ModelTier.premium, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/kling-video/v2/master/text-to-video",
         min_credits=850, recommended_credits=850, sort_order=190),
    # veo3 депрекирован; resolution=4k есть только у veo3.1.
    dict(**_MEDIA, category=ModelCategory.video, code="veo_video", display_name="Veo Video",
         tier=ModelTier.ultra, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/veo3.1",
         min_credits=4800, recommended_credits=4800, sort_order=200),
]
```

Также убрать устаревшее предупреждение в `app/db/seed.py:47-49`, заменив его на:

```python
# provider_model_id медиа-моделей проверены по схемам fal 2026-07-15 (см. спек
# docs/superpowers/specs/2026-07-15-generation-quality-design.md).
# Текстовые (OpenRouter) -- ВСЁ ЕЩЁ ПЛЕЙСХОЛДЕРЫ, не проверялись; цены = 0,
# поэтому списание текста идёт по min_credits (защитный минимум).
```

- [ ] **Step 4: Прогнать тесты и убедиться, что проходят**

Run: `python -m pytest tests/db/test_seed_catalog.py -v`
Expected: PASS, все тесты файла (включая старые `test_twenty_models_split_12_text_4_image_4_video` и `test_media_cost_units_match_tz` — они не затронуты).

- [ ] **Step 5: Коммит**

```bash
git add app/db/seed.py tests/db/test_seed_catalog.py
git commit -m "fix(catalog): реальные эндпоинты fal вместо непроверенных плейсхолдеров

wan/v2.2 и kling-video/v2 не существуют: очередь принимает запрос, воркер
отдаёт 'Path /v2.2 not found' уже после резервирования кредитов.
seedream/v3 и veo3 депрекированы fal; у преемников есть 2K/4K.
flux-pro/kontext -- это i2i (image_url обязателен), для t2i нужен /text-to-image.
Все id проверены запросом схемы fal 2026-07-15."
```

---

### Task 2: Привести цены к формуле проекта

Три модели продаются дешевле, чем предписывает собственная формула. Kling — **в минус**: себестоимость $1.40 (измерено списанием) против 850 кредитов ≈ 127 ₽ по пакету START и ≈ 73 ₽ по BUSINESS.

**Files:**
- Modify: `app/db/seed.py` (поля `min_credits`/`recommended_credits` у `wan_video`, `kling_video`, `veo_video`)
- Test: `tests/db/test_seed_catalog.py:75-89` (`test_model_codes_and_credit_floors_match_tz` — он фиксирует нынешние убыточные цифры и обязан упасть)

**Interfaces:**
- Consumes: `AI_MODELS` из Task 1.
- Produces: финальные значения `min_credits`/`recommended_credits`, которые Task 3 переносит в data-миграцию дословно.

- [ ] **Step 1: Написать падающий тест с ценами по формуле**

Заменить в `tests/db/test_seed_catalog.py` тело `test_model_codes_and_credit_floors_match_tz` (строки 75–89) на:

```python
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
```

Добавить `import math` в начало файла (рядом с `import pytest`).

- [ ] **Step 2: Прогнать тесты и убедиться, что падают**

Run: `python -m pytest tests/db/test_seed_catalog.py::test_model_codes_and_credit_floors_match_tz tests/db/test_seed_catalog.py::test_media_prices_follow_the_project_formula -v`
Expected: оба FAIL — `AssertionError: kling_video` (в сиде 850, ожидается 3220) и `kling_video: 850 < 3220 -- продаём ниже формулы`.

- [ ] **Step 3: Исправить цены в сиде**

В `app/db/seed.py` в трёх видео-моделях поменять только числа:

```python
    dict(**_MEDIA, category=ModelCategory.video, code="wan_video", display_name="Wan Video",
         tier=ModelTier.standard, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/wan/v2.2-a14b/text-to-video",
         # $0.08/с * 5.0625с (81 кадр / 16 fps) = $0.405 -> 932; пол = 480p ($0.2025 -> 466)
         min_credits=466, recommended_credits=932, sort_order=180),
    dict(**_MEDIA, category=ModelCategory.video, code="kling_video", display_name="Kling Video",
         tier=ModelTier.premium, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/kling-video/v2/master/text-to-video",
         # $1.40 за 5с (измерено списанием) -> 3220. Было 850 = продажа в минус.
         min_credits=3220, recommended_credits=3220, sort_order=190),
    dict(**_MEDIA, category=ModelCategory.video, code="veo_video", display_name="Veo Video",
         tier=ModelTier.ultra, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/veo3.1",
         # дефолт 8с со звуком: $0.40/с * 8 = $3.20 -> 7360.
         # пол: 4с без звука $0.20/с * 4 = $0.80 -> 1840.
         min_credits=1840, recommended_credits=7360, sort_order=200),
```

- [ ] **Step 4: Прогнать весь файл тестов**

Run: `python -m pytest tests/db/test_seed_catalog.py -v`
Expected: PASS, все тесты.

- [ ] **Step 5: Прогнать тесты ценообразования — проверить, что не сломали смежное**

Run: `python -m pytest tests/services/test_pricing.py tests/services/test_media_generation_service.py -v`
Expected: PASS. Если падает — тест зашит на старые цены; **не подгонять цены обратно**, а поправить тест и отметить это в отчёте.

- [ ] **Step 6: Коммит**

```bash
git add app/db/seed.py tests/db/test_seed_catalog.py
git commit -m "fix(pricing): привести цены видео-моделей к формуле проекта

Себестоимость измерена живыми генерациями fal 2026-07-15:
kling 5с = \$1.40, veo = \$0.40/с со звуком, wan 480p = \$0.04/с.
kling продавался за 850 кредитов при себестоимости 3220 по формуле --
минус ~56 руб с генерации на пакете BUSINESS.
kling 850->3220, veo 4800->7360, wan 600->932.
min_credits = цена самой дешёвой комбинации (пол не режет дешёвые опции)."
```

---

### Task 3: Data-миграция для существующих БД

`apply_seed` вставляет только отсутствующие строки (`app/db/seed.py`, `existing_models = {...}; if data["code"] not in existing_models`). Правки Task 1–2 починят только чистую БД — на проде строки уже есть и останутся сломанными. Нужен UPDATE.

**Files:**
- Create: `alembic/versions/a1b2c3d4e5f6_fix_fal_catalog_endpoints_and_prices.py`
- Test: `tests/db/test_seed_catalog.py`

**Interfaces:**
- Consumes: значения `provider_model_id` (Task 1) и `min_credits`/`recommended_credits` (Task 2) — переносятся дословно.
- Produces: ревизия `a1b2c3d4e5f6`, становится новой головой цепочки.

- [ ] **Step 1: Написать тест на совпадение миграции и сида**

Добавить в `tests/db/test_seed_catalog.py`:

```python
def test_migration_values_match_seed_constants():
    """Миграция чинит существующие строки, сид -- чистую БД. Если они разъедутся,
    прод и тесты будут жить в разных каталогах. Здесь ловим расхождение.
    """
    import re
    from pathlib import Path

    path = Path("alembic/versions/a1b2c3d4e5f6_fix_fal_catalog_endpoints_and_prices.py")
    text = path.read_text(encoding="utf-8")
    by_code = {m["code"]: m for m in AI_MODELS}

    for code in ("wan_video", "kling_video", "veo_video", "seedream", "flux_kontext_pro"):
        assert by_code[code]["provider_model_id"] in text, f"{code}: эндпоинт из сида не найден в миграции"
    for code in ("wan_video", "kling_video", "veo_video"):
        assert str(by_code[code]["recommended_credits"]) in text, f"{code}: цена из сида не найдена в миграции"
```

- [ ] **Step 2: Прогнать тест и убедиться, что падает**

Run: `python -m pytest tests/db/test_seed_catalog.py::test_migration_values_match_seed_constants -v`
Expected: FAIL — `FileNotFoundError`, миграции ещё нет.

- [ ] **Step 3: Написать миграцию**

Создать `alembic/versions/a1b2c3d4e5f6_fix_fal_catalog_endpoints_and_prices.py`:

```python
"""fix fal catalog: реальные эндпоинты + цены по формуле.

apply_seed идемпотентен по code и НЕ обновляет существующие строки, поэтому
правка констант в seed.py чинит только чистую БД. Здесь -- UPDATE для тех,
у кого каталог уже засеян.

Основания (спек docs/superpowers/specs/2026-07-15-generation-quality-design.md):
- wan/v2.2 и kling-video/v2 не существуют (воркер: "Path /v2.2 not found");
- seedream/v3 и veo3 депрекированы fal, 2K/4K только у преемников;
- flux-pro/kontext -- это i2i (image_url обязателен), t2i -- отдельный маршрут;
- цены измерены живыми генерациями: kling 5с=$1.40, veo=$0.40/с, wan 480p=$0.04/с.

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-07-15 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (code, новый provider_model_id, новый min_credits, новый recommended_credits)
# None в цене = не менять.
_FIXES = [
    ("seedream", "fal-ai/bytedance/seedream/v4/text-to-image", None, None),
    ("flux_kontext_pro", "fal-ai/flux-pro/kontext/text-to-image", None, None),
    ("wan_video", "fal-ai/wan/v2.2-a14b/text-to-video", 466, 932),
    ("kling_video", "fal-ai/kling-video/v2/master/text-to-video", 3220, 3220),
    ("veo_video", "fal-ai/veo3.1", 1840, 7360),
]

# Прежние значения -- для downgrade.
_ROLLBACK = [
    ("seedream", "fal-ai/bytedance/seedream/v3/text-to-image", None, None),
    ("flux_kontext_pro", "fal-ai/flux-pro/kontext", None, None),
    ("wan_video", "fal-ai/wan/v2.2", 600, 600),
    ("kling_video", "fal-ai/kling-video/v2", 850, 850),
    ("veo_video", "fal-ai/veo3", 4800, 4800),
]


def _apply(rows) -> None:
    for code, model_id, min_credits, recommended in rows:
        sets = {"provider_model_id": model_id}
        if min_credits is not None:
            sets["min_credits"] = min_credits
        if recommended is not None:
            sets["recommended_credits"] = recommended
        assignments = ", ".join(f"{k} = :{k}" for k in sets)
        op.execute(
            sa.text(f"UPDATE ai_models SET {assignments} WHERE code = :code").bindparams(
                **sets, code=code
            )
        )


def upgrade() -> None:
    _apply(_FIXES)


def downgrade() -> None:
    _apply(_ROLLBACK)
```

- [ ] **Step 4: Прогнать тест на совпадение**

Run: `python -m pytest tests/db/test_seed_catalog.py::test_migration_values_match_seed_constants -v`
Expected: PASS.

- [ ] **Step 5: Проверить, что цепочка миграций цела**

Run: `python -m alembic heads`
Expected: одна голова — `a1b2c3d4e5f6 (head)`. Если голов две, значит `down_revision` указан неверно.

- [ ] **Step 6: Прогнать миграцию на живой БД вверх и вниз**

Run:
```bash
docker compose up -d postgres
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
```
Expected: без ошибок. `downgrade` возвращает старые значения, `upgrade` снова ставит новые — это проверка, что откат рабочий.

- [ ] **Step 7: Коммит**

```bash
git add alembic/versions/a1b2c3d4e5f6_fix_fal_catalog_endpoints_and_prices.py tests/db/test_seed_catalog.py
git commit -m "fix(db): data-миграция каталога fal для существующих БД

apply_seed не обновляет существующие строки, поэтому правка констант чинит
только чистую БД. UPDATE эндпоинтов и цен + рабочий downgrade."
```

---

### Task 4: Развести text-to-image и image-to-image

`fal-ai/flux-pro/kontext` требует `image_url` (`required: ["prompt","image_url"]` по схеме). Task 1 перевёл модель на `/text-to-image`, но тогда сломается обратный сценарий: пользователь приложил фото → `api.generate(..., imageUrl=...)` → уходит в t2i-маршрут, который `image_url` не принимает. У `nano_banana` та же развилка (`fal-ai/nano-banana` против `fal-ai/nano-banana/edit`).

Одна строка каталога не может нести два эндпоинта — нужна колонка.

**Files:**
- Modify: `app/db/models/ai_models.py` (после `provider_model_id`, строка 19)
- Create: `alembic/versions/b2c3d4e5f6a8_add_provider_model_id_edit.py`
- Modify: `app/db/seed.py` (поля у `flux_kontext_pro`, `nano_banana`)
- Test: `tests/db/test_seed_catalog.py`

**Interfaces:**
- Consumes: `AI_MODELS` (Task 1–2), ревизия `a1b2c3d4e5f6` (Task 3).
- Produces: `AiModel.provider_model_id_edit: Mapped[str | None]` — колонка, которую **второй план** (этап 4, `FalClient`) выберет при наличии `image_url`. Ревизия `b2c3d4e5f6a8` — новая голова.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/db/test_seed_catalog.py`:

```python
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
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/db/test_seed_catalog.py::test_edit_endpoints_for_image_models_that_have_them -v`
Expected: FAIL — `KeyError: 'provider_model_id_edit'`.

- [ ] **Step 3: Добавить колонку в модель**

В `app/db/models/ai_models.py` после строки `provider_model_id: Mapped[str] = mapped_column(String(128))` добавить:

```python
    # Маршрут image-to-image, если у модели он отдельный (flux-pro/kontext, nano-banana/edit).
    # None = модель обходится одним provider_model_id. Выбор делает FalClient по наличию image_url.
    provider_model_id_edit: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
```

- [ ] **Step 4: Проставить значения в сиде**

В `app/db/seed.py` у двух моделей добавить поле:

```python
    dict(**_MEDIA, category=ModelCategory.image, code="flux_kontext_pro", display_name="Flux Kontext Pro",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/flux-pro/kontext/text-to-image",
         provider_model_id_edit="fal-ai/flux-pro/kontext",
         min_credits=100, recommended_credits=100, sort_order=150),
    dict(**_MEDIA, category=ModelCategory.image, code="nano_banana", display_name="Nano Banana",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/nano-banana",
         provider_model_id_edit="fal-ai/nano-banana/edit",
         min_credits=100, recommended_credits=100, sort_order=160),
```

- [ ] **Step 5: Написать миграцию**

Создать `alembic/versions/b2c3d4e5f6a8_add_provider_model_id_edit.py`:

```python
"""add ai_models.provider_model_id_edit -- отдельный маршрут image-to-image.

У flux-pro/kontext и nano-banana t2i и i2i -- разные эндпоинты fal.
Одна строка каталога не может нести оба, отсюда колонка.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_models', sa.Column('provider_model_id_edit', sa.String(length=128), nullable=True))
    op.execute(
        sa.text("UPDATE ai_models SET provider_model_id_edit = :v WHERE code = 'flux_kontext_pro'")
        .bindparams(v="fal-ai/flux-pro/kontext")
    )
    op.execute(
        sa.text("UPDATE ai_models SET provider_model_id_edit = :v WHERE code = 'nano_banana'")
        .bindparams(v="fal-ai/nano-banana/edit")
    )


def downgrade() -> None:
    op.drop_column('ai_models', 'provider_model_id_edit')
```

- [ ] **Step 6: Прогнать тесты**

Run: `python -m pytest tests/db/ -v`
Expected: PASS, включая новый `test_edit_column_roundtrips_through_orm`.

- [ ] **Step 7: Проверить миграцию на живой БД**

Run:
```bash
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
```
Expected: без ошибок, `alembic heads` показывает `b2c3d4e5f6a8 (head)`.

- [ ] **Step 8: Коммит**

```bash
git add app/db/models/ai_models.py app/db/seed.py alembic/versions/b2c3d4e5f6a8_add_provider_model_id_edit.py tests/db/test_seed_catalog.py
git commit -m "feat(catalog): provider_model_id_edit -- отдельный маршрут i2i

fal-ai/flux-pro/kontext требует image_url (i2i), для t2i нужен
/text-to-image. У nano-banana та же развилка (/edit). Колонка позволяет
одной модели каталога нести оба маршрута; выбор -- по наличию image_url
(подключается во втором плане, этап 4)."
```

---

### Task 5: Закрепить возврат кредитов и закрыть PLACEHOLDER'ы по формам ответа fal

Сломанные эндпоинты падали **после** резервирования: очередь принимала запрос, кредиты резервировались, а результатом приходило `{"detail":"Path /v2.2 not found"}`. Task 1 убрал причину, но класс ошибки остался — любой отказ воркера fal приходит тем же путём.

**Разбор кода показал: возврат реализован и работает.** `handle_fal_webhook` (`app/services/media_generation_service.py:227`) покрывает оба пути: при `status="ERROR"` зовёт `refund_request` (строка 298), а при `status="OK"`, если `extract_result_url` вернул `None`, — тоже возвращает (строки 264–275). Плюс `refund_stale_reserved_requests` (строка 311) подчищает зависшие резервы, если вебхук не придёт вовсе. Поэтому задача не чинит, а **закрепляет** поведение тестом и закрывает две устаревшие пометки PLACEHOLDER реальными формами ответов, наблюдёнными 2026-07-15.

**Files:**
- Modify: `app/services/media_generation_service.py:264-268` и `:285-286` (только комментарии-PLACEHOLDER)
- Test: `tests/services/test_media_generation_service.py`

**Interfaces:**
- Consumes: `start_media_generation(session, user, model_code, prompt)` и `handle_fal_webhook(session, payload)` (оба уже импортированы в тест-файле); хелперы того же файла — `_seed(session, *models, balance=1000)`, `_image_model(code="img", ...)`, `_request_rows(session)`, `_tx_types(session)`; фикстуры `session`, `fal`, `fake_redis` (последние две — `autouse`). `FakeFalClient` выдаёт `provider_response_id == "fal-req-1"`.
- Produces: только тест и комментарии. Поведение не меняется.

- [ ] **Step 1: Написать тест на отказ воркера**

Добавить в конец `tests/services/test_media_generation_service.py`:

```python
async def test_worker_rejection_body_refunds_credits(session, fal, fake_redis):
    """Наблюдалось вживую 2026-07-15: сломанный эндпоинт fal-ai/wan/v2.2 --
    очередь приняла запрос (кредиты зарезервированы), а воркер вернул
    {"detail": "Path /v2.2 not found"} вместо результата.

    extract_result_url не найдёт ни images, ни video -> вернёт None ->
    кредиты обязаны вернуться, иначе пользователь платит за 404.
    """
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")
    assert (await session.get(User, user.id)).credits_balance == 900  # 100 зарезервировано

    await handle_fal_webhook(session, {
        "request_id": "fal-req-1",
        "status": "OK",
        "payload": {"detail": "Path /v2.2 not found"},
    })

    assert (await session.get(User, user.id)).credits_balance == 1000  # вернулись
    rows = await _request_rows(session)
    assert rows[0].status == RequestStatus.failed
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]


async def test_worker_validation_error_body_refunds_credits(session, fal, fake_redis):
    """Вторая наблюдённая форма отказа: pydantic-ошибка воркера списком.
    fal при этом отдаёт status=ERROR."""
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(session, {
        "request_id": "fal-req-1",
        "status": "ERROR",
        "payload": {"detail": [
            {"type": "missing", "loc": ["body", "prompt"], "msg": "Field required"}
        ]},
    })

    assert (await session.get(User, user.id)).credits_balance == 1000
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]
```

Убедиться, что `handle_fal_webhook` есть в блоке импорта `from app.services.media_generation_service import (...)` (строка 33); если нет — дописать.

- [ ] **Step 2: Прогнать тесты**

Run: `python -m pytest tests/services/test_media_generation_service.py -v -k "refunds_credits"`
Expected: **PASS оба** — путь возврата уже реализован, тест его закрепляет.
Если что-то падает — **не подгонять тест под код**: это значит, что найден настоящий денежный баг. Пометить `@pytest.mark.xfail(reason="...")`, описать в отчёте и завести отдельную задачу.

- [ ] **Step 3: Закрыть PLACEHOLDER'ы наблюдёнными формами**

В `app/services/media_generation_service.py` заменить комментарий на строках 264–268:

```python
            if result_url is None:
                # Формы успешного ответа fal подтверждены живыми вызовами 2026-07-15:
                # image -> {"images":[{"url":...}]}, video -> {"video":{"url":...}}
                # (обе уже разбирает fal_client.extract_result_url).
                # Сюда попадаем, когда воркер вернул не результат, а отказ:
                # {"detail":"Path /v2.2 not found"} или {"detail":[{...pydantic...}]}.
                # Кредиты за недоставленный результат не списываем.
```

и на строках 285–286:

```python
    elif status == "ERROR":
        # Тело ошибки fal наблюдалось в двух формах (2026-07-15):
        # строкой {"detail":"Path /v2.2 not found"} и списком pydantic-ошибок
        # {"detail":[{"type":"missing","loc":["body","prompt"],...}]}.
        # str() покрывает обе; отдельный ключ "error" оставляем как запасной.
```

- [ ] **Step 4: Прогнать весь файл**

Run: `python -m pytest tests/services/test_media_generation_service.py -v`
Expected: PASS, все тесты (комментарии поведение не меняют).

- [ ] **Step 5: Коммит**

```bash
git add app/services/media_generation_service.py tests/services/test_media_generation_service.py
git commit -m "test(media): закрепить возврат кредитов при отказе воркера fal

Регрессия на реальный случай: fal принимает задачу и резервирует списание,
а воркер отдаёт отказ вместо результата. Обе наблюдённые формы отказа
(строка и список pydantic-ошибок) ведут к возврату -- проверено тестом.
Заодно закрыты два PLACEHOLDER'а: формы ответов fal подтверждены живыми
вызовами 2026-07-15."
```

---

## Приёмка плана

- [ ] `python -m pytest tests/ -v` — зелёный (кроме помеченных `xfail`, если Task 5 нашла баг).
- [ ] `python -m alembic heads` — одна голова, `b2c3d4e5f6a8`.
- [ ] `python -m alembic upgrade head && python -m alembic downgrade -2 && python -m alembic upgrade head` — без ошибок.
- [ ] В `app/db/seed.py` не осталось слова PLACEHOLDER у медиа-моделей (у текстовых — осталось намеренно, они не проверялись).

## Что этот план НЕ делает (второй план, этапы 2–7)

- Таблица `model_option` и опции качества/длительности/звука.
- Множители в `pricing.py`; удаление `duration/5` для видео.
- `FalClient`: merge `provider_params`, выбор `provider_model_id_edit`, отказ от угаданных полей.
- API `quality_code`/`duration_code`, `options` в `ModelOut`.
- Фронт: сегменты вместо слайдера 2–15.
- Админка CRUD опций.

**Денежные баги, которые остаются жить до второго плана** (осознанно — их лечит механизм опций, а не заплатка):
- Переплата за длительность у Wan и Ovi: пользователь ставит слайдер на 15 с, платит `ceil(15/5 × recommended)`, но у обеих моделей поля длительности нет и приходит всегда ~5 с.
- Звук Veo включён молча и удваивает себестоимость ($0.40/с против $0.20/с).
