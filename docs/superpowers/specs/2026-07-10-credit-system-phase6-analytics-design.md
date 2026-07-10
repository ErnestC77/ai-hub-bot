# Phase 6 — Analytics (`/admin_stats` v2)

## Контекст

Последняя фаза credit system v2 rebuild (фазы 1-5 смёржены в master,
`docs/superpowers/specs/2026-07-08-credit-system-phase{1,2,3,4}-*-design.md`,
`docs/superpowers/specs/2026-07-10-credit-system-phase5-admin-antifraud-design.md`).
ТЗ (`C:\Users\mccaq\Desktop\promt.md`, раздел «Логи и аналитика») требует:

- сколько запросов по каждой модели, выручка в кредитах, себестоимость в USD,
  примерная маржа в RUB, топ пользователей по расходу, ошибки провайдеров,
  средняя стоимость запроса;
- `/admin_stats`: today revenue credits, today estimated revenue RUB,
  today provider cost USD, today margin RUB, model usage breakdown.

Ничего из этого не реализовано. `app/services/stats_service.py` после фазы 5
даёт только базовые счётчики под новую схему (`new_users`/`payments_count`/
`payments_amount_rub`/`ai_requests`/`api_cost_usd`/`errors` +
`credits_purchases_count`) — `api_cost_usd` стабильно равен `0.0`, потому что
`AIRequest.provider_cost_usd` (поле есть в схеме с фазы 1) ни одна фаза не
заполняла.

## Scope

**В скоуп:**
- Заполнение `AIRequest.provider_cost_usd` для text (OpenRouter) и media
  (fal.ai) запросов.
- Три новые чистые функции в `pricing.py`: `calculate_api_cost_usd` (text),
  `calculate_image_api_cost_usd`, `calculate_video_api_cost_usd` (media —
  зеркалирует существующее разделение `calculate_image_credits`/
  `calculate_video_credits` на две функции, не одну общую).
- Точечные вставки вызовов этих функций в `text_generation_service.py` /
  `media_generation_service.py` (не рерайт — по образцу фазы 5).
- Расширение `DailyStats` в `stats_service.py`: `revenue_credits`,
  `revenue_rub_estimated`, `margin_rub`, `avg_cost_credits`, `model_usage`,
  `top_users_by_spend`. `api_cost_usd`/`errors`/остальные существующие поля
  не меняются.
- Расширение `StatsOut` и `GET /admin/stats` в `admin.py` этими же полями.

**Вне скоупа:**
- Реальный вызов OpenRouter `/generation`-эндпойнта или `usage.include_cost`
  за фактической себестоимостью — используется расчёт по тем же ценам
  (`input_price_usd_per_1m_tokens`/`output_price_usd_per_1m_tokens`), что уже
  используются для биллинга пользователя. Обоснование: это тот же источник
  цены, что и в `calculate_text_credits`, без дополнительного round-trip'а
  к провайдеру на каждый запрос.
- Отдельная агрегированная таблица под model/user breakdown — агрегация на
  лету по `ai_requests` (`GROUP BY`), без новой схемы. При росте объёма
  запросов это можно будет оптимизировать в отдельной последующей работе,
  но сейчас — YAGNI.
- `MonthlyStats` (revenue_rub/credits_purchases_count) не расширяется этой
  фазой — ТЗ просит `/admin_stats` "today"-метрики, месячные метрики уже
  закрыты фазой 5.

## Заполнение `AIRequest.provider_cost_usd`

### Text (`pricing.calculate_api_cost_usd`)

```python
def calculate_api_cost_usd(model: AiModel, input_tokens: int, output_tokens: int) -> float:
    """Реальная себестоимость запроса в USD -- те же цены модели, что и в
    calculate_text_credits (шаги 1-2 ТЗ), но без конвертации в рубли/кредиты
    и без применения provider_fee_multiplier/margin_multiplier (это НАША
    внутренняя себестоимость, не то, что платит пользователь)."""
    input_cost_usd = input_tokens / 1_000_000 * float(model.input_price_usd_per_1m_tokens)
    output_cost_usd = output_tokens / 1_000_000 * float(model.output_price_usd_per_1m_tokens)
    return input_cost_usd + output_cost_usd
```

Интеграция в `text_generation_service.generate_text`: сразу после блока, где
уже считается `actual = calculate_text_credits(model, result.input_tokens,
result.output_tokens, settings=pricing)` (текущие строки ~161-163), добавить:

```python
request.provider_cost_usd = calculate_api_cost_usd(
    model, result.input_tokens, result.output_tokens
)
```

До вызова `settle_request` (который не трогает `provider_cost_usd` — это не
часть кредитного леджера, обычная колонка `AIRequest`, как уже `input_tokens`/
`output_tokens`, которые сервис пишет напрямую).

### Media (`pricing.calculate_image_api_cost_usd` / `calculate_video_api_cost_usd`)

Зеркалирует существующее разделение на ДВЕ функции (`calculate_image_credits`/
`calculate_video_credits` — не одна общая), с теми же сигнатурами параметров,
только через `fixed_cost_usd` вместо `recommended_credits`:

```python
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

(`VIDEO_BASE_SECONDS` уже существует в `pricing.py` с фазы 3, переиспользуется.)

Считаются на **reserve** (не на settle) — в отличие от text, у fal.ai нет
обратной связи по фактическому расходу: actual в медиа-flow всегда равен
estimated (см. фазу 5, `media_generation_service.handle_fal_webhook` всегда
settle'ит по `estimated_credits`).

Интеграция в `media_generation_service.start_media_generation`: в блоке, где
уже считается `estimated` (текущие строки ~99-108: `if model.category ==
ModelCategory.image: estimated = calculate_image_credits(model, quantity=1,
megapixels=1.0, is_edit=...) ... else: estimated = calculate_video_credits(
model, duration_seconds=...)`), добавить параллельный вызов
`calculate_image_api_cost_usd`/`calculate_video_api_cost_usd` с теми же
аргументами (`quantity=1, megapixels=1.0` / `duration_seconds=...`) и
записать результат в `request.provider_cost_usd` при создании `AIRequest`
(текущий блок `request = AIRequest(...)`, строки ~120-129) — новое
именованное поле в конструкторе рядом с `estimated_credits`.

## Расширение `stats_service.py`

`DailyStats` получает шесть новых полей (дополняют существующие, не заменяют):

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

Все новые метрики — окно "сегодня" (тот же `day_start`, что уже используется
в `get_daily_stats`), топ-10 записей для обоих списков.

- `revenue_credits` = `SUM(AIRequest.charged_credits)` где
  `status == RequestStatus.completed AND created_at >= day_start`.
- `revenue_rub_estimated` = `revenue_credits * rub_per_credit` (значение из
  `settings_service.get_setting(session, "rub_per_credit", cast=float, ...)` —
  тот же ключ, что уже читает `pricing.load_pricing_settings`).
- `margin_rub` = `revenue_rub_estimated - api_cost_usd * usd_to_rub_rate`
  (тот же ключ `usd_to_rub_rate`).
- `avg_cost_credits` = `revenue_credits / ai_requests`, `0.0` при
  `ai_requests == 0` (защита от деления на ноль).
- `model_usage` = `SELECT model_code, COUNT(*), SUM(charged_credits),
  SUM(provider_cost_usd) FROM ai_requests WHERE created_at >= day_start
  GROUP BY model_code ORDER BY SUM(charged_credits) DESC LIMIT 10`.
- `top_users_by_spend` = `SELECT ai_requests.user_id, users.telegram_id,
  SUM(charged_credits) FROM ai_requests JOIN users ... WHERE created_at >=
  day_start GROUP BY user_id ORDER BY SUM(charged_credits) DESC LIMIT 10`.

`get_daily_stats` подписывает новые запросы после уже существующих (порядок
запросов внутри функции не важен для корректности, важен только для
читаемости — держим рядом по смыслу: revenue/margin после `api_cost`,
breakdown-списки в конце).

`MonthlyStats` не меняется.

## `admin.py` (`GET /admin/stats`)

`StatsOut` расширяется соответствующими `today_*`-полями + двумя списками:

```python
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
```

Существующие поля и их порядок в начале схемы не трогаются (обратная
совместимость с уже написанными тестами `test_stats_returns_v2_shape` из
фазы 5 — тест обновляется, но структура запроса/эндпойнта не меняется).

## Тестирование

- `tests/services/test_pricing.py` — новые тесты на `calculate_api_cost_usd`
  (несколько комбинаций input/output tokens), `calculate_image_api_cost_usd`
  (ветки `cost_unit=image` и `cost_unit=megapixel` + ошибка на
  неподдерживаемый `cost_unit`), `calculate_video_api_cost_usd` (ветки
  `cost_unit=second` и `cost_unit=video` + ошибка на неподдерживаемый
  `cost_unit`).
- `tests/services/test_text_generation_service.py` — тест, что после успешной
  генерации `request.provider_cost_usd` заполнен корректным значением
  (не 0.0), посчитанным по факту usage от `FakeProvider`.
- `tests/services/test_media_generation_service.py` — тест, что после
  `start_media_generation` (image и video) `request.provider_cost_usd`
  заполнен корректным значением на основе `fixed_cost_usd`/`cost_unit`.
- `tests/services/test_stats_service.py` — расширить существующие фикстуры
  реальными `charged_credits`/`provider_cost_usd`/`model_code`/`user_id` на
  нескольких `AIRequest`-строках, проверить точные значения `revenue_credits`,
  `revenue_rub_estimated`, `margin_rub`, `avg_cost_credits`, порядок и состав
  `model_usage`/`top_users_by_spend` (включая обрезку по топ-10 и сортировку
  по убыванию), и границу "не сегодня" (как уже сделано для существующих
  полей).
- `tests/api/test_admin.py` — обновить `test_stats_returns_v2_shape` под
  новую форму ответа.

## Миграция

Не требуется — `AIRequest.provider_cost_usd` уже существует в схеме с фазы 1,
эта фаза только начинает его заполнять. Никаких изменений таблиц.
