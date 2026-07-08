# Кредитная система v2 — Фаза 2: OpenRouter + текстовый flow

## Контекст

Фаза 1 (`docs/superpowers/specs/2026-07-08-credit-system-phase1-foundation-design.md`,
план `docs/superpowers/plans/2026-07-08-credit-system-phase1-foundation.md`)
построила фундамент: `ai_models`/`credit_packages`/`settings`, движок
кредитов (`reserve_credits`/`settle_request`/`refund_request`/`grant_credits`
в `app/services/credit_service.py`) и чистые функции расчёта
(`app/services/pricing.py`). Она удалила старую схему (`ModelConfig`,
`Tariff`, `Subscription`, `UsageLimit`) целиком, оставив весь старый
текстовый pipeline (`app/services/ai/ai_router.py`, `access_service.py`,
`cost_service.py`, `ai/registry.py`, провайдеры `claude_service.py` /
`deepseek_service.py` / `gemini_service.py` / `openai_service.py`,
`app/api/routes/tariffs.py`, часть `me.py`) с неразрешимыми импортами
удалённых символов — намеренно, по плану фазы 1 (полный список — в
"Known accepted breakage" плана фазы 1).

Полное ТЗ: `C:\Users\mccaq\Desktop\promt.md`.

Эта фаза — **только бэкенд** (FastAPI API-эндпоинты, без изменений в
`frontend-next`). Из ТЗ команды `/balance`, `/models`, `/buy` реализуются как
API-эндпоинты в стиле уже существующих `/api/me`, `/api/chat` — этот проект
Mini App, а не классический бот со slash-командами.

## Решения, принятые до этого документа

- **Полная замена** старого текстового pipeline, а не точечный ремонт: старые
  файлы жёстко завязаны на удалённые `ModelConfig`/`Tariff`/`UsageLimit`
  (registry по provider, а не по tier; `access_service.check_access` — 7
  проверок против тарифной квоты, которой больше не существует). Чинить
  нечего — переписываем на новых основаниях (`AiModel` + `credit_service`).
- **`OpenRouterProvider` следует существующему паттерну `DeepSeekProvider`**
  (`app/services/ai/deepseek_service.py`): и DeepSeek, и OpenRouter дают
  OpenAI-совместимый chat-completions API, так что достаточно
  `AsyncOpenAI(api_key=..., base_url="https://openrouter.ai/api/v1")` —
  новых pip-зависимостей не требуется.
- **`fallback_model_code` добавляется в `ai_models`** новой миграцией поверх
  фазы 1 (в исходном каталоге фазы 1 такого поля не было) — ТЗ явно требует
  fallback-логику для текстовых моделей.
- Простой per-user Redis-лок на время генерации (как был в старом
  `ai_router.py`) сохраняется — предотвращает гонку параллельных запросов
  одного пользователя к одной и той же дорогой модели. Полноценный
  rate-limit / daily spend limit — это фаза 5, здесь не реализуется.

## Модель данных: миграция `ai_models.fallback_model_code`

Один новый nullable-столбец:

```python
fallback_model_code: Mapped[str | None] = mapped_column(String(64))
```

Без FK-констрейнта на `ai_models.code` (self-referencing FK на ту же
таблицу через код, не id, усложняет миграцию без реальной пользы — код
валидирует существование fallback-модели на уровне сервиса, не на уровне БД).
Alembic-миграция добавляет столбец с `server_default=NULL`; сиды фазы 1 не
меняются (fallback опционален, у существующих 12 текстовых моделей поле
остаётся `NULL`, кроме нескольких вручную заданных пар: `gpt_premium` →
`gemini_flash`, `claude_opus` → `claude_sonnet` — экономные fallback-и на
модель того же или более низкого tier, чтобы деградация не случайно
включала подтверждение по цене в обычном случае).

## Удаляемые файлы

- `app/services/ai/ai_router.py`, `access_service.py`, `cost_service.py`,
  `ai/registry.py`
- `app/services/ai/claude_service.py`, `deepseek_service.py`,
  `gemini_service.py`, `openai_service.py` (текстовые провайдеры под старый
  `ModelProvider` enum — заменяются одним `OpenRouterProvider`)
- `app/api/routes/tariffs.py`
- Из `app/api/schemas.py`: `CategoryLimitOut`, `LimitsOut`,
  `SubscriptionStatusOut`; `MeOut` упрощается (см. ниже)
- Соответствующие тесты, если они существуют и не собираются после удаления
  (на момент фазы 1 relevant тесты уже были удалены — `test_access_service.py`,
  `test_generation_service.py`, `test_generate_routes.py`)

`app/services/ai/base.py` (`AIProvider`, `AIResult`, `AIError`) и
`app/services/ai/image_service.py`/`piapi_client.py` — не трогаем
(`image_service.py`/`piapi_client.py` — фаза 3; `base.py` переиспользуется,
только его импорт `from app.db.models import ModelConfig` меняется на
`AiModel`).

## Новые файлы

### `app/services/ai/openrouter_service.py`

```python
class OpenRouterProvider(AIProvider):
    async def generate(
        self, model: AiModel, prompt: str, max_output_tokens: int, extra: dict | None = None
    ) -> AIResult: ...
```

Использует `get_key_manager().get_key(Provider.OPENROUTER, KeyPurpose.TEXT)`
(новая связка purpose→field в `api_key_manager.py`: `KeyPurpose.TEXT` →
`OpenRouterSettings.api_key`, новое поле рядом с уже существующими
`fallback_key`/`dev_key`). `model=model.provider_model_id` (не `model.code`
— пользовательский код никогда не уходит к провайдеру). Возвращает
`AIResult(answer, input_tokens, output_tokens)` из `response.usage`, как
`DeepSeekProvider`. Ошибки OpenRouter (HTTP/таймаут/невалидный ответ) —
`AIError` с логированием реальной причины (пользователю не показывается).

### `app/services/text_generation_service.py`

Заменяет `ai_router.py`. Основная функция:

```python
async def generate_text(
    session: AsyncSession, user: User, model_code: str, prompt: str, *, confirm: bool = False
) -> TextGenerationResult
```

Поток:
1. `model = get AiModel by code, category=text, is_active=True` (иначе
   `ModelNotFoundError`/`ModelUnavailableError` → пробуем `fallback_model_code`,
   если задан; если fallback тоже недоступен — `AIError`).
2. Redis-лок `ai_lock:{user.id}` (TTL как в старом коде) — если занят,
   `RequestInProgressError`.
3. Оценка: `input_tokens=2000, output_tokens=1000` (дефолты из ТЗ) →
   `calculate_text_credits(model, 2000, 1000, settings=pricing_settings)`.
4. Если `estimated_credits > 100` и `confirm=False` →
   `ConfirmationRequiredError(estimated_credits)` (лок снимается, ничего не
   резервируется) — вызывающий код (роут) превращает это в HTTP 409.
5. Если fallback дороже основной модели (по `recommended_credits`) и
   `confirm=False` при переходе на fallback — та же `ConfirmationRequiredError`.
6. `AIRequest` создаётся (`status=pending`), `reserve_credits(...)` →
   `status` на объекте выставляется в `reserved` (это ответственность
   вызывающего кода, не `credit_service` — см. Task 5 фазы 1: `reserve_credits`
   не трогает `AIRequest.status`).
7. Вызов `OpenRouterProvider.generate(model, prompt, max_output_tokens=TIER_MAX[model.tier])`.
   `TIER_MAX = {economy: 1000, standard: 2000, premium: 4000, pro: 8000, ultra: 12000}`
   (из ТЗ, "Ограничить max_output_tokens по tier").
8. При `AIError` — `refund_request(...)`, `status=failed` вручную не
   выставляется отдельно (refund уже переводит в `refunded`); лок снимается;
   исключение поднимается дальше как `AIError`.
9. При успехе — пересчёт `calculate_text_credits(model, result.input_tokens, result.output_tokens, settings=...)`
   → `settle_request(session, request, actual_credits)`.
10. Лок снимается (`finally`).
11. Возврат `TextGenerationResult(answer, charged_credits, balance_after)`.

## API-поверхность

### `GET /api/models`

Переписывается: читает `AiModel` где `category=text, is_visible=True,
is_active=True`, сортировка по `sort_order`. Отдаёт только
`code/display_name/tier/min_credits/recommended_credits` —
`provider_model_id` никогда не уходит в ответ (ТЗ: "не показывать
пользователю технические provider_model_id").

### `POST /api/chat`

```python
class ChatRequest(BaseModel):
    model_code: str
    prompt: str = Field(min_length=1, max_length=4000)
    confirm: bool = False

class ChatResponse(BaseModel):
    answer: str
    charged_credits: int
    balance_after: int
```

При `ConfirmationRequiredError` — HTTP 409 с телом
`{"estimated_credits": N}`; клиент должен повторить запрос с `confirm=true`.
При `InsufficientBalanceError` (из `reserve_credits`) — HTTP 402 с текстом
"Недостаточно кредитов". При `RequestInProgressError` — HTTP 409 (другое
тело: `{"detail": "..."}"`, отличимое от confirmation-409 по наличию поля
`estimated_credits`).

### `GET /api/me`

Упрощается — `MeOut` теряет `tariff_code/tariff_name/subscription_expires_at/limits`,
остаётся:

```python
class MeOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    default_model_code: str | None
    credits_balance: int
    total_credits_purchased: int
    total_credits_spent: int
```

Значение по умолчанию для `default_model_code`, если у пользователя не
установлено — `deepseek_v3` (ТЗ: "если у пользователя нет модели,
использовать DeepSeek V3 или GPT Mini по умолчанию"; берём первый вариант,
т.к. `deepseek_v3` уже sort_order=10, самый дешёвый и первый в списке).

### Удаляются целиком

`GET /api/tariffs`, `GET /api/subscription/me`.

## Явно вне рамок фазы 2

fal.ai / изображения / видео (фаза 3), `/api/buy` и пакеты (фаза 4), админ-
эндпоинты и антифрод/rate-limit/daily-spend-limit (фаза 5), `/admin_stats`
(фаза 6), обновления `frontend-next`.

## Тесты

- `tests/services/ai/test_openrouter_service.py` — `OpenRouterProvider`,
  замоканный HTTP-клиент (`respx` или monkeypatch `AsyncOpenAI` — выбрать по
  месту в плане, ориентируясь на то, как замокан `PiAPIClient` в
  `tests/services/ai/test_piapi_client.py`), успех + `AIError` на не-2xx/таймаут.
- `tests/services/test_text_generation_service.py` — полный
  reserve→settle/refund flow на sqlite-фикстуре (как `test_credit_service.py`):
  успешная генерация, ошибка провайдера → refund, `estimated_credits > 100`
  без `confirm` → `ConfirmationRequiredError`, недостаточный баланс →
  `InsufficientBalanceError`, fallback на другую модель при
  `is_active=False`, fallback дороже без confirm → `ConfirmationRequiredError`.
- `tests/api/test_chat_routes.py` (новый, взамен удалённого фазой 1
  `test_generate_routes.py`) — `/api/chat`, `/api/models`, `/api/me`.
  Никаких **сохранившихся** API-тестов в дереве сейчас нет (единственный
  файл этого рода был удалён в фазе 1 вместе со старым pipeline), но паттерн
  восстановим из истории git: `git show 9d3997b^:tests/api/test_generate_routes.py`
  показывает `httpx.AsyncClient(transport=ASGITransport(app=app))` +
  `app.dependency_overrides[current_user] = _fake_user` — этот же приём
  переиспользуется для новых тестов `/api/chat`/`/api/models`/`/api/me`.
