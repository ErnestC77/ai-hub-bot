# Credit System Phase 6 — Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Последняя фаза credit system v2 — аналитика `/admin_stats` v2: заполнение `AIRequest.provider_cost_usd` для text (OpenRouter) и media (fal.ai) запросов, расширение `DailyStats` (revenue/margin/avg + model_usage + top_users_by_spend, всё в окне «сегодня») и расширение `GET /admin/stats` этими же полями.

**Architecture:** Три новые чистые функции в `app/services/pricing.py` (`calculate_api_cost_usd` / `calculate_image_api_cost_usd` / `calculate_video_api_cost_usd`) в стиле существующих `calculate_*_credits`. Точечные вставки их вызовов в `text_generation_service.py` (на settle, по факту usage) и `media_generation_service.py` (на reserve — actual в медиа-flow всегда равен estimated). Агрегация в `stats_service.py` — на лету `GROUP BY` по `ai_requests`, без новой таблицы и без миграции.

**Tech Stack:** FastAPI + aiogram3 + SQLAlchemy 2 async + Postgres 16 (prod) / aiosqlite (unit-тесты) + Redis 7 (prod) / FakeRedis (тесты) + pytest (`asyncio_mode = auto`).

**Design spec (единственный источник истины):** `docs/superpowers/specs/2026-07-10-credit-system-phase6-analytics-design.md`

## Global Constraints

- **Миграции НЕТ.** `AIRequest.provider_cost_usd` существует в схеме с фазы 1 (`app/db/models/ai_request.py:31`, `Numeric(12, 6), default=0`) — фаза только начинает его заполнять. Никаких изменений таблиц и никаких новых Alembic-ревизий.
- **`MonthlyStats` не меняется** (`app/services/stats_service.py:31-34`); поля `month_revenue_rub` / `month_credits_purchases_count` в `StatsOut` остаются последними и как есть.
- `text_generation_service.py` / `media_generation_service.py` — **ТОЛЬКО точечные вставки** (по образцу фазы 5), никакого рерайта каркаса фаз 2-3.
- Новые pricing-функции считают **себестоимость**: без `provider_fee_multiplier` / `margin_multiplier` / `min_credits` / edit-множителя / глобальных минимумов — это НЕ то, что платит пользователь.
- Топ-списки: `LIMIT 10` (константа `TOP_LIMIT = 10` в `stats_service.py`), сортировка по `SUM(charged_credits) DESC`, окно «сегодня» — тот же `day_start`, что уже в `get_daily_stats` (`stats_service.py:38-39`).
- Курсы читаются из таблицы settings ключами `rub_per_credit` и `usd_to_rub_rate` через `settings_service.get_setting(session, key, cast=float, default=...)` с дефолтами из `PricingSettings()` (`pricing.py:16-25`: 0.10 и 80.0) — те же ключи, что уже читает `load_pricing_settings` (`settings_service.py:29-43`).
- `Numeric`-колонки (`provider_cost_usd`, `fixed_cost_usd`) возвращают из БД `Decimal`: в pricing-функциях уже есть `float(model.fixed_cost_usd)` / `float(model.*_price_*)`, в stats-агрегатах оборачивать суммы `float(...)` (как существующий `float(api_cost)` в `stats_service.py:80`), в тестах сравнивать `float(request.provider_cost_usd) == pytest.approx(...)`.
- Тесты запускать из корня репо: `python -m pytest <путь> -v`. Тестовые файлы generation-сервисов сами выставляют `BOT_TOKEN`/`DATABASE_URL` через `os.environ.setdefault` до импорта `app.*`.
- Номера строк в задачах актуальны на момент написания плана (2026-07-10, master после фазы 6-spec-коммита `fa04c23`). Внутри одной задачи более ранние правки того же файла сдвигают последующие строки — ориентироваться на приведённые «якорные» сниппеты кода.
- **Критерий готовности фазы (и всего rebuild'а):** `python -m pytest -q` полностью зелёный и `python -c "import app.main"` проходит.

## File Structure

| Файл | Действие |
|---|---|
| `app/services/pricing.py` | добавить 3 функции в конец файла (Task 1) |
| `tests/services/test_pricing.py` | расширить `_media_model`, добавить тесты (Task 1) |
| `app/services/text_generation_service.py` | точечная вставка: импорт + 3 строки (Task 2) |
| `tests/services/test_text_generation_service.py` | 1 новый тест (Task 2) |
| `app/services/media_generation_service.py` | точечная вставка: импорт + 2 ветки + 1 поле ctor (Task 3) |
| `tests/services/test_media_generation_service.py` | расширить хелперы, 3 новых теста (Task 3) |
| `app/services/stats_service.py` | расширить `DailyStats` + `get_daily_stats`, добавить `ModelUsageStat`/`UserSpendStat` (Task 4) |
| `tests/services/test_stats_service.py` | расширить `_request`, обновить `test_empty_db_returns_zero_stats`, новые тесты (Task 4) |
| `app/api/routes/admin.py` | расширить `StatsOut`, добавить `ModelUsageOut`/`UserSpendOut`, дополнить `stats()` (Task 5) |
| `tests/api/test_admin.py` | обновить `test_stats_returns_v2_shape` (Task 5) |
| — | финальная регрессия: полный прогон + `import app.main` (Task 6) |

---

### Task 1: Три pricing-функции себестоимости (`calculate_api_cost_usd` / `calculate_image_api_cost_usd` / `calculate_video_api_cost_usd`)

**Files:**
- Modify: `app/services/pricing.py`
- Test: `tests/services/test_pricing.py`

**Interfaces:**
- Consumes: `AiModel.input_price_usd_per_1m_tokens` / `output_price_usd_per_1m_tokens` / `fixed_cost_usd` / `cost_unit` / `code` (`app/db/models/ai_models.py:22-25`), `CostUnit` (уже импортирован в `pricing.py:7`), `VIDEO_BASE_SECONDS` (`pricing.py:13`).
- Produces (Tasks 2-3 полагаются на эти ТОЧНЫЕ имена):
  - `def calculate_api_cost_usd(model: AiModel, input_tokens: int, output_tokens: int) -> float`
  - `def calculate_image_api_cost_usd(model: AiModel, quantity: int, megapixels: float) -> float`
  - `def calculate_video_api_cost_usd(model: AiModel, duration_seconds: int) -> float`

- [ ] **Step 1: Написать падающие тесты**

В `tests/services/test_pricing.py`:

1. Расширить импорт (строки 5-10) — добавить три новых имени:

```python
from app.services.pricing import (
    PricingSettings,
    calculate_api_cost_usd,
    calculate_image_api_cost_usd,
    calculate_image_credits,
    calculate_text_credits,
    calculate_video_api_cost_usd,
    calculate_video_credits,
)
```

2. Расширить хелпер `_media_model` (строки 24-31) параметром `fixed_cost_usd` с дефолтом `0.0` (обратная совместимость: существующие вызовы не меняются, дефолт совпадает с column default):

```python
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
```

3. Добавить в конец файла (после `test_video_rejects_non_video_cost_unit`, строка 134):

```python
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
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

```
python -m pytest tests/services/test_pricing.py -v
```

Ожидание: новые тесты падают на `ImportError: cannot import name 'calculate_api_cost_usd'`; все существующие тесты файла по-прежнему зелёные ловить нечем — импорт валит весь файл, это нормально для этого шага.

- [ ] **Step 3: Реализовать**

В `app/services/pricing.py` добавить в конец файла (после `calculate_video_credits`, строка 64) — код 1:1 из спеки:

```python
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
    """Себестоимость video-генерации в USD -- структура 1:1 с
    calculate_video_credits, но fixed_cost_usd вместо recommended_credits."""
    if model.cost_unit == CostUnit.second:
        return duration_seconds / VIDEO_BASE_SECONDS * float(model.fixed_cost_usd)
    if model.cost_unit == CostUnit.video:
        return float(model.fixed_cost_usd)
    raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для video")
```

Ничего в существующих функциях/константах файла не менять.

- [ ] **Step 4: Запустить тесты — убедиться, что зелёные**

```
python -m pytest tests/services/test_pricing.py -v
```

Все тесты файла (старые + новые) должны пройти.

- [ ] **Step 5: Закоммитить**

```
git add app/services/pricing.py tests/services/test_pricing.py
git commit -m "feat(pricing): api-cost-функции себестоимости USD (фаза 6, Task 1)"
```

---

### Task 2: Заполнение `provider_cost_usd` в text-flow

**Files:**
- Modify: `app/services/text_generation_service.py`
- Test: `tests/services/test_text_generation_service.py`

**Interfaces:**
- Consumes: `calculate_api_cost_usd` (Task 1), `result.input_tokens` / `result.output_tokens` из `AIResult`.
- Produces: `AIRequest.provider_cost_usd` заполнен по факту usage на успешном settle-пути. `settle_request` поле не трогает — это обычная колонка `AIRequest`, как `input_tokens`/`output_tokens`, которые сервис уже пишет напрямую (строки 183-184).

- [ ] **Step 1: Написать падающий тест**

В `tests/services/test_text_generation_service.py` добавить после `test_success_reserves_settles_and_returns_result` (заканчивается строкой 186):

```python
async def test_success_fills_provider_cost_usd(session, monkeypatch):
    user = await _seed(session, _model())  # price=1 -> input/output = 1 USD за 1M токенов
    provider = FakeProvider(result=AIResult(answer="ответ", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    await generate_text(session, user, "cheap", "привет")

    [request] = await _request_rows(session)
    # По ФАКТУ usage (500/200), не по оценке (2000/1000): 500/1e6*1 + 200/1e6*1 = 0.0007
    assert float(request.provider_cost_usd) == pytest.approx(0.0007)
```

Новых импортов не нужно: `pytest`, `AIResult`, `FakeProvider`, `_seed`, `_model`, `_request_rows` уже есть в файле.

- [ ] **Step 2: Запустить тест — убедиться, что падает**

```
python -m pytest tests/services/test_text_generation_service.py::test_success_fills_provider_cost_usd -v
```

Ожидание: `AssertionError` — `provider_cost_usd` равен 0 (default), не 0.0007.

- [ ] **Step 3: Реализовать точечную вставку**

В `app/services/text_generation_service.py` два изменения:

1. Импорт (строка 34): было

```python
from app.services.pricing import calculate_text_credits
```

стало

```python
from app.services.pricing import calculate_api_cost_usd, calculate_text_credits
```

2. В `generate_text`, внутри успешной ветки после расчёта `actual` (строки 185-187) и ДО `await settle_request(session, request, actual)` (строка 188), вставить:

```python
            request.input_tokens = result.input_tokens
            request.output_tokens = result.output_tokens
            actual = calculate_text_credits(
                model, result.input_tokens, result.output_tokens, settings=pricing
            )
            request.provider_cost_usd = calculate_api_cost_usd(
                model, result.input_tokens, result.output_tokens
            )
            await settle_request(session, request, actual)
```

(Показан итоговый вид блока; новые строки — только присваивание `request.provider_cost_usd`. Больше ничего в файле не менять.)

- [ ] **Step 4: Запустить тесты — убедиться, что зелёные**

```
python -m pytest tests/services/test_text_generation_service.py -v
```

Весь файл (включая антифрод-тесты фазы 5) должен пройти.

- [ ] **Step 5: Закоммитить**

```
git add app/services/text_generation_service.py tests/services/test_text_generation_service.py
git commit -m "feat(text): заполнение AIRequest.provider_cost_usd по факту usage (фаза 6, Task 2)"
```

---

### Task 3: Заполнение `provider_cost_usd` в media-flow (image и video)

**Files:**
- Modify: `app/services/media_generation_service.py`
- Test: `tests/services/test_media_generation_service.py`

**Interfaces:**
- Consumes: `calculate_image_api_cost_usd` / `calculate_video_api_cost_usd` (Task 1).
- Produces: `AIRequest.provider_cost_usd` заполнен на **reserve** (не на settle): у fal.ai нет обратной связи по фактическому расходу — actual в медиа-flow всегда равен estimated (см. `handle_fal_webhook`, settle по `estimated_credits`, строка 266).

- [ ] **Step 1: Написать падающие тесты**

В `tests/services/test_media_generation_service.py`:

1. Расширить хелперы `_image_model` (строки 162-168) и `_video_model` (строки 171-177) параметром `fixed_cost_usd` с дефолтом `0.0` (существующие вызовы не меняются):

```python
def _image_model(code="img", *, cost_unit=CostUnit.image, recommended=100,
                 min_credits=0, fixed_cost_usd=0.0) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.image, code=code,
        display_name=code, provider_model_id=f"fal-ai/{code}", tier=ModelTier.standard,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
        fixed_cost_usd=fixed_cost_usd,
    )


def _video_model(code="vid", *, cost_unit=CostUnit.second, recommended=600,
                 min_credits=0, fixed_cost_usd=0.0) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.video, code=code,
        display_name=code, provider_model_id=f"fal-ai/{code}", tier=ModelTier.premium,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
        fixed_cost_usd=fixed_cost_usd,
    )
```

2. Добавить три теста после `test_video_duration_scales_credits_and_is_passed_to_fal` (заканчивается строкой 267):

```python
# --- provider_cost_usd (фаза 6) ---

async def test_image_start_fills_provider_cost_usd(session, fal):
    user = await _seed(session, _image_model(fixed_cost_usd=0.04))

    request = await start_media_generation(session, user, "img", "a bear")

    # cost_unit=image: 1 * fixed_cost_usd = 0.04, считается на reserve
    assert float(request.provider_cost_usd) == pytest.approx(0.04)


async def test_image_edit_does_not_multiply_provider_cost_usd(session, fal):
    user = await _seed(session, _image_model(fixed_cost_usd=0.04))

    request = await start_media_generation(
        session, user, "img", "make it night",
        image_url="https://cdn.example.com/in.png",
    )

    # Кредиты с edit-множителем (150), себестоимость -- без него (fal берёт столько же)
    assert request.estimated_credits == 150
    assert float(request.provider_cost_usd) == pytest.approx(0.04)


async def test_video_start_fills_provider_cost_usd(session, fal):
    user = await _seed(session, _video_model(fixed_cost_usd=0.5), balance=2000)

    request = await start_media_generation(
        session, user, "vid", "a bear runs", duration_seconds=10, confirm=True
    )

    # cost_unit=second: 10/5 * 0.5 = 1.0 (та же длительность, что и в кредитах)
    assert float(request.provider_cost_usd) == pytest.approx(1.0)
```

Новых импортов не нужно: `pytest`, `start_media_generation`, `_seed` уже есть.

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

```
python -m pytest tests/services/test_media_generation_service.py -k provider_cost_usd -v
```

Ожидание: три `AssertionError` — `provider_cost_usd` равен 0.

- [ ] **Step 3: Реализовать точечную вставку**

В `app/services/media_generation_service.py` три изменения:

1. Импорт (строка 43): было

```python
from app.services.pricing import calculate_image_credits, calculate_video_credits
```

стало

```python
from app.services.pricing import (
    calculate_image_api_cost_usd,
    calculate_image_credits,
    calculate_video_api_cost_usd,
    calculate_video_credits,
)
```

2. Блок оценки в `start_media_generation` (строки 117-126): в каждую ветку добавить параллельный расчёт себестоимости с ТЕМИ ЖЕ аргументами (итоговый вид):

```python
    if model.category == ModelCategory.image:
        estimated = calculate_image_credits(
            model, quantity=1, megapixels=1.0, is_edit=image_url is not None
        )
        provider_cost_usd = calculate_image_api_cost_usd(model, quantity=1, megapixels=1.0)
        threshold = IMAGE_CONFIRM_THRESHOLD_CREDITS
    else:
        estimated = calculate_video_credits(
            model, duration_seconds or VIDEO_DEFAULT_DURATION_SECONDS
        )
        provider_cost_usd = calculate_video_api_cost_usd(
            model, duration_seconds or VIDEO_DEFAULT_DURATION_SECONDS
        )
        threshold = VIDEO_CONFIRM_THRESHOLD_CREDITS
```

3. Конструктор `AIRequest(...)` (строки 143-152): добавить именованное поле рядом с `estimated_credits`/`reserved_credits` (итоговый вид):

```python
        request = AIRequest(
            user_id=user.id,
            provider="fal",
            model_code=model.code,
            category=model.category,
            status=RequestStatus.pending,
            prompt_preview=prompt[:200],
            estimated_credits=estimated,
            reserved_credits=estimated,
            provider_cost_usd=provider_cost_usd,
        )
```

Больше ничего в файле не менять (в частности `handle_fal_webhook` и `refund_stale_reserved_requests` не трогаются).

- [ ] **Step 4: Запустить тесты — убедиться, что зелёные**

```
python -m pytest tests/services/test_media_generation_service.py -v
```

Весь файл должен пройти (Postgres-тест `test_concurrent_webhook_delivery_settles_exactly_once` штатно скипается без `TEST_DATABASE_URL`).

- [ ] **Step 5: Закоммитить**

```
git add app/services/media_generation_service.py tests/services/test_media_generation_service.py
git commit -m "feat(media): заполнение AIRequest.provider_cost_usd на reserve (фаза 6, Task 3)"
```

---

### Task 4: Расширение `stats_service.py` — revenue/margin/avg + model_usage + top_users_by_spend

**Files:**
- Modify: `app/services/stats_service.py`
- Test: `tests/services/test_stats_service.py`

**Interfaces:**
- Consumes: `AIRequest.charged_credits` / `provider_cost_usd` / `model_code` / `user_id` / `created_at` / `status`, `User.telegram_id`, `RequestStatus.completed`, `settings_service.get_setting`, `pricing.PricingSettings` (только за дефолтами 0.10 / 80.0). Циклического импорта нет: `pricing` не импортирует ни `settings_service`, ни `stats_service`.
- Produces (Task 5 полагается на эти ТОЧНЫЕ имена):
  - `@dataclass ModelUsageStat` — `model_code: str, requests: int, credits_spent: int, cost_usd: float`
  - `@dataclass UserSpendStat` — `telegram_id: int, credits_spent: int`
  - `DailyStats` + 6 новых полей: `revenue_credits: int, revenue_rub_estimated: float, margin_rub: float, avg_cost_credits: float, model_usage: list[ModelUsageStat], top_users_by_spend: list[UserSpendStat]`
  - Существующие 6 полей `DailyStats` и весь `MonthlyStats` — без изменений.

Семантика (из спеки, дословно):
- `revenue_credits` = `SUM(charged_credits)` где `status == completed AND created_at >= day_start`.
- `revenue_rub_estimated` = `revenue_credits * rub_per_credit`.
- `margin_rub` = `revenue_rub_estimated - api_cost_usd * usd_to_rub_rate` (api_cost_usd — уже посчитанная существующая метрика, все сегодняшние запросы без фильтра по статусу).
- `avg_cost_credits` = `revenue_credits / ai_requests` (знаменатель — существующий счётчик ВСЕХ сегодняшних запросов, включая failed), `0.0` при `ai_requests == 0`.
- `model_usage` / `top_users_by_spend`: все сегодняшние запросы (без фильтра по статусу), `GROUP BY`, `ORDER BY SUM(charged_credits) DESC`, `LIMIT 10`.

- [ ] **Step 1: Написать падающие тесты**

В `tests/services/test_stats_service.py`:

1. Расширить импорты: в блок `from app.db.models import ...` (строка 15) добавить `Setting`; в блок `from app.services.stats_service import ...` (строки 16-21) добавить `ModelUsageStat, UserSpendStat`:

```python
from app.db.models import AIRequest, CreditTransaction, Payment, Setting, User
from app.services.stats_service import (
    DailyStats,
    ModelUsageStat,
    MonthlyStats,
    UserSpendStat,
    get_daily_stats,
    get_monthly_stats,
)
```

2. Расширить хелпер `_request` (строки 48-53) параметрами `charged_credits` и `model_code` (дефолты сохраняют поведение существующих тестов):

```python
def _request(user_id, *, status=RequestStatus.completed, provider_cost_usd=0,
             charged_credits=0, model_code="deepseek_v3", created_at=NOW):
    return AIRequest(
        user_id=user_id, provider="openrouter", model_code=model_code,
        category=ModelCategory.text, status=status, prompt_preview="p",
        provider_cost_usd=provider_cost_usd, charged_credits=charged_credits,
        created_at=created_at,
    )
```

3. Обновить `test_empty_db_returns_zero_stats` (строки 70-77) — dataclass-сравнение требует все поля:

```python
async def test_empty_db_returns_zero_stats(session):
    assert await get_daily_stats(session) == DailyStats(
        new_users=0, payments_count=0, payments_amount_rub=0.0,
        ai_requests=0, api_cost_usd=0.0, errors=0,
        revenue_credits=0, revenue_rub_estimated=0.0, margin_rub=0.0,
        avg_cost_credits=0.0, model_usage=[], top_users_by_spend=[],
    )
    assert await get_monthly_stats(session) == MonthlyStats(
        revenue_rub=0.0, credits_purchases_count=0
    )
```

4. Добавить новые тесты в конец файла (после `test_monthly_stats_revenue_and_purchases_count`, строка 126). Все суммы в USD подобраны двоично-точными (0.25/0.5/0.125), чтобы dataclass-сравнения списков не ловили float-шум:

```python
# --- фаза 6: revenue / margin / avg (окно "сегодня") ---

async def test_daily_revenue_margin_avg_with_default_settings(session):
    user = await _seed_user(session)
    session.add(_request(user.id, charged_credits=100, provider_cost_usd=0.25))
    session.add(_request(user.id, charged_credits=50, provider_cost_usd=0.25))
    session.add(_request(user.id, status=RequestStatus.failed, provider_cost_usd=0.25))
    session.add(_request(user.id, charged_credits=999, created_at=TWO_DAYS_AGO))  # не сегодня
    await session.commit()

    daily = await get_daily_stats(session)
    assert daily.revenue_credits == 150            # только completed сегодня (failed не в счёт)
    # Дефолты PricingSettings (settings-таблица пуста): rub_per_credit=0.10, usd_to_rub_rate=80.0
    assert daily.revenue_rub_estimated == pytest.approx(15.0)   # 150 * 0.10
    assert daily.api_cost_usd == pytest.approx(0.75)            # все сегодняшние, включая failed
    assert daily.margin_rub == pytest.approx(15.0 - 0.75 * 80.0)  # -45.0
    assert daily.avg_cost_credits == pytest.approx(150 / 3)       # знаменатель = все 3 сегодняшних


async def test_daily_revenue_and_margin_read_settings_rows(session):
    user = await _seed_user(session)
    session.add(Setting(key="rub_per_credit", value="0.2", type="float", description=None))
    session.add(Setting(key="usd_to_rub_rate", value="100", type="float", description=None))
    session.add(_request(user.id, charged_credits=100, provider_cost_usd=0.125))
    await session.commit()

    daily = await get_daily_stats(session)
    assert daily.revenue_rub_estimated == pytest.approx(20.0)      # 100 * 0.2
    assert daily.margin_rub == pytest.approx(20.0 - 0.125 * 100)   # 7.5


# --- фаза 6: model_usage ---

async def test_model_usage_grouped_and_sorted_desc(session):
    user = await _seed_user(session)
    session.add(_request(user.id, model_code="gpt", charged_credits=30, provider_cost_usd=0.25))
    session.add(_request(user.id, model_code="gpt", charged_credits=20, provider_cost_usd=0.25))
    session.add(_request(user.id, model_code="deepseek_v3", charged_credits=200, provider_cost_usd=0.125))
    session.add(_request(user.id, model_code="old", charged_credits=999, created_at=TWO_DAYS_AGO))
    await session.commit()

    daily = await get_daily_stats(session)
    assert daily.model_usage == [
        ModelUsageStat(model_code="deepseek_v3", requests=1, credits_spent=200, cost_usd=0.125),
        ModelUsageStat(model_code="gpt", requests=2, credits_spent=50, cost_usd=0.5),
    ]


async def test_model_usage_limited_to_top_ten(session):
    user = await _seed_user(session)
    for i in range(1, 13):  # 12 моделей, спенд по возрастанию
        session.add(_request(user.id, model_code=f"m{i:02d}", charged_credits=i * 10))
    await session.commit()

    daily = await get_daily_stats(session)
    assert len(daily.model_usage) == 10
    assert daily.model_usage[0].model_code == "m12"   # максимальный спенд первым
    assert daily.model_usage[-1].model_code == "m03"  # m02/m01 обрезаны


# --- фаза 6: top_users_by_spend ---

async def test_top_users_aggregates_today_only(session):
    u1 = await _seed_user(session, 1)
    u2 = await _seed_user(session, 2)
    session.add(_request(u1.id, charged_credits=40))
    session.add(_request(u1.id, charged_credits=40))
    session.add(_request(u2.id, charged_credits=50))
    session.add(_request(u2.id, charged_credits=999, created_at=TWO_DAYS_AGO))  # не сегодня
    await session.commit()

    daily = await get_daily_stats(session)
    assert daily.top_users_by_spend == [
        UserSpendStat(telegram_id=1, credits_spent=80),
        UserSpendStat(telegram_id=2, credits_spent=50),
    ]


async def test_top_users_limited_to_top_ten(session):
    for i in range(1, 13):  # 12 пользователей, спенд по возрастанию
        user = await _seed_user(session, i)
        session.add(_request(user.id, charged_credits=i * 10))
    await session.commit()

    daily = await get_daily_stats(session)
    assert len(daily.top_users_by_spend) == 10
    assert daily.top_users_by_spend[0] == UserSpendStat(telegram_id=12, credits_spent=120)
    assert daily.top_users_by_spend[-1] == UserSpendStat(telegram_id=3, credits_spent=30)
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

```
python -m pytest tests/services/test_stats_service.py -v
```

Ожидание: `ImportError: cannot import name 'ModelUsageStat'`.

- [ ] **Step 3: Реализовать**

`app/services/stats_service.py` — расширение, не рерайт:

1. Обновить модульный docstring (строки 1-9): убрать абзац про «api_cost_usd стабильно вернёт 0.0 до Phase 6» (больше не верно), например:

```python
"""Статистика для GET /admin/stats.

Фаза 6: поверх базовых счётчиков фазы 5 добавлены revenue/margin/avg и
breakdown-списки model_usage / top_users_by_spend -- агрегация на лету по
ai_requests (GROUP BY), без отдельной таблицы (YAGNI, см. спеку фазы 6).
provider_cost_usd заполняется generation-сервисами с фазы 6.
"""
```

2. Дополнить импорты (существующие строки 11-18):

```python
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType, PaymentStatus, RequestStatus
from app.db.models import AIRequest, CreditTransaction, Payment, User
from app.services.pricing import PricingSettings
from app.services.settings_service import get_setting

TOP_LIMIT = 10  # обе breakdown-выборки -- топ-10 (спека фазы 6)
```

3. Добавить дата-классы ПЕРЕД `DailyStats` и расширить `DailyStats` (строки 21-28):

```python
@dataclass
class ModelUsageStat:
    model_code: str
    requests: int
    credits_spent: int
    cost_usd: float


@dataclass
class UserSpendStat:
    telegram_id: int
    credits_spent: int


@dataclass
class DailyStats:
    new_users: int
    payments_count: int
    payments_amount_rub: float
    ai_requests: int
    api_cost_usd: float
    errors: int
    revenue_credits: int
    revenue_rub_estimated: float
    margin_rub: float
    avg_cost_credits: float
    model_usage: list[ModelUsageStat]
    top_users_by_spend: list[UserSpendStat]
```

4. В `get_daily_stats` после существующего блока `errors` (строки 67-73) и ПЕРЕД `return DailyStats(...)` (строка 75) добавить новые запросы (revenue/margin — сразу после `api_cost` по смыслу, breakdown-списки в конце):

```python
    revenue_credits = (
        await session.execute(
            select(func.coalesce(func.sum(AIRequest.charged_credits), 0)).where(
                AIRequest.status == RequestStatus.completed,
                AIRequest.created_at >= day_start,
            )
        )
    ).scalar_one()

    defaults = PricingSettings()
    rub_per_credit = await get_setting(
        session, "rub_per_credit", cast=float, default=defaults.rub_per_credit
    )
    usd_to_rub_rate = await get_setting(
        session, "usd_to_rub_rate", cast=float, default=defaults.usd_to_rub_rate
    )
    revenue_rub_estimated = revenue_credits * rub_per_credit
    margin_rub = revenue_rub_estimated - float(api_cost) * usd_to_rub_rate
    avg_cost_credits = revenue_credits / ai_requests if ai_requests else 0.0

    model_spend = func.coalesce(func.sum(AIRequest.charged_credits), 0).label("credits_spent")
    model_rows = (
        await session.execute(
            select(
                AIRequest.model_code,
                func.count(AIRequest.id).label("requests"),
                model_spend,
                func.coalesce(func.sum(AIRequest.provider_cost_usd), 0).label("cost_usd"),
            )
            .where(AIRequest.created_at >= day_start)
            .group_by(AIRequest.model_code)
            .order_by(model_spend.desc())
            .limit(TOP_LIMIT)
        )
    ).all()
    model_usage = [
        ModelUsageStat(
            model_code=row.model_code,
            requests=row.requests,
            credits_spent=row.credits_spent,
            cost_usd=float(row.cost_usd),
        )
        for row in model_rows
    ]

    user_spend = func.coalesce(func.sum(AIRequest.charged_credits), 0).label("credits_spent")
    user_rows = (
        await session.execute(
            select(User.telegram_id, user_spend)
            .select_from(AIRequest)
            .join(User, User.id == AIRequest.user_id)
            .where(AIRequest.created_at >= day_start)
            # users.telegram_id уникален (unique index), поэтому группировка по нему
            # эквивалентна GROUP BY user_id из спеки и валидна на Postgres и sqlite.
            .group_by(User.telegram_id)
            .order_by(user_spend.desc())
            .limit(TOP_LIMIT)
        )
    ).all()
    top_users_by_spend = [
        UserSpendStat(telegram_id=row.telegram_id, credits_spent=row.credits_spent)
        for row in user_rows
    ]
```

5. Расширить `return DailyStats(...)` (строки 75-82):

```python
    return DailyStats(
        new_users=new_users,
        payments_count=payments_count,
        payments_amount_rub=float(payments_amount),
        ai_requests=ai_requests,
        api_cost_usd=float(api_cost),
        errors=errors,
        revenue_credits=revenue_credits,
        revenue_rub_estimated=revenue_rub_estimated,
        margin_rub=margin_rub,
        avg_cost_credits=avg_cost_credits,
        model_usage=model_usage,
        top_users_by_spend=top_users_by_spend,
    )
```

`get_monthly_stats` и `MonthlyStats` не трогать.

- [ ] **Step 4: Запустить тесты — убедиться, что зелёные**

```
python -m pytest tests/services/test_stats_service.py -v
```

- [ ] **Step 5: Закоммитить**

```
git add app/services/stats_service.py tests/services/test_stats_service.py
git commit -m "feat(stats): revenue/margin/avg + model_usage + top_users_by_spend (фаза 6, Task 4)"
```

---

### Task 5: Расширение `GET /admin/stats` (`StatsOut` + `ModelUsageOut`/`UserSpendOut`)

**Files:**
- Modify: `app/api/routes/admin.py`
- Test: `tests/api/test_admin.py`

**Interfaces:**
- Consumes: расширенный `DailyStats` из Task 4.
- Produces: JSON `GET /admin/stats` — существующие 6 `today_*`-полей в прежнем порядке, затем 4 новых `today_*`, затем `model_usage`/`top_users_by_spend`, затем прежние `month_*`. Ничего кроме stats-секции в `admin.py` не трогается.

- [ ] **Step 1: Обновить тест (падающим образом)**

В `tests/api/test_admin.py` заменить `test_stats_returns_v2_shape` (строки 79-92) на:

```python
async def test_stats_returns_v2_shape(client):
    response = await client.get("/api/admin/stats")

    assert response.status_code == 200
    assert response.json() == {
        "today_new_users": 1,  # alice создана "сейчас" (server_default now)
        "today_payments_count": 0,
        "today_payments_amount_rub": 0.0,
        "today_ai_requests": 0,
        "today_api_cost_usd": 0.0,
        "today_errors": 0,
        "today_revenue_credits": 0,
        "today_revenue_rub_estimated": 0.0,
        "today_margin_rub": 0.0,
        "today_avg_cost_credits": 0.0,
        "model_usage": [],
        "top_users_by_spend": [],
        "month_revenue_rub": 0.0,
        "month_credits_purchases_count": 0,
    }
```

Остальные тесты файла не трогать.

- [ ] **Step 2: Запустить тест — убедиться, что падает**

```
python -m pytest tests/api/test_admin.py::test_stats_returns_v2_shape -v
```

Ожидание: `AssertionError` — в ответе нет новых ключей.

- [ ] **Step 3: Реализовать**

В `app/api/routes/admin.py` stats-секция (строки 28-54) — итоговый вид:

```python
# --- stats -------------------------------------------------------------

class ModelUsageOut(BaseModel):
    model_code: str
    requests: int
    credits_spent: int
    cost_usd: float


class UserSpendOut(BaseModel):
    telegram_id: int
    credits_spent: int


class StatsOut(BaseModel):
    today_new_users: int
    today_payments_count: int
    today_payments_amount_rub: float
    today_ai_requests: int
    today_api_cost_usd: float
    today_errors: int
    today_revenue_credits: int
    today_revenue_rub_estimated: float
    today_margin_rub: float
    today_avg_cost_credits: float
    model_usage: list[ModelUsageOut]
    top_users_by_spend: list[UserSpendOut]
    month_revenue_rub: float
    month_credits_purchases_count: int


@router.get("/stats", response_model=StatsOut)
async def stats(session: AsyncSession = Depends(get_db)) -> StatsOut:
    daily = await get_daily_stats(session)
    monthly = await get_monthly_stats(session)
    return StatsOut(
        today_new_users=daily.new_users,
        today_payments_count=daily.payments_count,
        today_payments_amount_rub=daily.payments_amount_rub,
        today_ai_requests=daily.ai_requests,
        today_api_cost_usd=daily.api_cost_usd,
        today_errors=daily.errors,
        today_revenue_credits=daily.revenue_credits,
        today_revenue_rub_estimated=daily.revenue_rub_estimated,
        today_margin_rub=daily.margin_rub,
        today_avg_cost_credits=daily.avg_cost_credits,
        model_usage=[
            ModelUsageOut(
                model_code=m.model_code,
                requests=m.requests,
                credits_spent=m.credits_spent,
                cost_usd=m.cost_usd,
            )
            for m in daily.model_usage
        ],
        top_users_by_spend=[
            UserSpendOut(telegram_id=u.telegram_id, credits_spent=u.credits_spent)
            for u in daily.top_users_by_spend
        ],
        month_revenue_rub=monthly.revenue_rub,
        month_credits_purchases_count=monthly.credits_purchases_count,
    )
```

Импорты файла уже содержат всё нужное (`get_daily_stats`, `get_monthly_stats`, `BaseModel`); остальные секции (`users`/`payments`/`models`/`packages`/`settings`/`banners`) не трогать.

- [ ] **Step 4: Запустить тесты — убедиться, что зелёные**

```
python -m pytest tests/api/test_admin.py -v
```

Весь файл должен пройти.

- [ ] **Step 5: Закоммитить**

```
git add app/api/routes/admin.py tests/api/test_admin.py
git commit -m "feat(admin): /admin/stats v2 -- revenue/margin/breakdown-поля (фаза 6, Task 5)"
```

---

### Task 6: Финальная регрессия — полный прогон и `import app.main`

Фаза 6 — ПОСЛЕДНЯЯ фаза всего credit-system-v2 rebuild'а: этот шаг закрывает не только фазу, но и весь проект переписывания.

- [ ] **Step 1: Полный прогон тестовой сюиты**

```
python -m pytest -q
```

Ожидание: всё зелёное (единственный допустимый skip — `test_concurrent_webhook_delivery_settles_exactly_once` без `TEST_DATABASE_URL`). Любой красный тест — стоп, разбор через superpowers:systematic-debugging, НЕ «подгонка» теста.

- [ ] **Step 2: Регрессия импорта приложения**

```
python -c "import app.main"
```

Ожидание: завершение без ошибок (после фазы 5 проходит; фаза 6 не должна это сломать — новые импорты `stats_service -> settings_service -> pricing` ацикличны).

- [ ] **Step 3: Закоммитить (если были правки) и зафиксировать завершение**

Если Step 1-2 потребовали фиксов — закоммитить их отдельным коммитом с пояснением. Если всё зелёное сразу — коммит не нужен (код уже закоммичен по задачам); зафиксировать факт завершения фазы 6 согласно процессу (superpowers:finishing-a-development-branch решает merge/PR).

---

## Self-Review (выполнено при написании плана)

- **Spec coverage:** все пункты скоупа спеки покрыты задачами 1-5 (3 pricing-функции — Task 1; text-вставка — Task 2; media-вставка, оба варианта категорий — Task 3; 6 новых полей `DailyStats` + 2 дата-класса — Task 4; `StatsOut`/эндпойнт — Task 5); вне-скоуп спеки (OpenRouter `/generation`, агрегатная таблица, `MonthlyStats`) — явно исключён в Global Constraints. Миграция не требуется — подтверждено полем `ai_request.py:31`.
- **Отклонения от буквы спеки (осознанные, семантика сохранена):**
  - тест-хелперы `_media_model`/`_image_model`/`_video_model` не задавали `fixed_cost_usd` — расширены обратно-совместимым kwarg `fixed_cost_usd=0.0`;
  - `test_empty_db_returns_zero_stats` сравнивает `DailyStats` целиком — обновлён новыми нулевыми полями (спека это не упоминала, но без правки тест красный);
  - `top_users_by_spend`: спека даёт `GROUP BY user_id` c выборкой `users.telegram_id` — в плане `GROUP BY users.telegram_id` (уникален), т.к. группировка по не-PK с выборкой зависимой колонки невалидна на Postgres;
  - USD-значения в stats-тестах подобраны двоично-точные (0.25/0.5/0.125) — dataclass-сравнения списков без float-шума, `float()`-обёртки над `Decimal` из `Numeric`-колонок повторяют существующий паттерн `float(api_cost)`.
- **Placeholder scan:** «TBD»/«добавить позже»/пустых шагов нет; каждый Step содержит полный код или точную команду.
- **Type consistency:** `ModelUsageStat`/`ModelUsageOut` и `UserSpendStat`/`UserSpendOut` — поля 1:1; `revenue_credits: int` (SUM Integer), `*_rub`/`cost_usd`/`avg_cost_credits: float`; имена функций/полей сверены с реальными файлами на текущих строках.
