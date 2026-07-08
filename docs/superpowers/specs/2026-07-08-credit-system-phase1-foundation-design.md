# Кредитная система v2 — Фаза 1: фундамент (БД + движок кредитов)

## Контекст

`ai-hub-bot` переходит на новую коммерческую модель: единая кредитная система
поверх двух провайдеров — OpenRouter (текст) и fal.ai (изображения/видео).
Полное ТЗ — `C:\Users\mccaq\Desktop\promt.md`.

Решения, принятые до этого документа:

- **Полная замена** текущей кредитной/модельной схемы (`ModelConfig`,
  `credit_service`, `credit_packages.py`), а не сосуществование с ней.
- **Тарифы/подписки удаляются полностью**: `Tariff`, `Subscription`,
  `UsageLimit` и связанный `subscription_service`/`usage_limit`-код уходят.
  Всё платное использование идёт только через кредиты.
- Работа разбита на 6 фаз (фундамент → OpenRouter → fal.ai → пакеты/платежи →
  админка/антифрод → аналитика/уборка). Этот документ описывает **только
  фазу 1**: схему данных и движок кредитов, без интеграции с провайдерами,
  без бот-команд, без админки.
- Баланс пользователя становится **хранимым полем** (`users.credits_balance`),
  обновляемым под блокировкой строки (`SELECT ... FOR UPDATE`), а не
  вычисляется как `SUM(credit_transactions.amount)`, как в текущем коде. Это
  осознанный отход от текущего паттерна — требуется явно ТЗ (шаги
  reserve/release, "получить пользователя с блокировкой строки").
- Найденная security-уязвимость (`credit_cost_override` от клиента в
  `app/api/routes/generate.py` / `app/services/generation_service.py`)
  закрывается тем, что оба файла полностью переписываются в фазах 2–3; в этой
  фазе они не трогаются, т.к. ещё не подключён ни один провайдер.

## Модель данных

### `users` (правки существующей таблицы)

Добавляются столбцы:

- `credits_balance: int` (default 0) — хранимый баланс, единственный источник
  истины для проверки `balance >= amount`.
- `total_credits_purchased: int` (default 0)
- `total_credits_spent: int` (default 0)
- `default_model_code: str | None` — выбранная пользователем модель по
  умолчанию (заменяет `active_model`, который переименовывается).

`active_model` → переименовать в `default_model_code` (данные переносятся
миграцией `ALTER TABLE ... RENAME COLUMN`, не дропаются).

### `credit_transactions` (пересоздаётся)

| поле | тип | примечание |
|---|---|---|
| id | PK | |
| user_id | FK users | |
| type | enum: purchase/spend/refund/reserve/release/admin_adjustment | заменяет старый `CreditTxType` |
| amount | int, **signed** | reserve/spend — отрицательные; purchase/refund/release — положительные |
| balance_before | int | снимок до операции |
| balance_after | int | снимок после операции |
| provider | str \| null | `openrouter` / `fal` / null для purchase/admin |
| model_code | str \| null | |
| request_id | FK ai_requests \| null | |
| description | str \| null | человекочитаемая причина (аналог текущего `reason`) |
| metadata_json | JSON \| null | произвольные доп. данные (например, разбивка токенов) |
| created_at | timestamptz | |

Старый `payment_id` FK убирается из этой таблицы (связь платёж→начисление
кредитов будет через `type=purchase` + `metadata_json`, платёжный флоу — фаза 4).

### `ai_requests` (пересоздаётся)

| поле | тип | примечание |
|---|---|---|
| id | PK | |
| user_id | FK users | |
| provider | str | `openrouter` / `fal` |
| model_code | str | ссылается на `ai_models.code` |
| category | enum: text/image/video | |
| status | enum: pending/reserved/processing/completed/failed/refunded | |
| prompt_preview | str (обрезанный prompt, напр. 200 симв.) | заменяет полный `prompt`/`answer` — полные тексты не обязательны для биллинга-таблицы |
| input_tokens, output_tokens | int, default 0 | |
| estimated_credits | int | расчёт до запроса |
| reserved_credits | int | фактически удержано |
| charged_credits | int | итоговое списание |
| provider_cost_usd | numeric(12,6) | |
| provider_response_id | str \| null | id ответа у провайдера (замена `provider_task_id`) |
| error_message | text \| null | |
| created_at, completed_at | timestamptz | |

### `ai_models` (новая)

Поля точно по ТЗ: `id, provider, category, code, display_name,
provider_model_id, tier, input_price_usd_per_1m_tokens,
output_price_usd_per_1m_tokens, fixed_cost_usd, cost_unit, min_credits,
recommended_credits, max_context_tokens, is_active, is_visible, sort_order,
created_at, updated_at`.

`tier`: enum `economy/standard/premium/pro/ultra`. `cost_unit`: enum
`tokens/image/megapixel/second/video`. `category`: enum `text/image/video`
(переиспользуем название, но это **новый** enum — не путать со старым
`ModelCategory.fast/medium/premium/image/video`, который удаляется).

### `credit_packages` (новая таблица взамен `app/services/credit_packages.py`)

Поля по ТЗ: `id, code, title, credits, price_rub, description, is_active,
created_at, updated_at`. Сиды — 5 пакетов START/BASIC/PLUS/PRO/BUSINESS из
ТЗ. (Использование в оплате — фаза 4; в этой фазе только таблица + сиды.)

### `settings` (новая)

`key (str, PK), value (str), type (str: int/float/str/bool), description (str
\| null), updated_at`. Стартовые записи:

- `usd_to_rub_rate = 80`
- `rub_per_credit = 0.10`
- `provider_fee_multiplier = 1.15`
- `margin_multiplier = 2.5`
- `minimum_text_credits = 3`

Читаются через тонкий helper `get_setting(session, key, cast=...)` с
дефолтом на случай отсутствия строки (защита от пустой БД до первого сида).

### Удаляемые таблицы/файлы

- `app/db/models/tariff.py`, `subscription.py`, `usage_limit.py` (модели)
- `app/services/subscription_service.py`, `app/services/limit_service.py`,
  `app/services/limit_fields.py`
- `app/services/credit_packages.py` (dataclass-список) → заменяется таблицей
- `app/db/models/model_config.py` → заменяется `ai_models.py`
- Соответствующие enum'ы `SubscriptionStatus`, старый `ModelCategory`,
  `ModelProvider` (заменяется на openrouter/fal), `CreditTxType` (заменяется
  новым набором значений)

`Banner`, `Payment`, `Referral` — не трогаются в этой фазе.

## Миграции

Одна alembic-миграция `phase1_credit_system_v2`:

1. `ALTER TABLE users` — добавить новые колонки (`credits_balance` и др.,
   default 0), переименовать `active_model` → `default_model_code`.
2. Data-migration шаг (тот же ревизии): для каждого существующего `user_id`
   посчитать текущий `SUM(credit_transactions.amount)` и записать в
   `users.credits_balance` (проект ещё не запущен в платном режиме —
   реальных пользовательских балансов на проде нет, но шаг делается
   безусловно, чтобы миграция была безопасна и на dev/staging, где тестовые
   данные могут быть).
3. `DROP TABLE` для tariffs, subscriptions, usage_limits, model_configs.
4. Пересоздать `credit_transactions`, `ai_requests` с новой схемой (см. выше).
5. Создать `ai_models`, `credit_packages`, `settings`.
6. Новые enum-типы в Postgres (SQLAlchemy `Enum`), удалить старые.

## Движок кредитов — `app/services/credit_service.py` (переписывается)

Все операции — внутри одной DB-транзакции, с `SELECT ... FOR UPDATE` на
строку `users`.

```
async def reserve_credits(session, user_id, amount, *, request_id, provider, model_code) -> CreditTransaction
```
- Лочит `users` строку, читает `credits_balance`.
- Если `balance < amount` → `InsufficientBalanceError` (ничего не пишет).
- Иначе: `balance_after = balance_before - amount`, обновляет
  `users.credits_balance`, создаёт transaction `type=reserve, amount=-amount`.

```
async def settle_request(session, request, actual_credits) -> CreditTransaction
```
Реализует шаги 6–9 из ТЗ:
- `actual_credits < reserved_credits` → создать `type=release,
  amount=+(reserved-actual)`, вернуть разницу на баланс.
- `actual_credits > reserved_credits`:
  - если `balance >= (actual-reserved)` → списать доплату
    (`type=spend, amount=-(actual-reserved)`).
  - если баланса не хватает → списать 0 доплаты, `request.status` помечается
    флагом `insufficient_balance_after_usage=True` (доп. булево поле на
    `ai_requests`), `charged_credits = reserved_credits`.
- Обновляет `ai_requests.charged_credits`, `status=completed`.

```
async def refund_request(session, request, *, reason) -> CreditTransaction
```
- Полный возврат `reserved_credits` (или `charged_credits`, если уже
  списано) при ошибке провайдера. `type=refund`, `status=refunded`.

```
async def grant_credits(session, user_id, amount, *, reason, tx_type=purchase) -> CreditTransaction
```
- Используется фазой 4 (покупка) и админкой (фаза 5). В этой фазе — только
  функция + тесты, без вызывающего кода.

Общий принцип: **никогда** не обновлять `credits_balance` вне этих функций;
`credit_transactions` — неизменяемый аудит-лог с `balance_before/after`.

## Функции расчёта — `app/services/pricing.py` (новый файл)

`calculate_text_credits(model, input_tokens, output_tokens, *, settings) -> int` —
формула 1:1 из ТЗ (шаги 1–8), читает `usd_to_rub_rate`,
`provider_fee_multiplier`, `margin_multiplier`, `rub_per_credit` из
`settings`-таблицы; `finalCredits = max(credits, model.min_credits)`.

`calculate_image_credits(model, quantity, megapixels, *, is_edit=False) -> int` —
`cost_unit=image` → `quantity * model.recommended_credits`; `cost_unit=megapixel`
→ `ceil(quantity * megapixels * model.recommended_credits)`; `is_edit=True` →
`x1.5`, но не меньше 100.

`calculate_video_credits(model, duration_seconds) -> int` —
`cost_unit=second` → `ceil(duration_seconds/5 * model.recommended_credits)`;
`cost_unit=video` → `model.recommended_credits`; итог не меньше 500.

Все три — чистые функции (без DB-записи), покрываются юнит-тестами на
граничные случаи (min_credits форсирует минимум, ceil-округление).

## Seed (`app/db/seed.py`, переписывается)

- 5 `credit_packages` (START…BUSINESS) из ТЗ.
- 5 `settings` записей из раздела выше.
- 20 `ai_models`: 12 text (DeepSeek V3 … Claude Opus), 4 image (Qwen Image,
  Seedream, Flux Kontext Pro, Nano Banana), 4 video (Ovi, Wan, Kling, Veo) —
  поля `provider_model_id`, `input_price_usd_per_1m_tokens` и т.п. заполняются
  плейсхолдерами с явным комментарием "уточнить перед продакшн-запуском"
  (ТЗ прямо говорит: реальные provider_model_id и цены — из конфига, не
  хардкодить бизнес-логику под конкретную модель).
- `Banner` сиды — переносятся как есть (не относятся к кредитам).

## Тесты (`tests/services/`)

- `test_pricing.py` — все три функции расчёта, включая: `credits <
  min_credits` → форсируется min; округление `ceil`; `is_edit` множитель и
  его минимум 100; видео — минимум 500.
- `test_credit_service.py`:
  - `reserve_credits` при нехватке баланса → `InsufficientBalanceError`,
    баланс не меняется.
  - `settle_request`: `actual < reserved` (release), `actual > reserved` и
    хватает баланса (доплата), `actual > reserved` и не хватает
    (`insufficient_balance_after_usage=True`, без ошибки).
  - `refund_request` — полный возврат.
  - Конкурентный reserve (два параллельных вызова на одном user_id) —
    проверка, что блокировка строки не даёт списать больше баланса
    (интеграционный тест с реальной БД, не мок).

## Явно вне рамок фазы 1

OpenRouterClient, FalClient, бот-команды (`/balance`, `/buy`, `/models`),
админ-команды, PaymentProvider, антифрод (rate limit, idempotency,
daily spend limit), `/admin_stats`. Эти пункты — фазы 2–6, каждая получит
свой spec перед реализацией.
