# Phase 5 — Admin + Antifraud (credit system v2 rebuild)

## Контекст

Фазы 1-4 credit system v2 (`docs/superpowers/specs/2026-07-08-credit-system-phase{1,2,3,4}-*-design.md`)
заменили `Tariff`/`Subscription`/`ModelConfig` на `AiModel`/`CreditPackage`/`Setting` +
кредитный движок (`app/services/credit_service.py`). Четыре файла до сих пор
импортируют удалённые модели и не могут быть импортированы, из-за чего
`app/main.py` не собирается с фазы 1:

- `app/api/routes/admin.py`
- `app/services/admin_service.py`
- `app/services/stats_service.py`
- `app/services/keys/key_healthcheck.py`

Плюс в ТЗ (`C:\Users\mccaq\Desktop\promt.md`) остаются нереализованными пункты
защиты от убытков: free-tier ограничения, daily spend limit, rate-limiting,
защита от повторной отправки. Это последняя нефункциональная дыра перед
Phase 6 (аналитика).

## Scope

**В скоуп:**
- Полный рерайт четырёх файлов выше под текущую схему (`AiModel`/`CreditPackage`/
  `Setting`/`CreditTransaction`/`AIRequest`).
- Новый `app/services/antifraud_service.py`: free-tier гейтинг, daily spend limit,
  rate-limit (user + model), защита от дублей.
- Минимальные вставки вызовов antifraud-проверок в `text_generation_service.py`
  и `media_generation_service.py` (не рерайт этих файлов — они остаются
  каркасом фаз 2-3, только обрастают вызовами guard-функций).
- Новые admin-эндпойнты: `/admin/packages`, `/admin/settings`,
  `/admin/users/{telegram_id}/transactions`,
  `/admin/users/{telegram_id}/credits` (grant + deduct).
- Новая функция `credit_service.adjust_credits_admin`.
- Новая функция `settings_service.set_setting`.
- Новые ключи `settings` (антифрод-пороги) + сиды.

**Вне скоупа (явные non-goals):**
- Phase 6: `/admin_stats` с revenue/margin/model-usage breakdown, заполнение
  `AIRequest.provider_cost_usd`. `stats_service.py` в этой фазе получает
  минимальный фикс под новую схему, не полную аналитику.
- `frontend-next/` — фронтенд не трогается (как во всех предыдущих фазах);
  экраны `AdminTariffs.tsx` и подобные останутся несовместимы с новым API
  до отдельной фазы выравнивания фронтенда. Это уже принятое решение с фазы 1.
- `Banner`, `referral_service.py`, `user_service.py` — не трогаются, уже
  совместимы с новой схемой.
- Telegram bot admin-команды (`/admin_models` и т.п. из ТЗ) — в проекте нет
  aiogram-хендлеров админки, есть только HTTP `/admin/*` API, потребляемый
  `frontend-next`. Именование команд из ТЗ трактуется как названия
  HTTP-ресурсов, а не bot-команд.

## Antifraud service (`app/services/antifraud_service.py`)

Чистый набор guard-функций поверх `redis_client` и `Setting`. Каждая функция
кидает своё исключение при нарушении, ничего не пишет в Postgres.

```python
class DuplicateRequestError(Exception): ...
class RateLimitExceededError(Exception): ...
class TierNotAllowedError(Exception): ...
class FreeTierLimitExceededError(Exception): ...
class DailySpendLimitExceededError(Exception): ...

@dataclass(frozen=True)
class AntifraudSettings:
    daily_spend_limit_credits: int = 10_000
    rate_limit_per_user_per_minute: int = 10
    rate_limit_per_model_per_minute: int = 60
    duplicate_cooldown_seconds: int = 5
    free_tier_credit_cap: int = 100

async def load_antifraud_settings(session) -> AntifraudSettings: ...

async def check_duplicate_request(user_id: int, model_code: str, prompt: str, *, settings: AntifraudSettings) -> None
async def check_rate_limits(user_id: int, model_code: str, *, settings: AntifraudSettings) -> None
async def check_tier_allowed(user: User, model: AiModel) -> None
async def check_free_tier_cap(user: User, estimated_credits: int, *, settings: AntifraudSettings) -> None
async def check_daily_spend_limit(user_id: int, estimated_credits: int, *, settings: AntifraudSettings) -> None
async def record_daily_spend(user_id: int, delta: int) -> None
```

### Redis-ключи

| Назначение | Ключ | TTL | Операция |
|---|---|---|---|
| Duplicate cooldown | `dup:{user_id}:{sha256(model_code+prompt)[:16]}` | `duplicate_cooldown_seconds` | `SET NX EX` |
| Rate limit (user) | `rate_limit:user:{user_id}:{minute_bucket}` | 60с | `INCR` + `EXPIRE` при первом инкременте |
| Rate limit (model, глобальный) | `rate_limit:model:{model_code}:{minute_bucket}` | 60с | то же |
| Daily spend | `daily_spend:{user_id}:{YYYY-MM-DD}` (UTC-день) | 25ч (страховка) | `INCRBY`/`DECRBY` |

`minute_bucket = int(time.time() // 60)` — фиксированные 60-секундные окна
(не скользящее окно; проще и достаточно для защиты от убытков, не для точного
throttling API).

Важное различие в семантике между двумя видами счётчиков:
- **Rate limit** (user и model) — `check_rate_limits` сам атомарно делает
  `INCR` и сравнивает результат с лимитом (`EXPIRE` ставится только когда
  `INCR` вернул `1`, т.е. это первый запрос в окне). Check и increment —
  одна операция, отдельного вызова "record" для rate-limit нет.
- **Daily spend** — `check_daily_spend_limit` только читает текущее значение
  (`GET`, без записи) и сравнивает `текущее + estimated` с лимитом; запись
  происходит отдельным вызовом `record_daily_spend` уже ПОСЛЕ успешного
  `reserve_credits` (см. порядок интеграции ниже) и на нём же лежит
  ответственность за `EXPIRE` при создании ключа. Разделение check/record
  обязательно: между проверкой и фактическим резервом ещё стоит
  confirmation-gate, который может прервать поток без записи.

### Порядок интеграции в `generate_text` / `start_media_generation`

Обе функции получают одинаковый набор вставок, до и после уже существующей
логики (текст фаз 2-3 не переписывается):

1. **До `ai_lock`** (быстрый и дешёвый отказ):
   1. `check_duplicate_request` — по хэшу `(model_code, prompt)`.
   2. `check_rate_limits` — user, затем model.
   3. `check_tier_allowed` — `total_credits_purchased == 0` и
      (`model.category == video` или `model.tier == ultra`) → отказ ещё до
      оценки стоимости.
2. **После оценки `estimated`, до confirmation-gate:**
   4. `check_free_tier_cap` — `total_credits_purchased == 0` и
      `total_credits_spent + estimated > free_tier_credit_cap` → отказ.
      Cumulative cap переиспользует существующие поля `User`, новых колонок
      не требует: raз пользователь ничего не покупал, весь его
      `total_credits_spent` — это трата free-кредитов.
   5. `check_daily_spend_limit` — `GET daily_spend:... + estimated > daily_spend_limit_credits`
      → отказ.
3. **После успешного `reserve_credits`:** `record_daily_spend(user_id, +estimated)`.
4. **На ветке `release`/`refund` (`settle_request`/`refund_request` уже
   возвращают достаточно данных вызывающему коду):** компенсирующий
   `record_daily_spend(user_id, -diff)` — вызывается в тех же местах
   generation-сервисов, где уже вызывается `settle_request`/`refund_request`.

Новые исключения маппятся в `chat.py`/`generate.py` рядом с уже существующими
`except`-блоками:
- `DuplicateRequestError` → 429, `"Слишком быстрый повтор запроса, подождите пару секунд"`.
- `RateLimitExceededError` → 429, `"Слишком много запросов, попробуйте через минуту"`.
- `TierNotAllowedError` → 403, `"Эта модель доступна после первой покупки пакета"`.
- `FreeTierLimitExceededError` → 402, `"Бесплатный лимит исчерпан, купите пакет кредитов"`.
- `DailySpendLimitExceededError` → 429, `"Дневной лимit трат исчерпан, попробуйте завтра"`.

### Новые ключи `settings` (сиды в `app/db/seed.py`)

```python
dict(key="daily_spend_limit_credits", value="10000", type="int", description="Дневной лимит трат на пользователя")
dict(key="rate_limit_per_user_per_minute", value="10", type="int", description="Rate limit запросов на пользователя")
dict(key="rate_limit_per_model_per_minute", value="60", type="int", description="Rate limit запросов на модель (глобально)")
dict(key="duplicate_cooldown_seconds", value="5", type="int", description="Окно блокировки повторного идентичного запроса")
dict(key="free_tier_credit_cap", value="100", type="int", description="Максимум бесплатных кредитов для непокупавших пользователей")
```

`settings_service.py` получает симметричную запись:

```python
async def set_setting(session, key: str, value: str, *, type_: str, description: str | None = None) -> Setting:
    """Upsert строки settings. Единственное место записи в таблицу settings."""
```

## `credit_service.adjust_credits_admin`

```python
async def adjust_credits_admin(
    session: AsyncSession, user_id: int, delta: int, *, reason: str
) -> CreditTransaction:
    """Ручная корректировка баланса админом: delta может быть отрицательным
    (списание) или положительным (начисление). В отличие от grant_credits/
    refund_request, НЕ трогает total_credits_purchased/total_credits_spent --
    это внебалансовая корректировка, а не покупка или трата по запросу.
    tx_type=CreditTxType.admin_adjustment. Списание ниже нуля запрещено
    (InsufficientBalanceError), начисление ограничений не имеет."""
```

Использует существующий `_lock_user`. Заменяет старый (нерабочий, использовал
несуществующий `CreditTxType.manual_adjustment`) вызов `grant_credits` из
`admin.py`.

## Admin API (`app/api/routes/admin.py` — полный рерайт)

Дерево эндпойнтов после рерайта:

- `GET /admin/stats` — как раньше, но данные из `stats_service.py` v2 (см. ниже).
- `GET /admin/users?query=` / `GET /admin/users/{telegram_id}` — без
  tariff/subscription полей, с `credits_balance`/`total_credits_purchased`/
  `total_credits_spent`.
- `GET /admin/users/{telegram_id}/transactions?limit=&offset=` — новый,
  постранично отдаёт `CreditTransaction` пользователя (новейшие первыми).
- `POST /admin/users/{telegram_id}/block` / `/unblock` — без изменений.
- `POST /admin/users/{telegram_id}/credits` `{amount: int}` — `amount` может
  быть отрицательным; вызывает `adjust_credits_admin`. Заменяет
  `grant-credits`, `grant` (tariff-подписка) и `cancel-subscription`, которых
  в новой схеме не существует.
- `GET /admin/payments` / `POST /admin/payments/{id}/refund` — без изменений
  (`Payment` не удалялась).
- `GET /admin/models` / `PATCH /admin/models/{code}` — на `AiModel`:
  `is_active`, `is_visible`, `recommended_credits`, `min_credits`,
  `provider_model_id`, `input_price_usd_per_1m_tokens`,
  `output_price_usd_per_1m_tokens`, `sort_order`.
- `GET /admin/packages` / `PATCH /admin/packages/{code}` — новый, на
  `CreditPackage`: `price_rub`, `price_stars`, `credits`, `is_active`.
  Полностью заменяет секцию `/admin/tariffs`.
- `GET /admin/settings` / `PATCH /admin/settings/{key}` — новый, читает/пишет
  через `settings_service.get_setting`/`set_setting`. `PATCH` принимает
  `{value: str}`, `type`/`description` не меняются при обновлении значения
  существующего ключа.
- `GET /admin/banners`, `POST`, `PATCH`, `DELETE /admin/banners/{id}` — без
  изменений.

## `stats_service.py` (минимальный фикс, не Phase 6 аналитика)

`DailyStats`/`MonthlyStats` пересобираются под новую схему без добавления
новых метрик:

- `new_users` — без изменений (`User.created_at`).
- `payments_count`/`payments_amount_rub` — без изменений (`Payment`,
  `PaymentStatus.succeeded`), таблица не удалялась.
- `ai_requests` — без изменений (`AIRequest.created_at`).
- `api_cost_usd` — читает `AIRequest.provider_cost_usd` как раньше; поле
  существует, но ни одна фаза его не заполняет — будет стабильно возвращать
  `0.0` до Phase 6. Не в скоупе чинить сбор фактической себестоимости сейчас.
- `errors` — `RequestStatus.failed` вместо несуществующего `RequestStatus.error`.
- `MonthlyStats.active_subscriptions` — поля `Subscription` больше нет;
  заменяется на `credits_purchases_count` (число `CreditTransaction` с
  `type=purchase` за месяц) как ближайший осмысленный аналог "активности".

## `key_healthcheck.py` (рерайт под 2 провайдера)

Провайдеров в каталоге теперь ровно два (`ModelProvider.openrouter`,
`ModelProvider.fal`), поле `key_purpose` на `AiModel` не существует (в отличие
от старого `ModelConfig`). Purpose выводится из `ModelCategory`:

```python
_CATEGORY_TO_PURPOSE = {
    ModelCategory.text: KeyPurpose.TEXT,
    ModelCategory.image: KeyPurpose.IMAGE,
    ModelCategory.video: KeyPurpose.VIDEO,
}
_DB_PROVIDER_TO_KEY_PROVIDER = {
    ModelProvider.openrouter: Provider.OPENROUTER,
    ModelProvider.fal: Provider.FAL,
}
```

Остальная логика (лог `[OK]`/`[MISSING]`, никогда не роняет старт) без
изменений.

## Тестирование

- `tests/services/test_antifraud_service.py` (новый) — по одному тесту на
  каждую guard-функцию: happy path, отказ на пороге, отказ за порогом,
  сброс после истечения TTL/минуты (`freezegun` или ручной сдвиг
  `minute_bucket`, как принято в проекте).
- `tests/services/test_text_generation_service.py` /
  `test_media_generation_service.py` — расширить `FakeRedis` (сейчас
  поддерживает только `set`/`delete`) методами `get`/`incr`/`incrby`/
  `expire`, иначе новые вызовы `antifraud_service` в этих файлах упадут при
  тестах. Добавить тесты на: rate-limit-отказ, duplicate-отказ, free-tier
  gate (video/ultra), free-tier cap, daily-limit-отказ, и что daily-spend
  корректно декрементируется при release/refund.
- `tests/api/test_admin.py` (новый, если директории `tests/api/` ещё нет —
  завести) — по happy-path тесту на каждый новый/переписанный эндпойнт:
  models PATCH, packages PATCH, settings GET/PATCH, users credits (grant и
  deduct), users/transactions.
- `tests/services/test_credit_service.py` — добавить тесты на
  `adjust_credits_admin` (положительная/отрицательная дельта, запрет ухода
  в минус, что `total_credits_purchased/spent` не меняются).
- Regression: `python -c "import app.main"` должен проходить без ошибок —
  это прямой критерий готовности фазы (сейчас падает).

## Миграция

Одна alembic-ревизия, `down_revision = "e6f7a8b9c0d1"` (текущий head после
Phase 4): вставка пяти новых строк `settings` (см. выше) через `op.bulk_insert`
по образцу существующих сидов в `app/db/seed.py` / прошлых миграций фаз 1-4.
Никаких изменений схемы таблиц не требуется — все новые механизмы (rate-limit,
daily-spend, dedup) живут в Redis, free-tier cap переиспользует существующие
поля `User`.
