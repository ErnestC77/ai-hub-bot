# Credit System Phase 5 — Admin + Antifraud Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Последняя нефункциональная фаза credit system v2 — antifraud-гарды (free-tier, daily limit, rate-limit, дедуп) поверх Redis + полный рерайт четырёх сломанных файлов (`admin.py`, `admin_service.py`, `stats_service.py`, `key_healthcheck.py`) под новую схему, чтобы `import app.main` наконец проходил.

**Architecture:** Новый `app/services/antifraud_service.py` — чистые guard-функции поверх `redis_client` и таблицы `settings`; они кидают исключения и ничего не пишут в Postgres. Generation-сервисы фаз 2-3 НЕ переписываются — получают точечные вставки вызовов. Admin API переписывается на `AiModel`/`CreditPackage`/`Setting`/`CreditTransaction`; секции payments/banners переносятся без изменений.

**Tech Stack:** FastAPI + aiogram3 + SQLAlchemy 2 async + Postgres 16 (prod) / aiosqlite (unit-тесты) + Redis 7 (prod) / FakeRedis (тесты) + Alembic + pytest (`asyncio_mode = auto`).

**Design spec (единственный источник истины):** `docs/superpowers/specs/2026-07-10-credit-system-phase5-admin-antifraud-design.md`

## Global Constraints

- Alembic head до фазы: `e6f7a8b9c0d1` (подтверждено: ни одна ревизия не ссылается на неё как `down_revision`). Новая ревизия: `f7a8b9c0d1e2`, `down_revision = 'e6f7a8b9c0d1'`.
- Дефолты антифрод-порогов (= сид): `daily_spend_limit_credits=10000`, `rate_limit_per_user_per_minute=10`, `rate_limit_per_model_per_minute=60`, `duplicate_cooldown_seconds=5`, `free_tier_credit_cap=100`.
- Redis-ключи строго по спеке: `dup:{user_id}:{sha256(model_code+prompt)[:16]}`, `rate_limit:user:{user_id}:{minute_bucket}`, `rate_limit:model:{model_code}:{minute_bucket}`, `daily_spend:{user_id}:{YYYY-MM-DD}` (UTC), `minute_bucket = int(time.time() // 60)`.
- HTTP-маппинг новых исключений (тексты — точные копии из спеки, в спеке была опечатка «лимit» — в коде пишем «лимит»):
  - `DuplicateRequestError` → 429 «Слишком быстрый повтор запроса, подождите пару секунд»
  - `RateLimitExceededError` → 429 «Слишком много запросов, попробуйте через минуту»
  - `TierNotAllowedError` → 403 «Эта модель доступна после первой покупки пакета»
  - `FreeTierLimitExceededError` → 402 «Бесплатный лимит исчерпан, купите пакет кредитов»
  - `DailySpendLimitExceededError` → 429 «Дневной лимит трат исчерпан, попробуйте завтра»
- Конвенция credit_service: каждая пишущая функция начинается с `_lock_user` (SELECT ... FOR UPDATE), делает `flush()` но НЕ `commit()` — транзакцией владеет вызывающий код.
- `text_generation_service.py` / `media_generation_service.py` — ТОЛЬКО точечные вставки, никакого рерайта каркаса фаз 2-3.
- Не трогать: `frontend-next/`, `Banner`-логику, `referral_service.py`, `user_service.py`, banners/payments-секции admin.py (переносятся дословно).
- Тесты запускать из корня репо: `python -m pytest <путь> -v`. Тестовые файлы сами выставляют `BOT_TOKEN`/`DATABASE_URL` через `os.environ.setdefault` до импорта `app.*`.
- Критерий готовности фазы: `python -c "import app.main"` проходит без ошибок (сейчас падает).

## File Structure

| Файл | Действие |
|---|---|
| `app/services/antifraud_service.py` | создать (Task 1) |
| `tests/services/test_antifraud_service.py` | создать (Task 1) |
| `app/services/settings_service.py` | добавить `set_setting` (Task 2) |
| `tests/services/test_settings_service.py` | дополнить (Task 2) |
| `app/services/credit_service.py` | добавить `adjust_credits_admin` (Task 3) |
| `tests/services/test_credit_service.py` | дополнить (Task 3) |
| `app/services/text_generation_service.py` | точечные вставки (Task 4) |
| `tests/services/test_text_generation_service.py` | FakeRedis v2 + новые тесты (Task 4) |
| `app/services/media_generation_service.py` | точечные вставки (Task 5) |
| `tests/services/test_media_generation_service.py` | FakeRedis v2 + новые тесты (Task 5) |
| `tests/api/test_generate_routes.py` | FakeRedis v2 в real_service-фикстуре (Task 5), маппинг-тесты (Task 6) |
| `app/api/routes/chat.py`, `app/api/routes/generate.py` | новые `except`-блоки (Task 6) |
| `tests/api/test_chat_routes.py` | маппинг-тесты (Task 6) |
| `app/services/stats_service.py` | полный рерайт (Task 7) |
| `tests/services/test_stats_service.py` | создать (Task 7) |
| `app/services/keys/key_healthcheck.py` | полный рерайт (Task 8) |
| `tests/services/keys/test_key_healthcheck.py` | создать (Task 8) |
| `app/api/routes/admin.py` | полный рерайт (Task 9) |
| `app/services/admin_service.py` | удалить (Task 9, обоснование в задаче) |
| `tests/api/test_admin.py` | создать (Task 9) |
| `app/db/seed.py`, `alembic/versions/f7a8b9c0d1e2_phase5_antifraud_settings.py`, `tests/db/test_seed_catalog.py` | сиды + миграция (Task 10) |
| — | regression `import app.main` (Task 11) |

---

### Task 1: `antifraud_service.py` — guard-функции, AntifraudSettings, Redis-ключи

**Files:**
- Create: `app/services/antifraud_service.py`
- Test: `tests/services/test_antifraud_service.py`

**Interfaces:**
- Consumes: `app.redis_client.redis_client` (module-level, тесты подменяют `afs.redis_client`), `app.services.settings_service.get_setting(session, key, *, cast, default)`, модели `User` (`total_credits_purchased`, `total_credits_spent`), `AiModel` (`category`, `tier`, `code`), enum'ы `ModelCategory.video`, `ModelTier.ultra`.
- Produces (Tasks 4-6 полагаются на эти ТОЧНЫЕ имена):
  - исключения `DuplicateRequestError`, `RateLimitExceededError`, `TierNotAllowedError`, `FreeTierLimitExceededError`, `DailySpendLimitExceededError`
  - `@dataclass(frozen=True) AntifraudSettings` (5 полей с дефолтами из Global Constraints)
  - `async load_antifraud_settings(session: AsyncSession) -> AntifraudSettings`
  - `async check_duplicate_request(user_id: int, model_code: str, prompt: str, *, settings: AntifraudSettings) -> None`
  - `async check_rate_limits(user_id: int, model_code: str, *, settings: AntifraudSettings) -> None`
  - `async check_tier_allowed(user: User, model: AiModel) -> None`
  - `async check_free_tier_cap(user: User, estimated_credits: int, *, settings: AntifraudSettings) -> None`
  - `async check_daily_spend_limit(user_id: int, estimated_credits: int, *, settings: AntifraudSettings) -> None`
  - `async record_daily_spend(user_id: int, delta: int) -> None`
  - хелперы `_minute_bucket() -> int` и `_daily_spend_key(user_id: int) -> str` (тесты Task 4-5 используют их для сборки ключей и подмены окна)

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/services/test_antifraud_service.py` целиком:

```python
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel, Setting, User
from app.services import antifraud_service as afs
from app.services.antifraud_service import (
    AntifraudSettings,
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
    check_daily_spend_limit,
    check_duplicate_request,
    check_free_tier_cap,
    check_rate_limits,
    check_tier_allowed,
    load_antifraud_settings,
    record_daily_spend,
)


class FakeRedis:
    """In-memory Redis: set(nx)/get/delete/incr/incrby/decrby/expire.

    locked=True отклоняет ТОЛЬКО попытку взять ai_lock:* (эмуляция занятого
    per-user лока) -- antifraud-ключи (dup:*, rate_limit:*, daily_spend:*)
    живут как обычно. Тот же класс копируется в generation-тесты (Tasks 4-5).
    """

    def __init__(self, locked: bool = False):
        self.locked = locked
        self.deleted: list[str] = []
        self.store: dict[str, str] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def set(self, key, value, nx=False, ex=None):
        if key.startswith("ai_lock:") and self.locked:
            return None
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.expire_calls.append((key, ex))
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)

    async def incr(self, key):
        return await self.incrby(key, 1)

    async def incrby(self, key, amount):
        value = int(self.store.get(key, "0")) + int(amount)
        self.store[key] = str(value)
        return value

    async def decrby(self, key, amount):
        return await self.incrby(key, -int(amount))

    async def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))
        return True


DEFAULTS = AntifraudSettings()


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(afs, "redis_client", fake)
    return fake


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _user(*, purchased=0, spent=0) -> User:
    return User(
        telegram_id=1, username="u", credits_balance=1000,
        total_credits_purchased=purchased, total_credits_spent=spent,
    )


def _model(*, category=ModelCategory.text, tier=ModelTier.economy) -> AiModel:
    cost_unit = CostUnit.tokens if category == ModelCategory.text else CostUnit.image
    provider = ModelProvider.openrouter if category == ModelCategory.text else ModelProvider.fal
    return AiModel(
        provider=provider, category=category, code="m", display_name="m",
        provider_model_id="x/m", tier=tier, cost_unit=cost_unit,
        min_credits=0, recommended_credits=1,
    )


# --- AntifraudSettings / load_antifraud_settings ---

def test_defaults_match_phase5_seed():
    assert DEFAULTS == AntifraudSettings(
        daily_spend_limit_credits=10_000,
        rate_limit_per_user_per_minute=10,
        rate_limit_per_model_per_minute=60,
        duplicate_cooldown_seconds=5,
        free_tier_credit_cap=100,
    )


async def test_load_antifraud_settings_empty_db_uses_defaults(session):
    assert await load_antifraud_settings(session) == DEFAULTS


async def test_load_antifraud_settings_reads_overrides(session):
    session.add(Setting(key="daily_spend_limit_credits", value="5000", type="int"))
    session.add(Setting(key="free_tier_credit_cap", value="250", type="int"))
    await session.commit()

    loaded = await load_antifraud_settings(session)
    assert loaded.daily_spend_limit_credits == 5000
    assert loaded.free_tier_credit_cap == 250
    assert loaded.rate_limit_per_user_per_minute == 10  # остальные -- дефолты


# --- check_duplicate_request ---

async def test_duplicate_first_request_passes_and_sets_cooldown_key(fake_redis):
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)

    [key] = list(fake_redis.store)
    assert key.startswith("dup:1:")
    assert len(key.split(":")[2]) == 16  # sha256(model_code+prompt)[:16]
    assert fake_redis.expire_calls == [(key, 5)]  # TTL = duplicate_cooldown_seconds


async def test_duplicate_repeat_within_cooldown_raises(fake_redis):
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)
    with pytest.raises(DuplicateRequestError):
        await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)


async def test_duplicate_different_prompt_or_user_passes(fake_redis):
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)
    await check_duplicate_request(1, "deepseek_v3", "другой prompt", settings=DEFAULTS)
    await check_duplicate_request(2, "deepseek_v3", "привет", settings=DEFAULTS)  # другой user


async def test_duplicate_passes_again_after_ttl_expiry(fake_redis):
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)
    fake_redis.store.clear()  # эмуляция истечения TTL (FakeRedis не тикает время)
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)


# --- check_rate_limits ---

async def test_rate_limit_user_allows_up_to_limit_then_raises(fake_redis, monkeypatch):
    monkeypatch.setattr(afs, "_minute_bucket", lambda: 100)
    for _ in range(10):  # ровно лимит -- проходит
        await check_rate_limits(1, "deepseek_v3", settings=DEFAULTS)
    with pytest.raises(RateLimitExceededError):
        await check_rate_limits(1, "deepseek_v3", settings=DEFAULTS)
    # EXPIRE ставился только при первом инкременте каждого ключа
    assert fake_redis.expire_calls == [
        ("rate_limit:user:1:100", 60),
        ("rate_limit:model:deepseek_v3:100", 60),
    ]


async def test_rate_limit_model_is_global_across_users(fake_redis, monkeypatch):
    monkeypatch.setattr(afs, "_minute_bucket", lambda: 100)
    settings = AntifraudSettings(rate_limit_per_model_per_minute=2)
    await check_rate_limits(1, "veo_video", settings=settings)
    await check_rate_limits(2, "veo_video", settings=settings)
    with pytest.raises(RateLimitExceededError):
        await check_rate_limits(3, "veo_video", settings=settings)


async def test_rate_limit_resets_in_next_minute_bucket(fake_redis, monkeypatch):
    monkeypatch.setattr(afs, "_minute_bucket", lambda: 100)
    settings = AntifraudSettings(rate_limit_per_user_per_minute=1)
    await check_rate_limits(1, "deepseek_v3", settings=settings)
    with pytest.raises(RateLimitExceededError):
        await check_rate_limits(1, "deepseek_v3", settings=settings)

    monkeypatch.setattr(afs, "_minute_bucket", lambda: 101)  # новое окно
    await check_rate_limits(1, "deepseek_v3", settings=settings)


# --- check_tier_allowed ---

async def test_tier_blocks_video_and_ultra_for_non_payers():
    with pytest.raises(TierNotAllowedError):
        await check_tier_allowed(_user(purchased=0), _model(category=ModelCategory.video))
    with pytest.raises(TierNotAllowedError):
        await check_tier_allowed(_user(purchased=0), _model(tier=ModelTier.ultra))


async def test_tier_allows_everything_else(fake_redis):
    await check_tier_allowed(_user(purchased=0), _model())  # text economy
    await check_tier_allowed(_user(purchased=0), _model(category=ModelCategory.image))
    await check_tier_allowed(_user(purchased=1), _model(category=ModelCategory.video))
    await check_tier_allowed(_user(purchased=1), _model(tier=ModelTier.ultra))


# --- check_free_tier_cap ---

async def test_free_tier_cap_allows_exactly_at_cap():
    await check_free_tier_cap(_user(purchased=0, spent=95), 5, settings=DEFAULTS)  # 100 == cap


async def test_free_tier_cap_blocks_over_cap():
    with pytest.raises(FreeTierLimitExceededError):
        await check_free_tier_cap(_user(purchased=0, spent=95), 6, settings=DEFAULTS)


async def test_free_tier_cap_ignored_after_first_purchase():
    await check_free_tier_cap(_user(purchased=1, spent=100_000), 100_000, settings=DEFAULTS)


# --- check_daily_spend_limit / record_daily_spend ---

async def test_daily_limit_allows_exactly_at_limit(fake_redis):
    await check_daily_spend_limit(1, 10_000, settings=DEFAULTS)  # 0 + 10000 == limit


async def test_daily_limit_blocks_over_limit_using_current_counter(fake_redis):
    fake_redis.store[afs._daily_spend_key(1)] = "9995"
    with pytest.raises(DailySpendLimitExceededError):
        await check_daily_spend_limit(1, 6, settings=DEFAULTS)
    await check_daily_spend_limit(1, 5, settings=DEFAULTS)  # 9995 + 5 == limit


async def test_check_daily_limit_is_read_only(fake_redis):
    await check_daily_spend_limit(1, 100, settings=DEFAULTS)
    assert fake_redis.store == {}  # GET без записи: запись -- только record_daily_spend


async def test_record_daily_spend_increments_and_sets_ttl_once(fake_redis):
    key = afs._daily_spend_key(1)
    await record_daily_spend(1, 100)
    assert fake_redis.store[key] == "100"
    assert fake_redis.expire_calls == [(key, afs.DAILY_SPEND_TTL_SECONDS)]

    await record_daily_spend(1, 50)  # ключ уже существует -- второго EXPIRE нет
    assert fake_redis.store[key] == "150"
    assert len(fake_redis.expire_calls) == 1


async def test_record_daily_spend_negative_delta_decrements(fake_redis):
    key = afs._daily_spend_key(1)
    await record_daily_spend(1, 100)
    await record_daily_spend(1, -40)
    assert fake_redis.store[key] == "60"


async def test_record_daily_spend_zero_delta_is_noop(fake_redis):
    await record_daily_spend(1, 0)
    assert fake_redis.store == {}
    assert fake_redis.expire_calls == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/services/test_antifraud_service.py -v`
Expected: FAIL на импорте — `ModuleNotFoundError: No module named 'app.services.antifraud_service'`.

- [ ] **Step 3: Написать реализацию**

Создать `app/services/antifraud_service.py` целиком:

```python
"""Antifraud-гарды фазы 5: free-tier гейтинг, дневной лимит трат, rate-limit,
защита от дублей. Чистые guard-функции поверх Redis + таблицы settings: каждая
кидает своё исключение при нарушении и НИЧЕГО не пишет в Postgres. Пороги
редактируются админкой (settings), дефолты = сид фазы 5.
"""

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelCategory, ModelTier
from app.db.models import AiModel, User
from app.redis_client import redis_client
from app.services.settings_service import get_setting

DAILY_SPEND_TTL_SECONDS = 25 * 60 * 60  # 25ч -- страховка поверх UTC-дня (спека)


class DuplicateRequestError(Exception):
    """Повтор идентичного (model_code, prompt) в окне duplicate_cooldown_seconds."""


class RateLimitExceededError(Exception):
    """Превышен per-minute лимит запросов (user или model)."""


class TierNotAllowedError(Exception):
    """video/ultra модели закрыты до первой покупки пакета."""


class FreeTierLimitExceededError(Exception):
    """Кумулятивный лимит бесплатных кредитов исчерпан."""


class DailySpendLimitExceededError(Exception):
    """Дневной лимит трат исчерпан."""


@dataclass(frozen=True)
class AntifraudSettings:
    """Снимок антифрод-порогов из таблицы settings. Дефолты = сид фазы 5
    (защита от пустой БД до первого сида, как у PricingSettings)."""

    daily_spend_limit_credits: int = 10_000
    rate_limit_per_user_per_minute: int = 10
    rate_limit_per_model_per_minute: int = 60
    duplicate_cooldown_seconds: int = 5
    free_tier_credit_cap: int = 100


async def load_antifraud_settings(session: AsyncSession) -> AntifraudSettings:
    defaults = AntifraudSettings()
    return AntifraudSettings(
        daily_spend_limit_credits=await get_setting(
            session, "daily_spend_limit_credits", cast=int,
            default=defaults.daily_spend_limit_credits,
        ),
        rate_limit_per_user_per_minute=await get_setting(
            session, "rate_limit_per_user_per_minute", cast=int,
            default=defaults.rate_limit_per_user_per_minute,
        ),
        rate_limit_per_model_per_minute=await get_setting(
            session, "rate_limit_per_model_per_minute", cast=int,
            default=defaults.rate_limit_per_model_per_minute,
        ),
        duplicate_cooldown_seconds=await get_setting(
            session, "duplicate_cooldown_seconds", cast=int,
            default=defaults.duplicate_cooldown_seconds,
        ),
        free_tier_credit_cap=await get_setting(
            session, "free_tier_credit_cap", cast=int,
            default=defaults.free_tier_credit_cap,
        ),
    )


def _minute_bucket() -> int:
    # Фиксированные 60-секундные окна (не скользящее окно): проще и достаточно
    # для защиты от убытков, не для точного throttling API (спека фазы 5).
    return int(time.time() // 60)


def _daily_spend_key(user_id: int) -> str:
    return f"daily_spend:{user_id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"


async def check_duplicate_request(
    user_id: int, model_code: str, prompt: str, *, settings: AntifraudSettings
) -> None:
    digest = hashlib.sha256((model_code + prompt).encode("utf-8")).hexdigest()[:16]
    key = f"dup:{user_id}:{digest}"
    # SET NX EX: проверка и захват cooldown-окна -- одна атомарная операция.
    acquired = await redis_client.set(key, "1", nx=True, ex=settings.duplicate_cooldown_seconds)
    if not acquired:
        raise DuplicateRequestError(
            f"duplicate request {key} within {settings.duplicate_cooldown_seconds}s"
        )


async def _check_one_rate_limit(key: str, limit: int, what: str) -> None:
    # Check и increment -- одна операция (INCR), отдельного "record" нет (спека).
    count = await redis_client.incr(key)
    if count == 1:
        # Первый запрос создал ключ -- ставим TTL, чтобы окно очистилось само.
        await redis_client.expire(key, 60)
    if count > limit:
        raise RateLimitExceededError(f"{what}: {count} > {limit}/min")


async def check_rate_limits(
    user_id: int, model_code: str, *, settings: AntifraudSettings
) -> None:
    bucket = _minute_bucket()
    await _check_one_rate_limit(
        f"rate_limit:user:{user_id}:{bucket}",
        settings.rate_limit_per_user_per_minute,
        f"user {user_id}",
    )
    await _check_one_rate_limit(
        f"rate_limit:model:{model_code}:{bucket}",
        settings.rate_limit_per_model_per_minute,
        f"model {model_code}",
    )


async def check_tier_allowed(user: User, model: AiModel) -> None:
    if user.total_credits_purchased > 0:
        return
    if model.category == ModelCategory.video or model.tier == ModelTier.ultra:
        raise TierNotAllowedError(
            f"model {model.code} requires a purchase "
            f"(category={model.category.value}, tier={model.tier.value})"
        )


async def check_free_tier_cap(
    user: User, estimated_credits: int, *, settings: AntifraudSettings
) -> None:
    # Раз пользователь ничего не покупал, весь его total_credits_spent -- это
    # трата free-кредитов (спека фазы 5): новых колонок не требуется.
    if user.total_credits_purchased > 0:
        return
    if user.total_credits_spent + estimated_credits > settings.free_tier_credit_cap:
        raise FreeTierLimitExceededError(
            f"free tier cap: {user.total_credits_spent} + {estimated_credits} "
            f"> {settings.free_tier_credit_cap}"
        )


async def check_daily_spend_limit(
    user_id: int, estimated_credits: int, *, settings: AntifraudSettings
) -> None:
    # Только чтение (GET): запись делает record_daily_spend ПОСЛЕ успешного
    # reserve_credits -- между проверкой и резервом стоит confirmation-gate,
    # который может прервать поток без записи (спека фазы 5).
    raw = await redis_client.get(_daily_spend_key(user_id))
    current = int(raw) if raw is not None else 0
    if current + estimated_credits > settings.daily_spend_limit_credits:
        raise DailySpendLimitExceededError(
            f"daily spend: {current} + {estimated_credits} "
            f"> {settings.daily_spend_limit_credits}"
        )


async def record_daily_spend(user_id: int, delta: int) -> None:
    """Инкремент/декремент дневного счётчика трат. Вызывается ПОСЛЕ успешного
    reserve_credits (delta=+estimated) и на ветках release/refund (delta<0)."""
    if delta == 0:
        return
    key = _daily_spend_key(user_id)
    if delta > 0:
        new_value = await redis_client.incrby(key, delta)
        if new_value == delta:  # ключ только что создан -- страховочный TTL
            await redis_client.expire(key, DAILY_SPEND_TTL_SECONDS)
    else:
        await redis_client.decrby(key, -delta)
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/services/test_antifraud_service.py -v`
Expected: PASS (все тесты).

- [ ] **Step 5: Commit**

```bash
git add app/services/antifraud_service.py tests/services/test_antifraud_service.py
git commit -m "feat(antifraud): guard-функции antifraud_service + AntifraudSettings"
```

---

### Task 2: `settings_service.set_setting` — единственное место записи в settings

**Files:**
- Modify: `app/services/settings_service.py`
- Test: `tests/services/test_settings_service.py`

**Interfaces:**
- Consumes: модель `Setting` (`key`, `value`, `type`, `description`).
- Produces: `async set_setting(session: AsyncSession, key: str, value: str, *, type_: str, description: str | None = None) -> Setting` — upsert; при обновлении существующего ключа меняется ТОЛЬКО `value` (`type`/`description` сохраняются). Делает `flush()`, НЕ `commit()`. Используется в Task 9 (`PATCH /admin/settings/{key}`).

- [ ] **Step 1: Написать падающие тесты**

В конец `tests/services/test_settings_service.py` добавить (и расширить строку импорта):

```python
# заменить строку
#   from app.services.settings_service import get_setting, load_pricing_settings
# на:
from app.services.settings_service import get_setting, load_pricing_settings, set_setting
```

```python
# --- set_setting ---

async def test_set_setting_creates_new_row(session):
    row = await set_setting(
        session, "daily_spend_limit_credits", "10000",
        type_="int", description="Дневной лимит трат на пользователя",
    )
    await session.commit()

    assert row.key == "daily_spend_limit_credits"
    assert row.value == "10000"
    assert row.type == "int"
    assert row.description == "Дневной лимит трат на пользователя"
    assert await get_setting(session, "daily_spend_limit_credits", cast=int) == 10000


async def test_set_setting_updates_value_only(session):
    session.add(Setting(key="free_tier_credit_cap", value="100", type="int",
                        description="исходное описание"))
    await session.commit()

    row = await set_setting(
        session, "free_tier_credit_cap", "250", type_="str", description="другое"
    )
    await session.commit()

    assert row.value == "250"
    assert row.type == "int"                       # тип НЕ меняется при обновлении
    assert row.description == "исходное описание"  # описание НЕ меняется
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/services/test_settings_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'set_setting'`.

- [ ] **Step 3: Написать реализацию**

В конец `app/services/settings_service.py` добавить:

```python
async def set_setting(
    session: AsyncSession,
    key: str,
    value: str,
    *,
    type_: str,
    description: str | None = None,
) -> Setting:
    """Upsert строки settings. Единственное место записи в таблицу settings.
    При обновлении существующего ключа меняется только value -- type/description
    заданы сидом и при правке значения не трогаются (спека фазы 5).
    flush, не commit -- транзакцией владеет вызывающий код."""
    row = await session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value, type=type_, description=description)
        session.add(row)
    else:
        row.value = value
    await session.flush()
    return row
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/services/test_settings_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/settings_service.py tests/services/test_settings_service.py
git commit -m "feat(settings): set_setting -- upsert строки settings"
```

---

### Task 3: `credit_service.adjust_credits_admin`

**Files:**
- Modify: `app/services/credit_service.py` (добавить функцию в конец файла)
- Test: `tests/services/test_credit_service.py`

**Interfaces:**
- Consumes: существующие `_lock_user(session, user_id)`, `InsufficientBalanceError(balance, required)`, `CreditTxType.admin_adjustment`.
- Produces: `async adjust_credits_admin(session: AsyncSession, user_id: int, delta: int, *, reason: str) -> CreditTransaction` — используется в Task 9 (`POST /admin/users/{telegram_id}/credits`). `flush()`, не `commit()`.

- [ ] **Step 1: Написать падающие тесты**

В `tests/services/test_credit_service.py` расширить импорт:

```python
# заменить блок импорта из credit_service на:
from app.services.credit_service import (
    InsufficientBalanceError,
    adjust_credits_admin,
    grant_credits,
    refund_request,
    reserve_credits,
    settle_request,
)
```

В конец файла (перед секцией «Конкурентный reserve») добавить:

```python
# --- adjust_credits_admin ---

async def test_adjust_admin_positive_delta_credits_balance(session):
    user = await _make_user(session, balance=10)

    tx = await adjust_credits_admin(session, user.id, 40, reason="компенсация сбоя")
    await session.commit()

    assert tx.type == CreditTxType.admin_adjustment
    assert tx.amount == 40
    assert tx.balance_before == 10
    assert tx.balance_after == 50
    assert tx.description == "компенсация сбоя"
    assert user.credits_balance == 50
    assert user.total_credits_purchased == 0  # внебалансовая корректировка
    assert user.total_credits_spent == 0


async def test_adjust_admin_negative_delta_debits_balance(session):
    user = await _make_user(session, balance=100)

    tx = await adjust_credits_admin(session, user.id, -30, reason="списание за абьюз")
    await session.commit()

    assert tx.type == CreditTxType.admin_adjustment
    assert tx.amount == -30
    assert tx.balance_before == 100
    assert tx.balance_after == 70
    assert user.credits_balance == 70
    assert user.total_credits_purchased == 0
    assert user.total_credits_spent == 0


async def test_adjust_admin_cannot_take_balance_below_zero(session):
    user = await _make_user(session, balance=20)
    await session.commit()
    user_id = user.id  # захват ДО rollback (см. комментарий к test_reserve_insufficient...)

    with pytest.raises(InsufficientBalanceError) as exc_info:
        await adjust_credits_admin(session, user_id, -21, reason="слишком много")

    assert exc_info.value.balance == 20
    assert exc_info.value.required == 21
    await session.rollback()
    fetched = await session.get(User, user_id)
    assert fetched.credits_balance == 20
    assert await _tx_count(session) == 0


async def test_adjust_admin_rejects_zero_delta(session):
    user = await _make_user(session, balance=0)
    with pytest.raises(ValueError):
        await adjust_credits_admin(session, user.id, 0, reason="ноль")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/services/test_credit_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'adjust_credits_admin'`.

- [ ] **Step 3: Написать реализацию**

В конец `app/services/credit_service.py` добавить:

```python
async def adjust_credits_admin(
    session: AsyncSession, user_id: int, delta: int, *, reason: str
) -> CreditTransaction:
    """Ручная корректировка баланса админом: delta может быть отрицательной
    (списание) или положительной (начисление). В отличие от grant_credits/
    refund_request НЕ трогает total_credits_purchased/total_credits_spent --
    это внебалансовая корректировка, а не покупка или трата по запросу.
    Списание ниже нуля запрещено (InsufficientBalanceError), начисление
    ограничений не имеет."""
    if delta == 0:
        raise ValueError("adjust delta must be non-zero")

    user = await _lock_user(session, user_id)
    if delta < 0 and user.credits_balance + delta < 0:
        raise InsufficientBalanceError(balance=user.credits_balance, required=-delta)

    balance_before = user.credits_balance
    user.credits_balance = balance_before + delta
    tx = CreditTransaction(
        user_id=user_id,
        type=CreditTxType.admin_adjustment,
        amount=delta,
        balance_before=balance_before,
        balance_after=user.credits_balance,
        description=reason,
    )
    session.add(tx)
    await session.flush()
    return tx
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/services/test_credit_service.py -v`
Expected: PASS (Postgres-тест skipped без `TEST_DATABASE_URL` — это норма).

- [ ] **Step 5: Commit**

```bash
git add app/services/credit_service.py tests/services/test_credit_service.py
git commit -m "feat(credits): adjust_credits_admin -- админ-корректировка баланса"
```

---

### Task 4: Antifraud-вставки в `text_generation_service.py` + FakeRedis v2

**Files:**
- Modify: `app/services/text_generation_service.py`
- Modify: `tests/services/test_text_generation_service.py`

**Interfaces:**
- Consumes (из Task 1, точные имена): `load_antifraud_settings`, `check_duplicate_request`, `check_rate_limits`, `check_tier_allowed`, `check_free_tier_cap`, `check_daily_spend_limit`, `record_daily_spend`, `afs._minute_bucket`, `afs._daily_spend_key`.
- Produces: `generate_text` теперь может кидать 5 antifraud-исключений (маппинг в роуте — Task 6). Публичная сигнатура `generate_text(session, user, model_code, prompt, *, confirm=False)` НЕ меняется.

Порядок вставок (спека): (1) до `ai_lock` — duplicate → rate → tier; (2) после `estimated`, до confirmation-gate — free-tier cap → daily limit; (3) после успешного commit резерва — `record_daily_spend(+estimated)`; (4) на ветках release/refund — компенсирующий декремент.

Решение по confirm-повтору (закрывает конфликт спеки с UX): `check_duplicate_request` вызывается только при `confirm=False`. Повтор с `confirm=True` — это осознанное подтверждение после 409 `ConfirmationRequired`, приходящее внутри 5-секундного cooldown-окна; блокировать его дедупом нельзя. Rate-limit при этом всё равно считает обе попытки.

- [ ] **Step 1: Обновить FakeRedis и хелперы тестов (существующие тесты должны остаться зелёными)**

В `tests/services/test_text_generation_service.py`:

1. Заменить класс `FakeRedis` (строки 34-43) целиком на расширенную версию из Task 1 Step 1 (класс `FakeRedis` со `store`/`expire_calls`/`get`/`incr`/`incrby`/`decrby`/`expire`; `locked=True` отклоняет только `ai_lock:*`). Скопировать код класса дословно.

2. Добавить импорты (после строки `from app.services import text_generation_service as tgs`):

```python
from app.services import antifraud_service as afs
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
```

3. Заменить autouse-фикстуру `fake_redis`:

```python
@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(tgs, "redis_client", fake)
    monkeypatch.setattr(afs, "redis_client", fake)
    return fake
```

4. Заменить `_seed` (добавить `purchased`/`spent`):

```python
async def _seed(session, *models, balance=100, purchased=0, spent=0) -> User:
    user = User(
        telegram_id=1, username="u", credits_balance=balance,
        total_credits_purchased=purchased, total_credits_spent=spent,
    )
    session.add(user)
    for m in models:
        session.add(m)
    await session.commit()
    return user
```

5. Три существующих теста конфликтуют с новыми гардами (ultra-tier и estimate > cap для непокупавшего) — дать пользователю покупку:

```python
# test_tier_max_caps_output_tokens: заменить строку
#   user = await _seed(session, _model(code="big", tier=ModelTier.ultra))
# на:
    user = await _seed(session, _model(code="big", tier=ModelTier.ultra), purchased=1)

# test_expensive_estimate_without_confirm_raises: заменить строку
#   user = await _seed(session, _model(code="exp", price=20, min_credits=20, recommended=30), balance=500)
# на:
    user = await _seed(
        session, _model(code="exp", price=20, min_credits=20, recommended=30),
        balance=500, purchased=1,
    )

# test_expensive_estimate_with_confirm_proceeds: заменить строку
#   user = await _seed(session, _model(code="exp", price=20, min_credits=20, recommended=30), balance=500)
# на:
    user = await _seed(
        session, _model(code="exp", price=20, min_credits=20, recommended=30),
        balance=500, purchased=1,
    )
```

Run: `python -m pytest tests/services/test_text_generation_service.py -v`
Expected: PASS (сервис ещё не трогали; обновлённая инфраструктура обратно-совместима).

- [ ] **Step 2: Написать новые падающие тесты**

В конец `tests/services/test_text_generation_service.py` добавить:

```python
# --- antifraud (фаза 5) ---

async def test_duplicate_prompt_within_cooldown_is_rejected(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(tgs, "_provider", provider)

    await generate_text(session, user, "cheap", "привет")
    with pytest.raises(DuplicateRequestError):
        await generate_text(session, user, "cheap", "привет")

    assert len(provider.calls) == 1               # до провайдера дошёл только первый
    assert len(await _request_rows(session)) == 1  # второй ничего не создал


async def test_confirm_retry_is_not_blocked_by_dedup(session, monkeypatch):
    # Повтор с confirm=True после 409 ConfirmationRequired приходит внутри
    # cooldown-окна и НЕ должен блокироваться дедупом.
    user = await _seed(
        session, _model(code="exp", price=20, min_credits=20, recommended=30),
        balance=500, purchased=1,
    )
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    with pytest.raises(ConfirmationRequiredError):
        await generate_text(session, user, "exp", "hi")

    result = await generate_text(session, user, "exp", "hi", confirm=True)
    assert result.charged_credits == 33


async def test_user_rate_limit_rejects_over_limit(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    bucket = afs._minute_bucket()
    fake_redis.store[f"rate_limit:user:{user.id}:{bucket}"] = "10"  # лимит уже выбран

    with pytest.raises(RateLimitExceededError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []
    assert await _tx_types(session) == []


async def test_model_rate_limit_rejects_over_limit(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    bucket = afs._minute_bucket()
    fake_redis.store[f"rate_limit:model:cheap:{bucket}"] = "60"

    with pytest.raises(RateLimitExceededError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []


async def test_ultra_model_blocked_until_first_purchase(session, fake_redis, monkeypatch):
    user = await _seed(session, _model(code="big", tier=ModelTier.ultra))  # purchased=0
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(tgs, "_provider", provider)

    with pytest.raises(TierNotAllowedError):
        await generate_text(session, user, "big", "hi")

    assert provider.calls == []
    assert await _request_rows(session) == []
    assert fake_redis.deleted == []  # отказ ДО взятия лока


async def test_free_tier_cap_blocks_when_estimate_exceeds_remaining(session, fake_redis, monkeypatch):
    # cap=100, spent=95, оценка cheap-модели = 7 -> 95 + 7 > 100.
    user = await _seed(session, _model(), purchased=0, spent=95)
    monkeypatch.setattr(tgs, "_provider", FakeProvider())

    with pytest.raises(FreeTierLimitExceededError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []
    assert await _tx_types(session) == []
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок был взят и снят в finally


async def test_daily_spend_limit_blocks_request(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    fake_redis.store[afs._daily_spend_key(user.id)] = "9998"  # 9998 + 7 > 10000

    with pytest.raises(DailySpendLimitExceededError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "9998"  # счётчик не тронут


async def test_success_records_daily_spend_adjusted_to_charged(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())  # оценка 7, факт 3
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "cheap", "привет")

    assert result.charged_credits == 3
    # +7 после reserve, затем -4 после settle (release) -> итог = фактическое списание
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "3"


async def test_provider_error_decrements_daily_spend_fully(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider(error=AIError("boom")))

    with pytest.raises(AIError):
        await generate_text(session, user, "cheap", "привет")

    # +7 после reserve, -7 после refund
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "0"
```

- [ ] **Step 3: Убедиться, что новые тесты падают**

Run: `python -m pytest tests/services/test_text_generation_service.py -v -k "duplicate or rate_limit or ultra or free_tier or daily"`
Expected: FAIL — исключения не кидаются (`DID NOT RAISE`) и/или счётчики не пишутся (`KeyError` по daily-ключу).

- [ ] **Step 4: Вставить antifraud-вызовы в сервис**

В `app/services/text_generation_service.py`:

1. Добавить импорт после блока `from app.services.credit_service import (...)` (строки 19-24):

```python
from app.services.antifraud_service import (
    check_daily_spend_limit,
    check_duplicate_request,
    check_free_tier_cap,
    check_rate_limits,
    check_tier_allowed,
    load_antifraud_settings,
    record_daily_spend,
)
```

2. Вставка pre-checks до лока — в `generate_text` (сейчас строки 107-109), заменить:

```python
    model, requested = await _resolve_model(session, model_code)

    lock_key = f"ai_lock:{user.id}"
```

на:

```python
    model, requested = await _resolve_model(session, model_code)

    # Antifraud pre-checks (фаза 5) -- быстрый и дешёвый отказ ДО взятия лока.
    af_settings = await load_antifraud_settings(session)
    if not confirm:
        # confirm=True -- осознанный повтор после 409 ConfirmationRequired:
        # он приходит внутри cooldown-окна и не должен блокироваться дедупом.
        await check_duplicate_request(user.id, model_code, prompt, settings=af_settings)
    await check_rate_limits(user.id, model.code, settings=af_settings)
    await check_tier_allowed(user, model)

    lock_key = f"ai_lock:{user.id}"
```

3. Вставка cap/daily после оценки, до confirmation-gate (сейчас строки 115-121), заменить:

```python
        pricing = await load_pricing_settings(session)
        estimated = calculate_text_credits(
            model, ESTIMATE_INPUT_TOKENS, ESTIMATE_OUTPUT_TOKENS, settings=pricing
        )

        fallback_used = model is not requested
```

на:

```python
        pricing = await load_pricing_settings(session)
        estimated = calculate_text_credits(
            model, ESTIMATE_INPUT_TOKENS, ESTIMATE_OUTPUT_TOKENS, settings=pricing
        )

        # Antifraud (фаза 5): free-tier cap и дневной лимит -- после оценки,
        # ДО confirmation-gate (запись в daily-счётчик будет после reserve).
        await check_free_tier_cap(user, estimated, settings=af_settings)
        await check_daily_spend_limit(user.id, estimated, settings=af_settings)

        fallback_used = model is not requested
```

4. Запись daily-счётчика после commit резерва (сейчас строки 154-155), заменить:

```python
        request.status = RequestStatus.reserved
        await session.commit()  # резерв фиксируется ДО долгого внешнего вызова
```

на:

```python
        request.status = RequestStatus.reserved
        await session.commit()  # резерв фиксируется ДО долгого внешнего вызова
        await record_daily_spend(user.id, estimated)
```

5. Декремент на refund-ветке (сейчас строки 165-169), заменить:

```python
        except Exception as exc:
            request.error_message = str(exc)
            await refund_request(session, request, reason=f"provider error: {exc}")
            await session.commit()
            raise
```

на:

```python
        except Exception as exc:
            request.error_message = str(exc)
            await refund_request(session, request, reason=f"provider error: {exc}")
            await session.commit()
            await record_daily_spend(user.id, -estimated)
            raise
```

6. Выравнивание после settle (release/доплата), сейчас строки 171-172, заменить:

```python
        charged = request.charged_credits
        balance_after = user.credits_balance
```

на:

```python
        if request.charged_credits != estimated:
            # settle скорректировал списание (release или доплата) --
            # выравниваем дневной счётчик на разницу.
            await record_daily_spend(user.id, request.charged_credits - estimated)

        charged = request.charged_credits
        balance_after = user.credits_balance
```

- [ ] **Step 5: Убедиться, что весь файл тестов проходит**

Run: `python -m pytest tests/services/test_text_generation_service.py -v`
Expected: PASS (все старые + все новые).

- [ ] **Step 6: Commit**

```bash
git add app/services/text_generation_service.py tests/services/test_text_generation_service.py
git commit -m "feat(antifraud): интеграция guard'ов в текстовый flow"
```

---

### Task 5: Antifraud-вставки в `media_generation_service.py` + FakeRedis v2

**Files:**
- Modify: `app/services/media_generation_service.py`
- Modify: `tests/services/test_media_generation_service.py`
- Modify: `tests/api/test_generate_routes.py` (только FakeRedis + фикстура `real_service`)

**Interfaces:**
- Consumes: те же имена из Task 1, что и Task 4.
- Produces: `start_media_generation` может кидать 5 antifraud-исключений (маппинг — Task 6). Сигнатуры `start_media_generation` / `handle_fal_webhook` / `refund_stale_reserved_requests` НЕ меняются.

- [ ] **Step 1: Обновить тестовую инфраструктуру (существующие тесты остаются зелёными)**

В `tests/services/test_media_generation_service.py`:

1. Заменить класс `FakeRedis` (строки 36-47) на расширенную версию из Task 1 Step 1 (дословно тот же класс).

2. Добавить импорты (после `from app.services import media_generation_service as mgs`):

```python
from app.services import antifraud_service as afs
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
```

3. Заменить autouse-фикстуру `fake_redis`:

```python
@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(mgs, "redis_client", fake)
    monkeypatch.setattr(afs, "redis_client", fake)
    return fake
```

4. Заменить `_seed` — дефолт `purchased=1`, чтобы существующие video/дорогие-image тесты (которые проверяют НЕ антифрод) не упирались в tier-гейт и free-tier cap; антифрод-тесты передают `purchased=0` явно:

```python
async def _seed(session, *models, balance=1000, purchased=1, spent=0) -> User:
    user = User(
        telegram_id=1, username="u", credits_balance=balance,
        total_credits_purchased=purchased, total_credits_spent=spent,
    )
    session.add(user)
    for m in models:
        session.add(m)
    await session.commit()
    return user
```

В `tests/api/test_generate_routes.py`:

5. Заменить класс `FakeRedis` (строки 51-60) на ту же расширенную версию.

6. Добавить импорт `from app.services import antifraud_service as afs` (после строки `from app.services import media_generation_service as mgs`).

7. В фикстуре `real_service` заменить строку `monkeypatch.setattr(mgs, "redis_client", FakeRedis())` на общий инстанс для обоих модулей:

```python
    fake_redis = FakeRedis()
    monkeypatch.setattr(mgs, "redis_client", fake_redis)
    monkeypatch.setattr(afs, "redis_client", fake_redis)
```

Run: `python -m pytest tests/services/test_media_generation_service.py tests/api/test_generate_routes.py -v`
Expected: PASS (сервис ещё не изменён).

- [ ] **Step 2: Написать новые падающие тесты**

В конец `tests/services/test_media_generation_service.py` добавить:

```python
# --- antifraud (фаза 5) ---

async def test_duplicate_media_prompt_within_cooldown_is_rejected(session, fal):
    user = await _seed(session, _image_model())

    await start_media_generation(session, user, "img", "a bear")
    with pytest.raises(DuplicateRequestError):
        await start_media_generation(session, user, "img", "a bear")

    assert len(fal.image_calls) == 1
    assert len(await _request_rows(session)) == 1


async def test_media_user_rate_limit_rejects_over_limit(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    bucket = afs._minute_bucket()
    fake_redis.store[f"rate_limit:user:{user.id}:{bucket}"] = "10"

    with pytest.raises(RateLimitExceededError):
        await start_media_generation(session, user, "img", "a bear")

    assert fal.image_calls == []
    assert await _request_rows(session) == []


async def test_video_blocked_until_first_purchase(session, fake_redis, fal):
    user = await _seed(session, _video_model(), purchased=0)

    with pytest.raises(TierNotAllowedError):
        await start_media_generation(session, user, "vid", "a bear runs")

    assert fal.video_calls == []
    assert await _request_rows(session) == []
    assert fake_redis.deleted == []  # отказ ДО взятия лока


async def test_free_tier_cap_blocks_media_over_cap(session, fal):
    # cap=100, spent=50, оценка image = 100 -> 50 + 100 > 100.
    user = await _seed(session, _image_model(), purchased=0, spent=50)

    with pytest.raises(FreeTierLimitExceededError):
        await start_media_generation(session, user, "img", "a bear")

    assert await _request_rows(session) == []


async def test_daily_spend_limit_blocks_media(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    fake_redis.store[afs._daily_spend_key(user.id)] = "9950"  # 9950 + 100 > 10000

    with pytest.raises(DailySpendLimitExceededError):
        await start_media_generation(session, user, "img", "a bear")

    assert await _request_rows(session) == []
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "9950"


async def test_start_records_daily_spend(session, fake_redis, fal):
    user = await _seed(session, _image_model())

    await start_media_generation(session, user, "img", "a bear")

    assert fake_redis.store[afs._daily_spend_key(user.id)] == "100"


async def test_submit_failure_decrements_daily_spend(session, fake_redis, monkeypatch):
    user = await _seed(session, _image_model())
    monkeypatch.setattr(mgs, "FalClient", FakeFalClient(error=RuntimeError("fal down")))

    with pytest.raises(AIError):
        await start_media_generation(session, user, "img", "a bear")

    assert fake_redis.store[afs._daily_spend_key(user.id)] == "0"


async def test_webhook_error_decrements_daily_spend(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "100"

    await handle_fal_webhook(
        session, {"request_id": "fal-req-1", "status": "ERROR", "error": "nsfw content"}
    )

    assert fake_redis.store[afs._daily_spend_key(user.id)] == "0"


async def test_webhook_ok_keeps_daily_spend(session, fake_redis, fal):
    # actual == estimated -> settle без корректировки, счётчик остаётся равным списанию.
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(session, _ok_payload())

    assert fake_redis.store[afs._daily_spend_key(user.id)] == "100"


async def test_reconcile_refund_decrements_daily_spend(session, fake_redis):
    model = _image_model()
    user = await _seed(session, model)
    await _seed_reserved_request(session, user, model, reserved_credits=100, age_minutes=30)
    fake_redis.store[afs._daily_spend_key(user.id)] = "100"  # состояние после record при reserve

    count = await refund_stale_reserved_requests(session, older_than_minutes=20)

    assert count == 1
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "0"
```

- [ ] **Step 3: Убедиться, что новые тесты падают**

Run: `python -m pytest tests/services/test_media_generation_service.py -v -k "duplicate_media or media_user_rate or video_blocked or cap_blocks_media or daily"`
Expected: FAIL (`DID NOT RAISE` / `KeyError` по daily-ключу).

- [ ] **Step 4: Вставить antifraud-вызовы в сервис**

В `app/services/media_generation_service.py`:

1. Импорт после блока `from app.services.credit_service import (...)` (строки 26-31):

```python
from app.services.antifraud_service import (
    check_daily_spend_limit,
    check_duplicate_request,
    check_free_tier_cap,
    check_rate_limits,
    check_tier_allowed,
    load_antifraud_settings,
    record_daily_spend,
)
```

2. Pre-checks в `start_media_generation` (сейчас строка 94), заменить:

```python
    model = await _get_media_model(session, model_code)
```

на:

```python
    model = await _get_media_model(session, model_code)

    # Antifraud pre-checks (фаза 5) -- быстрый отказ до оценки и лока.
    af_settings = await load_antifraud_settings(session)
    if not confirm:
        # confirm=True -- осознанный повтор после 409 ConfirmationRequired:
        # он приходит внутри cooldown-окна и не должен блокироваться дедупом.
        await check_duplicate_request(user.id, model_code, prompt, settings=af_settings)
    await check_rate_limits(user.id, model.code, settings=af_settings)
    await check_tier_allowed(user, model)
```

3. Cap/daily до confirmation-gate (сейчас строки 110-112), заменить:

```python
    if estimated > threshold and not confirm:
        # Ничего не создано, лок ещё не брался.
        raise ConfirmationRequiredError(estimated)
```

на:

```python
    # Antifraud (фаза 5): free-tier cap и дневной лимит -- после оценки, ДО
    # confirmation-gate (запись в daily-счётчик будет после reserve).
    await check_free_tier_cap(user, estimated, settings=af_settings)
    await check_daily_spend_limit(user.id, estimated, settings=af_settings)

    if estimated > threshold and not confirm:
        # Ничего не создано, лок ещё не брался.
        raise ConfirmationRequiredError(estimated)
```

4. Запись daily-счётчика после успешного commit резерва (сейчас строки 148-153), заменить:

```python
    except Exception:
        # Любая синхронная ошибка до submit -- лок снимается сразу.
        await redis_client.delete(lock_key)
        raise

    purpose = KeyPurpose.IMAGE if model.category == ModelCategory.image else KeyPurpose.VIDEO
```

на:

```python
    except Exception:
        # Любая синхронная ошибка до submit -- лок снимается сразу.
        await redis_client.delete(lock_key)
        raise

    await record_daily_spend(user.id, estimated)

    purpose = KeyPurpose.IMAGE if model.category == ModelCategory.image else KeyPurpose.VIDEO
```

5. Декремент при ошибке submit (сейчас строки 168-174), заменить:

```python
    except Exception as exc:
        # Резерв уже закоммичен -- возвращаем его и снимаем лок.
        request.error_message = str(exc)
        await refund_request(session, request, reason=f"fal submit failed: {exc}")
        await session.commit()
        await redis_client.delete(lock_key)
        raise AIError(f"fal submit failed: {exc}") from exc
```

на:

```python
    except Exception as exc:
        # Резерв уже закоммичен -- возвращаем его и снимаем лок.
        request.error_message = str(exc)
        await refund_request(session, request, reason=f"fal submit failed: {exc}")
        await session.commit()
        await record_daily_spend(user.id, -estimated)
        await redis_client.delete(lock_key)
        raise AIError(f"fal submit failed: {exc}") from exc
```

6. Декремент в OK-ветке вебхука без result_url (сейчас строки 226-234 внутри `handle_fal_webhook`), заменить:

```python
                request.error_message = "fal webhook: could not extract result url"
                await refund_request(
                    session, request, reason="fal webhook: could not extract result url"
                )
```

на:

```python
                request.error_message = "fal webhook: could not extract result url"
                await refund_request(
                    session, request, reason="fal webhook: could not extract result url"
                )
                await record_daily_spend(request.user_id, -request.reserved_credits)
```

7. Декремент в ERROR-ветке вебхука (сейчас строки 256-257), заменить:

```python
        try:
            await refund_request(session, request, reason=f"fal error: {error_message}")
            await session.commit()
```

на:

```python
        try:
            await refund_request(session, request, reason=f"fal error: {error_message}")
            await record_daily_spend(request.user_id, -request.reserved_credits)
            await session.commit()
```

8. Декремент в reconcile-джобе (сейчас строки 323-327 в `refund_stale_reserved_requests`), заменить:

```python
        await refund_request(
            session, request, reason="reconciliation: fal webhook never arrived"
        )
        await redis_client.delete(f"ai_lock:{request.user_id}")
        refunded_count += 1
```

на:

```python
        await refund_request(
            session, request, reason="reconciliation: fal webhook never arrived"
        )
        await record_daily_spend(request.user_id, -request.reserved_credits)
        await redis_client.delete(f"ai_lock:{request.user_id}")
        refunded_count += 1
```

- [ ] **Step 5: Убедиться, что все тесты проходят**

Run: `python -m pytest tests/services/test_media_generation_service.py tests/api/test_generate_routes.py -v`
Expected: PASS (старые + новые; Postgres-тест skipped).

- [ ] **Step 6: Commit**

```bash
git add app/services/media_generation_service.py tests/services/test_media_generation_service.py tests/api/test_generate_routes.py
git commit -m "feat(antifraud): интеграция guard'ов в медиа-flow (start/webhook/reconcile)"
```

---

### Task 6: Маппинг antifraud-исключений в `chat.py` / `generate.py`

**Files:**
- Modify: `app/api/routes/chat.py`
- Modify: `app/api/routes/generate.py`
- Test: `tests/api/test_chat_routes.py`, `tests/api/test_generate_routes.py`

**Interfaces:**
- Consumes: 5 исключений из Task 1 (импортируются из `app.services.antifraud_service`).
- Produces: HTTP-контракт из Global Constraints (429/403/402 + русские тексты). Существующие маппинги (404/409/402/502) не меняются.

- [ ] **Step 1: Написать падающие тесты**

В `tests/api/test_chat_routes.py` добавить импорт (после блока `from app.services.text_generation_service import (...)`):

```python
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
```

и тесты (после `test_chat_provider_error_maps_to_502`):

```python
async def test_chat_duplicate_request_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=DuplicateRequestError("dup")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком быстрый повтор запроса, подождите пару секунд"


async def test_chat_rate_limit_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=RateLimitExceededError("rl")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много запросов, попробуйте через минуту"


async def test_chat_tier_not_allowed_maps_to_403(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=TierNotAllowedError("tier")))
    response = await client.post("/api/chat", json={"model_code": "claude_opus", "prompt": "hi"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Эта модель доступна после первой покупки пакета"


async def test_chat_free_tier_limit_maps_to_402(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=FreeTierLimitExceededError("cap")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 402
    assert response.json()["detail"] == "Бесплатный лимит исчерпан, купите пакет кредитов"


async def test_chat_daily_spend_limit_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=DailySpendLimitExceededError("daily")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Дневной лимит трат исчерпан, попробуйте завтра"
```

В `tests/api/test_generate_routes.py` добавить к уже существующему (Task 5) импорту `afs` прямой импорт исключений:

```python
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
```

и тесты (после `test_generate_provider_error_maps_to_502`):

```python
async def test_generate_duplicate_request_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=DuplicateRequestError("dup"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком быстрый повтор запроса, подождите пару секунд"


async def test_generate_rate_limit_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=RateLimitExceededError("rl"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много запросов, попробуйте через минуту"


async def test_generate_tier_not_allowed_maps_to_403(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=TierNotAllowedError("tier"))
    )
    response = await client.post("/api/generate", json={"model_code": "veo_video", "prompt": "hi"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Эта модель доступна после первой покупки пакета"


async def test_generate_free_tier_limit_maps_to_402(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=FreeTierLimitExceededError("cap"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 402
    assert response.json()["detail"] == "Бесплатный лимит исчерпан, купите пакет кредитов"


async def test_generate_daily_spend_limit_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=DailySpendLimitExceededError("daily"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Дневной лимит трат исчерпан, попробуйте завтра"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/api/test_chat_routes.py tests/api/test_generate_routes.py -v -k "429 or 403 or free_tier or daily or tier_not"`
Expected: FAIL — необработанные исключения всплывают из роута (httpx поднимает исходное исключение вместо HTTP-ответа).

- [ ] **Step 3: Добавить except-блоки в роуты**

В `app/api/routes/chat.py`:

1. Импорт (после `from app.services.ai.base import AIError`):

```python
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
```

2. В функции `chat` — заменить:

```python
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов") from exc
    except AIError as exc:
```

на:

```python
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов") from exc
    except DuplicateRequestError as exc:
        raise HTTPException(
            status_code=429, detail="Слишком быстрый повтор запроса, подождите пару секунд"
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429, detail="Слишком много запросов, попробуйте через минуту"
        ) from exc
    except TierNotAllowedError as exc:
        raise HTTPException(
            status_code=403, detail="Эта модель доступна после первой покупки пакета"
        ) from exc
    except FreeTierLimitExceededError as exc:
        raise HTTPException(
            status_code=402, detail="Бесплатный лимит исчерпан, купите пакет кредитов"
        ) from exc
    except DailySpendLimitExceededError as exc:
        raise HTTPException(
            status_code=429, detail="Дневной лимит трат исчерпан, попробуйте завтра"
        ) from exc
    except AIError as exc:
```

В `app/api/routes/generate.py`: тот же импорт (после `from app.services.ai.base import AIError`) и ровно те же 5 except-блоков, вставленные в функцию `generate` между `except InsufficientBalanceError...` и `except AIError...` (текст блоков идентичен приведённому выше).

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/api/test_chat_routes.py tests/api/test_generate_routes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/chat.py app/api/routes/generate.py tests/api/test_chat_routes.py tests/api/test_generate_routes.py
git commit -m "feat(api): маппинг antifraud-исключений в chat/generate (429/403/402)"
```

---

### Task 7: Рерайт `stats_service.py` под новую схему

**Files:**
- Rewrite: `app/services/stats_service.py`
- Test: `tests/services/test_stats_service.py` (новый)

**Interfaces:**
- Consumes: `User.created_at`, `Payment` (`status`, `paid_at`, `amount`, `currency`), `AIRequest` (`created_at`, `status`, `provider_cost_usd`), `CreditTransaction` (`type`, `created_at`), enum'ы `PaymentStatus.succeeded`, `RequestStatus.failed`, `CreditTxType.purchase`.
- Produces (Task 9 полагается на эти ТОЧНЫЕ имена):
  - `@dataclass DailyStats(new_users: int, payments_count: int, payments_amount_rub: float, ai_requests: int, api_cost_usd: float, errors: int)`
  - `@dataclass MonthlyStats(revenue_rub: float, credits_purchases_count: int)`
  - `async get_daily_stats(session) -> DailyStats`, `async get_monthly_stats(session) -> MonthlyStats`

Изменения против старой версии (по спеке, минимальный фикс, НЕ Phase-6 аналитика): `Subscription`/`SubscriptionStatus` удаляются; `errors` считает `RequestStatus.failed` (старого `RequestStatus.error` не существует); `api_cost_usd` суммирует `AIRequest.provider_cost_usd` (поле существует, но до Phase 6 никем не заполняется — стабильно вернёт `0.0`, чинить сбор себестоимости сейчас НЕ в скоупе); `MonthlyStats.active_subscriptions` заменяется на `credits_purchases_count`.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/services/test_stats_service.py` целиком:

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import (
    CreditTxType,
    ModelCategory,
    PaymentProvider,
    PaymentStatus,
    RequestStatus,
)
from app.db.models import AIRequest, CreditTransaction, Payment, User
from app.services.stats_service import (
    DailyStats,
    MonthlyStats,
    get_daily_stats,
    get_monthly_stats,
)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


NOW = datetime.now(timezone.utc)
TWO_DAYS_AGO = NOW - timedelta(days=2)
LAST_MONTH = NOW - timedelta(days=40)


def _payment(user_id, amount, *, status=PaymentStatus.succeeded, paid_at=NOW, currency="RUB"):
    return Payment(
        user_id=user_id, provider=PaymentProvider.yookassa, amount=amount,
        currency=currency, status=status, idempotence_key=str(uuid.uuid4()),
        paid_at=paid_at,
    )


def _request(user_id, *, status=RequestStatus.completed, provider_cost_usd=0, created_at=NOW):
    return AIRequest(
        user_id=user_id, provider="openrouter", model_code="deepseek_v3",
        category=ModelCategory.text, status=status, prompt_preview="p",
        provider_cost_usd=provider_cost_usd, created_at=created_at,
    )


def _purchase_tx(user_id, *, tx_type=CreditTxType.purchase, created_at=NOW):
    return CreditTransaction(
        user_id=user_id, type=tx_type, amount=1000,
        balance_before=0, balance_after=1000, created_at=created_at,
    )


async def _seed_user(session, telegram_id=1, *, created_at=NOW) -> User:
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", created_at=created_at)
    session.add(user)
    await session.flush()
    return user


async def test_empty_db_returns_zero_stats(session):
    assert await get_daily_stats(session) == DailyStats(
        new_users=0, payments_count=0, payments_amount_rub=0.0,
        ai_requests=0, api_cost_usd=0.0, errors=0,
    )
    assert await get_monthly_stats(session) == MonthlyStats(
        revenue_rub=0.0, credits_purchases_count=0
    )


async def test_daily_stats_counts_today_only(session):
    user = await _seed_user(session, 1)
    await _seed_user(session, 2, created_at=TWO_DAYS_AGO)  # не сегодня

    session.add(_payment(user.id, 599))
    session.add(_payment(user.id, 149, paid_at=TWO_DAYS_AGO))          # не сегодня
    session.add(_payment(user.id, 100, status=PaymentStatus.pending))  # не succeeded

    session.add(_request(user.id))
    session.add(_request(user.id, status=RequestStatus.failed))
    session.add(_request(user.id, status=RequestStatus.refunded))
    session.add(_request(user.id, created_at=TWO_DAYS_AGO))  # не сегодня
    await session.commit()

    daily = await get_daily_stats(session)
    assert daily.new_users == 1
    assert daily.payments_count == 1
    assert daily.payments_amount_rub == 599.0
    assert daily.ai_requests == 3           # только сегодняшние
    assert daily.errors == 1                # только RequestStatus.failed
    assert daily.api_cost_usd == 0.0        # provider_cost_usd не заполняется до Phase 6


async def test_daily_api_cost_sums_provider_cost_usd(session):
    user = await _seed_user(session)
    session.add(_request(user.id, provider_cost_usd=0.25))
    session.add(_request(user.id, provider_cost_usd=0.5))
    await session.commit()

    daily = await get_daily_stats(session)
    assert daily.api_cost_usd == 0.75


async def test_monthly_stats_revenue_and_purchases_count(session):
    user = await _seed_user(session)
    session.add(_payment(user.id, 599))
    session.add(_payment(user.id, 149, paid_at=LAST_MONTH))  # не этот месяц

    session.add(_purchase_tx(user.id))
    session.add(_purchase_tx(user.id))
    session.add(_purchase_tx(user.id, created_at=LAST_MONTH))          # не этот месяц
    session.add(_purchase_tx(user.id, tx_type=CreditTxType.spend))     # не purchase
    await session.commit()

    monthly = await get_monthly_stats(session)
    assert monthly.revenue_rub == 599.0
    assert monthly.credits_purchases_count == 2
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/services/test_stats_service.py -v`
Expected: FAIL на импорте — старый `stats_service.py` импортирует несуществующие `SubscriptionStatus`/`Subscription` (`ImportError`).

- [ ] **Step 3: Переписать `app/services/stats_service.py` целиком**

```python
"""Статистика для GET /admin/stats. Фаза 5: минимальный фикс под новую схему
(AiModel/CreditPackage/CreditTransaction), НЕ Phase-6 аналитика.

- api_cost_usd читает AIRequest.provider_cost_usd: поле существует, но ни одна
  фаза его не заполняет -- стабильно вернёт 0.0 до Phase 6 (вне скоупа).
- active_subscriptions больше нет (подписки удалены в фазе 1); ближайший
  осмысленный аналог "активности" -- credits_purchases_count (число покупок
  кредитов за месяц).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType, PaymentStatus, RequestStatus
from app.db.models import AIRequest, CreditTransaction, Payment, User


@dataclass
class DailyStats:
    new_users: int
    payments_count: int
    payments_amount_rub: float
    ai_requests: int
    api_cost_usd: float
    errors: int


@dataclass
class MonthlyStats:
    revenue_rub: float
    credits_purchases_count: int


async def get_daily_stats(session: AsyncSession) -> DailyStats:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    new_users = (
        await session.execute(select(func.count(User.id)).where(User.created_at >= day_start))
    ).scalar_one()

    payments_count, payments_amount = (
        await session.execute(
            select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.succeeded,
                Payment.paid_at >= day_start,
                Payment.currency == "RUB",
            )
        )
    ).one()

    ai_requests = (
        await session.execute(select(func.count(AIRequest.id)).where(AIRequest.created_at >= day_start))
    ).scalar_one()

    api_cost = (
        await session.execute(
            select(func.coalesce(func.sum(AIRequest.provider_cost_usd), 0)).where(
                AIRequest.created_at >= day_start
            )
        )
    ).scalar_one()

    errors = (
        await session.execute(
            select(func.count(AIRequest.id)).where(
                AIRequest.created_at >= day_start, AIRequest.status == RequestStatus.failed
            )
        )
    ).scalar_one()

    return DailyStats(
        new_users=new_users,
        payments_count=payments_count,
        payments_amount_rub=float(payments_amount),
        ai_requests=ai_requests,
        api_cost_usd=float(api_cost),
        errors=errors,
    )


async def get_monthly_stats(session: AsyncSession) -> MonthlyStats:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    revenue = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.succeeded,
                Payment.paid_at >= month_start,
                Payment.currency == "RUB",
            )
        )
    ).scalar_one()

    credits_purchases_count = (
        await session.execute(
            select(func.count(CreditTransaction.id)).where(
                CreditTransaction.type == CreditTxType.purchase,
                CreditTransaction.created_at >= month_start,
            )
        )
    ).scalar_one()

    return MonthlyStats(
        revenue_rub=float(revenue), credits_purchases_count=credits_purchases_count
    )
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/services/test_stats_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/stats_service.py tests/services/test_stats_service.py
git commit -m "feat(stats): рерайт stats_service под схему v2 (failed, provider_cost_usd, purchases_count)"
```

---

### Task 8: Рерайт `key_healthcheck.py` под 2 провайдера

**Files:**
- Rewrite: `app/services/keys/key_healthcheck.py`
- Test: `tests/services/keys/test_key_healthcheck.py` (новый)

**Interfaces:**
- Consumes: `AiModel` (`provider`, `category`, `code`, `is_active`), `ModelProvider.openrouter/.fal`, `ModelCategory`, `Provider.OPENROUTER/.FAL`, `KeyPurpose.TEXT/.IMAGE/.VIDEO`, `ApiKeyManager.has_key(provider, purpose) -> bool`, `get_key_manager()`.
- Produces: `async run_key_healthcheck(session: AsyncSession, key_manager: ApiKeyManager | None = None) -> None` — сигнатура не меняется (используется в `app/main.py` lifespan). Purpose выводится из `ModelCategory` (поля `key_purpose` на `AiModel` не существует).

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/services/keys/test_key_healthcheck.py` целиком:

```python
import logging

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.keys.enums import KeyPurpose, Provider
from app.services.keys.key_healthcheck import run_key_healthcheck


class FakeKeyManager:
    def __init__(self, configured: set[tuple[Provider, KeyPurpose]] = frozenset()):
        self.configured = set(configured)
        self.calls: list[tuple[Provider, KeyPurpose]] = []

    def has_key(self, provider, purpose):
        self.calls.append((provider, purpose))
        return (provider, purpose) in self.configured


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _model(code, category, provider, *, is_active=True) -> AiModel:
    cost_unit = CostUnit.tokens if category == ModelCategory.text else CostUnit.image
    return AiModel(
        provider=provider, category=category, code=code, display_name=code,
        provider_model_id=f"x/{code}", tier=ModelTier.standard, cost_unit=cost_unit,
        min_credits=0, recommended_credits=1, is_active=is_active,
    )


async def test_logs_ok_for_configured_key_and_missing_for_absent(session, caplog):
    session.add(_model("txt", ModelCategory.text, ModelProvider.openrouter))
    session.add(_model("vid", ModelCategory.video, ModelProvider.fal))
    await session.commit()
    manager = FakeKeyManager(configured={(Provider.OPENROUTER, KeyPurpose.TEXT)})

    with caplog.at_level(logging.INFO, logger="app.services.keys.key_healthcheck"):
        await run_key_healthcheck(session, manager)  # не кидает даже при MISSING

    ok = [r for r in caplog.records if "[OK]" in r.message]
    missing = [r for r in caplog.records if "[MISSING]" in r.message]
    assert len(ok) == 1 and "txt" in ok[0].message
    assert len(missing) == 1 and "vid" in missing[0].message


async def test_purpose_is_derived_from_category(session):
    session.add(_model("txt", ModelCategory.text, ModelProvider.openrouter))
    session.add(_model("img", ModelCategory.image, ModelProvider.fal))
    session.add(_model("vid", ModelCategory.video, ModelProvider.fal))
    await session.commit()
    manager = FakeKeyManager()

    await run_key_healthcheck(session, manager)

    assert set(manager.calls) == {
        (Provider.OPENROUTER, KeyPurpose.TEXT),
        (Provider.FAL, KeyPurpose.IMAGE),
        (Provider.FAL, KeyPurpose.VIDEO),
    }


async def test_inactive_models_are_skipped(session):
    session.add(_model("dead", ModelCategory.text, ModelProvider.openrouter, is_active=False))
    await session.commit()
    manager = FakeKeyManager()

    await run_key_healthcheck(session, manager)

    assert manager.calls == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/services/keys/test_key_healthcheck.py -v`
Expected: FAIL на импорте — старый `key_healthcheck.py` импортирует несуществующий `ModelConfig` (`ImportError`).

- [ ] **Step 3: Переписать `app/services/keys/key_healthcheck.py` целиком**

```python
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelCategory, ModelProvider
from app.db.models import AiModel
from app.services.keys.api_key_manager import ApiKeyManager, get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

logger = logging.getLogger(__name__)

# Провайдеров в каталоге ровно два (фаза 1). Поля key_purpose на AiModel нет
# (в отличие от старого ModelConfig) -- purpose выводится из категории модели.
_DB_PROVIDER_TO_KEY_PROVIDER = {
    ModelProvider.openrouter: Provider.OPENROUTER,
    ModelProvider.fal: Provider.FAL,
}

_CATEGORY_TO_PURPOSE = {
    ModelCategory.text: KeyPurpose.TEXT,
    ModelCategory.image: KeyPurpose.IMAGE,
    ModelCategory.video: KeyPurpose.VIDEO,
}


async def run_key_healthcheck(
    session: AsyncSession, key_manager: ApiKeyManager | None = None
) -> None:
    """Логирует статус ключей активных моделей при старте.

    Никогда не роняет приложение: отсутствующий ключ означает, что конкретная
    модель ответит пользователю безопасной ошибкой ("модель временно
    недоступна"), а не крэш всего сервиса -- так остальные модели и функции
    (пакеты, баланс, оплата) продолжают работать, даже если часть AI-ключей
    ещё не настроена.
    """
    key_manager = key_manager or get_key_manager()

    models = (
        await session.execute(select(AiModel).where(AiModel.is_active.is_(True)))
    ).scalars().all()

    for model in models:
        provider = _DB_PROVIDER_TO_KEY_PROVIDER.get(model.provider)
        if provider is None:
            logger.warning(
                "[WARNING] %s: no key-manager mapping for provider=%s", model.code, model.provider
            )
            continue

        purpose = _CATEGORY_TO_PURPOSE.get(model.category)
        if purpose is None:
            logger.warning(
                "[WARNING] %s: no key purpose for category=%s", model.code, model.category
            )
            continue

        if key_manager.has_key(provider, purpose):
            logger.info("[OK] %s/%s configured (model=%s)", provider.value, purpose.value, model.code)
        else:
            logger.warning(
                "[MISSING] %s is active but %s/%s key is not configured -- "
                "requests to it will fail with a safe error until the key is set",
                model.code, provider.value, purpose.value,
            )
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/services/keys/ -v`
Expected: PASS (включая существующий `test_openrouter_key.py`).

- [ ] **Step 5: Commit**

```bash
git add app/services/keys/key_healthcheck.py tests/services/keys/test_key_healthcheck.py
git commit -m "feat(keys): key_healthcheck v2 -- openrouter/fal, purpose из category"
```

---

### Task 9: Полный рерайт `admin.py` + удаление `admin_service.py` + `tests/api/test_admin.py`

**Files:**
- Rewrite: `app/api/routes/admin.py`
- Delete: `app/services/admin_service.py`
- Test: `tests/api/test_admin.py` (новый)

**Interfaces:**
- Consumes: `adjust_credits_admin` + `InsufficientBalanceError` (Task 3), `set_setting` (Task 2), `get_daily_stats`/`get_monthly_stats` + `DailyStats.errors`/`MonthlyStats.credits_purchases_count` (Task 7), `get_user_by_telegram_id`/`search_users`/`set_blocked` (существующий `user_service`), `refund` (существующий `refund_service`), модели `AiModel`/`CreditPackage`/`Setting`/`CreditTransaction`/`Payment`/`Banner`/`User`.
- Produces: HTTP-дерево из спеки. Секции payments и banners — дословный перенос из текущего файла.

Обоснование удаления `admin_service.py`: обе его функции (`grant_manual_subscription`, `cancel_subscription`) оперируют удалёнными в фазе 1 моделями `Subscription`/`Tariff`; в новом дереве эндпойнтов замена — `POST /users/{telegram_id}/credits` → `credit_service.adjust_credits_admin` напрямую (спека). Обёртка не нужна; единственный импортёр — старый `admin.py`. Спека не определяет ни одной функции admin_service, поэтому «рерайт» этого файла = удаление.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/api/test_admin.py` целиком:

```python
import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
# postgresql+asyncpg:// (не голый postgresql://): app.api.deps -> app.db.session
# строит create_async_engine при импорте модуля -- см. комментарий в
# tests/api/test_chat_routes.py.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_admin, get_db
from app.api.routes import admin
from app.db.base import Base
from app.db.enums import CostUnit, CreditTxType, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel, CreditPackage, CreditTransaction, Setting, User

app = FastAPI()
app.include_router(admin.router, prefix="/api")

_admin_user = User(
    id=99, telegram_id=99, username="admin", first_name="A", is_admin=True,
    default_model_code=None, credits_balance=0,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_admin():
    return _admin_user


@pytest.fixture
async def db_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(User(
            id=1, telegram_id=100, username="alice", first_name="Alice",
            credits_balance=100, total_credits_purchased=1000, total_credits_spent=900,
        ))
        s.add(AiModel(
            provider=ModelProvider.openrouter, category=ModelCategory.text,
            code="deepseek_v3", display_name="DeepSeek V3",
            provider_model_id="deepseek/deepseek-chat", tier=ModelTier.economy,
            cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=3, sort_order=10,
        ))
        s.add(CreditPackage(
            code="start", title="START", credits=1000, price_rub=149, price_stars=75,
        ))
        s.add(Setting(
            key="margin_multiplier", value="2.5", type="float",
            description="Множитель целевой маржи",
        ))
        await s.commit()
    yield maker
    await engine.dispose()


@pytest.fixture
async def client(db_sessionmaker):
    async def _get_db():
        async with db_sessionmaker() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[current_admin] = _fake_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# --- GET /api/admin/stats ---

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
        "month_revenue_rub": 0.0,
        "month_credits_purchases_count": 0,
    }


# --- users ---

async def test_get_user_returns_credit_fields(client):
    response = await client.get("/api/admin/users/100")

    assert response.status_code == 200
    assert response.json() == {
        "telegram_id": 100,
        "username": "alice",
        "first_name": "Alice",
        "is_admin": False,
        "is_blocked": False,
        "credits_balance": 100,
        "total_credits_purchased": 1000,
        "total_credits_spent": 900,
    }


async def test_get_unknown_user_is_404(client):
    response = await client.get("/api/admin/users/777")
    assert response.status_code == 404


async def test_users_search_by_username(client):
    response = await client.get("/api/admin/users", params={"query": "ali"})
    assert response.status_code == 200
    assert [u["telegram_id"] for u in response.json()] == [100]


async def test_block_and_unblock_user(client):
    blocked = await client.post("/api/admin/users/100/block")
    assert blocked.status_code == 200
    assert blocked.json()["is_blocked"] is True

    unblocked = await client.post("/api/admin/users/100/unblock")
    assert unblocked.json()["is_blocked"] is False


# --- POST /api/admin/users/{telegram_id}/credits ---

async def test_adjust_credits_positive_amount(client, db_sessionmaker):
    response = await client.post("/api/admin/users/100/credits", json={"amount": 50})

    assert response.status_code == 200
    body = response.json()
    assert body["credits_balance"] == 150
    assert body["total_credits_purchased"] == 1000  # totals не трогаются
    assert body["total_credits_spent"] == 900

    async with db_sessionmaker() as s:
        [tx] = (await s.execute(select(CreditTransaction))).scalars().all()
        assert tx.type == CreditTxType.admin_adjustment
        assert tx.amount == 50


async def test_adjust_credits_negative_amount(client):
    response = await client.post("/api/admin/users/100/credits", json={"amount": -60})
    assert response.status_code == 200
    assert response.json()["credits_balance"] == 40


async def test_adjust_credits_below_zero_is_400(client):
    response = await client.post("/api/admin/users/100/credits", json={"amount": -101})
    assert response.status_code == 400
    assert response.json()["detail"] == "Недостаточно кредитов для списания"


async def test_adjust_credits_zero_is_422(client):
    response = await client.post("/api/admin/users/100/credits", json={"amount": 0})
    assert response.status_code == 422


# --- GET /api/admin/users/{telegram_id}/transactions ---

async def test_transactions_paginated_newest_first(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        for i, amount in enumerate([10, 20, 30], start=1):
            s.add(CreditTransaction(
                user_id=1, type=CreditTxType.purchase, amount=amount,
                balance_before=0, balance_after=amount, description=f"tx{i}",
            ))
        await s.commit()

    page1 = await client.get("/api/admin/users/100/transactions", params={"limit": 2})
    assert page1.status_code == 200
    assert [tx["amount"] for tx in page1.json()] == [30, 20]  # новейшие первыми
    assert page1.json()[0]["type"] == "purchase"

    page2 = await client.get(
        "/api/admin/users/100/transactions", params={"limit": 2, "offset": 2}
    )
    assert [tx["amount"] for tx in page2.json()] == [10]


# --- models ---

async def test_models_list_returns_catalog_fields(client):
    response = await client.get("/api/admin/models")

    assert response.status_code == 200
    [model] = response.json()
    assert model == {
        "code": "deepseek_v3",
        "provider": "openrouter",
        "category": "text",
        "tier": "economy",
        "display_name": "DeepSeek V3",
        "provider_model_id": "deepseek/deepseek-chat",
        "input_price_usd_per_1m_tokens": 0.0,
        "output_price_usd_per_1m_tokens": 0.0,
        "min_credits": 3,
        "recommended_credits": 3,
        "is_active": True,
        "is_visible": True,
        "sort_order": 10,
    }


async def test_patch_model_updates_editable_fields(client, db_sessionmaker):
    response = await client.patch("/api/admin/models/deepseek_v3", json={
        "is_active": False,
        "recommended_credits": 9,
        "input_price_usd_per_1m_tokens": 0.5,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False
    assert body["recommended_credits"] == 9
    assert body["input_price_usd_per_1m_tokens"] == 0.5

    async with db_sessionmaker() as s:
        row = (await s.execute(select(AiModel).where(AiModel.code == "deepseek_v3"))).scalar_one()
        assert row.is_active is False
        assert row.recommended_credits == 9


async def test_patch_unknown_model_is_404(client):
    response = await client.patch("/api/admin/models/nope", json={"is_active": False})
    assert response.status_code == 404


# --- packages ---

async def test_packages_list_and_patch(client, db_sessionmaker):
    listed = await client.get("/api/admin/packages")
    assert listed.status_code == 200
    assert [p["code"] for p in listed.json()] == ["start"]

    patched = await client.patch("/api/admin/packages/start", json={
        "price_stars": 99, "credits": 1200, "is_active": False,
    })
    assert patched.status_code == 200
    body = patched.json()
    assert body["price_stars"] == 99
    assert body["credits"] == 1200
    assert body["is_active"] is False

    async with db_sessionmaker() as s:
        row = (await s.execute(select(CreditPackage).where(CreditPackage.code == "start"))).scalar_one()
        assert row.price_stars == 99


async def test_patch_unknown_package_is_404(client):
    response = await client.patch("/api/admin/packages/nope", json={"credits": 1})
    assert response.status_code == 404


# --- settings ---

async def test_settings_list_returns_rows(client):
    response = await client.get("/api/admin/settings")
    assert response.status_code == 200
    assert response.json() == [{
        "key": "margin_multiplier",
        "value": "2.5",
        "type": "float",
        "description": "Множитель целевой маржи",
    }]


async def test_patch_setting_updates_value_keeps_type(client, db_sessionmaker):
    response = await client.patch(
        "/api/admin/settings/margin_multiplier", json={"value": "3.0"}
    )

    assert response.status_code == 200
    assert response.json()["value"] == "3.0"
    assert response.json()["type"] == "float"

    async with db_sessionmaker() as s:
        row = await s.get(Setting, "margin_multiplier")
        assert row.value == "3.0"
        assert row.type == "float"


async def test_patch_unknown_setting_is_404(client):
    response = await client.patch("/api/admin/settings/no_such_key", json={"value": "1"})
    assert response.status_code == 404


# --- старые tariff-эндпойнты удалены ---

async def test_tariffs_endpoints_are_gone(client):
    assert (await client.get("/api/admin/tariffs")).status_code == 404
    assert (
        await client.post("/api/admin/users/100/grant", json={"tariff_code": "x"})
    ).status_code == 404
    assert (await client.post("/api/admin/users/100/cancel-subscription")).status_code == 404
    assert (
        await client.post("/api/admin/users/100/grant-credits", json={"amount": 1})
    ).status_code == 404
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/api/test_admin.py -v`
Expected: FAIL на импорте `app.api.routes.admin` — старый файл импортирует несуществующие `ModelConfig`/`Tariff`/`subscription_service` (`ImportError`/`ModuleNotFoundError`).

- [ ] **Step 3: Переписать `app/api/routes/admin.py` целиком и удалить `admin_service.py`**

```bash
git rm app/services/admin_service.py
```

Новый `app/api/routes/admin.py` (секции payments и banners — дословный перенос из старого файла):

```python
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_admin, get_db
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import (
    AiModel,
    Banner,
    CreditPackage,
    CreditTransaction,
    Payment,
    Setting,
    User,
)
from app.services.credit_service import InsufficientBalanceError, adjust_credits_admin
from app.services.payments.refund_service import refund
from app.services.settings_service import set_setting
from app.services.stats_service import get_daily_stats, get_monthly_stats
from app.services.user_service import get_user_by_telegram_id, search_users, set_blocked

router = APIRouter(prefix="/admin", dependencies=[Depends(current_admin)])


# --- stats -------------------------------------------------------------

class StatsOut(BaseModel):
    today_new_users: int
    today_payments_count: int
    today_payments_amount_rub: float
    today_ai_requests: int
    today_api_cost_usd: float
    today_errors: int
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
        month_revenue_rub=monthly.revenue_rub,
        month_credits_purchases_count=monthly.credits_purchases_count,
    )


# --- users ---------------------------------------------------------------

class UserOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    is_blocked: bool
    credits_balance: int
    total_credits_purchased: int
    total_credits_spent: int


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        is_admin=user.is_admin,
        is_blocked=user.is_blocked,
        credits_balance=user.credits_balance,
        total_credits_purchased=user.total_credits_purchased,
        total_credits_spent=user.total_credits_spent,
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(query: str | None = None, session: AsyncSession = Depends(get_db)) -> list[UserOut]:
    users = await search_users(session, query)
    return [_to_user_out(u) for u in users]


async def _get_user_or_404(session: AsyncSession, telegram_id: int) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.get("/users/{telegram_id}", response_model=UserOut)
async def get_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    return _to_user_out(user)


@router.post("/users/{telegram_id}/block", response_model=UserOut)
async def block_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    await set_blocked(session, user, True)
    return _to_user_out(user)


@router.post("/users/{telegram_id}/unblock", response_model=UserOut)
async def unblock_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    await set_blocked(session, user, False)
    return _to_user_out(user)


class TransactionOut(BaseModel):
    id: int
    type: str
    amount: int
    balance_before: int
    balance_after: int
    provider: str | None
    model_code: str | None
    request_id: int | None
    description: str | None
    created_at: str


@router.get("/users/{telegram_id}/transactions", response_model=list[TransactionOut])
async def list_user_transactions(
    telegram_id: int,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> list[TransactionOut]:
    user = await _get_user_or_404(session, telegram_id)
    txs = (
        await session.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user.id)
            .order_by(CreditTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return [
        TransactionOut(
            id=tx.id,
            type=tx.type.value,
            amount=tx.amount,
            balance_before=tx.balance_before,
            balance_after=tx.balance_after,
            provider=tx.provider,
            model_code=tx.model_code,
            request_id=tx.request_id,
            description=tx.description,
            created_at=tx.created_at.isoformat(),
        )
        for tx in txs
    ]


class AdjustCreditsRequest(BaseModel):
    amount: int
    reason: str = "ручная корректировка админом"


@router.post("/users/{telegram_id}/credits", response_model=UserOut)
async def adjust_user_credits(
    telegram_id: int, body: AdjustCreditsRequest, session: AsyncSession = Depends(get_db)
) -> UserOut:
    if body.amount == 0:
        raise HTTPException(status_code=422, detail="amount не может быть нулевым")
    user = await _get_user_or_404(session, telegram_id)
    try:
        await adjust_credits_admin(session, user.id, body.amount, reason=body.reason)
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=400, detail="Недостаточно кредитов для списания") from exc
    await session.commit()
    return _to_user_out(user)


# --- payments ------------------------------------------------------------

class PaymentOut(BaseModel):
    id: int
    telegram_id: int
    provider: str
    amount: float
    currency: str
    status: str
    created_at: str


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    status: str | None = None, provider: str | None = None, session: AsyncSession = Depends(get_db)
) -> list[PaymentOut]:
    stmt = select(Payment).order_by(Payment.created_at.desc()).limit(50)
    if status:
        try:
            stmt = stmt.where(Payment.status == PaymentStatus(status))
        except ValueError:
            raise HTTPException(status_code=422, detail="Некорректный status")
    if provider:
        try:
            stmt = stmt.where(Payment.provider == PaymentProvider(provider))
        except ValueError:
            raise HTTPException(status_code=422, detail="Некорректный provider")

    payments = (await session.execute(stmt)).scalars().all()
    out = []
    for p in payments:
        user = await session.get(User, p.user_id)
        out.append(
            PaymentOut(
                id=p.id,
                telegram_id=user.telegram_id if user else 0,
                provider=p.provider.value,
                amount=float(p.amount),
                currency=p.currency,
                status=p.status.value,
                created_at=p.created_at.isoformat(),
            )
        )
    return out


@router.post("/payments/{payment_id}/refund", response_model=PaymentOut)
async def refund_payment(payment_id: int, session: AsyncSession = Depends(get_db)) -> PaymentOut:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")

    ok = await refund(session, payment)
    if not ok:
        raise HTTPException(status_code=400, detail="Возврат не удался")

    user = await session.get(User, payment.user_id)
    return PaymentOut(
        id=payment.id,
        telegram_id=user.telegram_id if user else 0,
        provider=payment.provider.value,
        amount=float(payment.amount),
        currency=payment.currency,
        status=payment.status.value,
        created_at=payment.created_at.isoformat(),
    )


# --- models ---------------------------------------------------------------

class AiModelAdminOut(BaseModel):
    code: str
    provider: str
    category: str
    tier: str
    display_name: str
    provider_model_id: str
    input_price_usd_per_1m_tokens: float
    output_price_usd_per_1m_tokens: float
    min_credits: int
    recommended_credits: int
    is_active: bool
    is_visible: bool
    sort_order: int


def _to_model_out(m: AiModel) -> AiModelAdminOut:
    return AiModelAdminOut(
        code=m.code,
        provider=m.provider.value,
        category=m.category.value,
        tier=m.tier.value,
        display_name=m.display_name,
        provider_model_id=m.provider_model_id,
        input_price_usd_per_1m_tokens=float(m.input_price_usd_per_1m_tokens),
        output_price_usd_per_1m_tokens=float(m.output_price_usd_per_1m_tokens),
        min_credits=m.min_credits,
        recommended_credits=m.recommended_credits,
        is_active=m.is_active,
        is_visible=m.is_visible,
        sort_order=m.sort_order,
    )


@router.get("/models", response_model=list[AiModelAdminOut])
async def list_models(session: AsyncSession = Depends(get_db)) -> list[AiModelAdminOut]:
    models = (
        await session.execute(select(AiModel).order_by(AiModel.sort_order, AiModel.id))
    ).scalars().all()
    return [_to_model_out(m) for m in models]


class AiModelUpdateRequest(BaseModel):
    is_active: bool | None = None
    is_visible: bool | None = None
    recommended_credits: int | None = None
    min_credits: int | None = None
    provider_model_id: str | None = None
    input_price_usd_per_1m_tokens: float | None = None
    output_price_usd_per_1m_tokens: float | None = None
    sort_order: int | None = None


@router.patch("/models/{code}", response_model=AiModelAdminOut)
async def update_model(
    code: str, body: AiModelUpdateRequest, session: AsyncSession = Depends(get_db)
) -> AiModelAdminOut:
    model = (
        await session.execute(select(AiModel).where(AiModel.code == code))
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Модель не найдена")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    await session.commit()

    return _to_model_out(model)


# --- packages ---------------------------------------------------------------

class PackageAdminOut(BaseModel):
    code: str
    title: str
    credits: int
    price_rub: float
    price_stars: int
    description: str | None
    is_active: bool


def _to_package_out(p: CreditPackage) -> PackageAdminOut:
    return PackageAdminOut(
        code=p.code,
        title=p.title,
        credits=p.credits,
        price_rub=float(p.price_rub),
        price_stars=p.price_stars,
        description=p.description,
        is_active=p.is_active,
    )


@router.get("/packages", response_model=list[PackageAdminOut])
async def list_packages(session: AsyncSession = Depends(get_db)) -> list[PackageAdminOut]:
    packages = (
        await session.execute(select(CreditPackage).order_by(CreditPackage.price_rub))
    ).scalars().all()
    return [_to_package_out(p) for p in packages]


class PackageUpdateRequest(BaseModel):
    credits: int | None = None
    price_rub: float | None = None
    price_stars: int | None = None
    is_active: bool | None = None


@router.patch("/packages/{code}", response_model=PackageAdminOut)
async def update_package(
    code: str, body: PackageUpdateRequest, session: AsyncSession = Depends(get_db)
) -> PackageAdminOut:
    package = (
        await session.execute(select(CreditPackage).where(CreditPackage.code == code))
    ).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="Пакет не найден")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(package, field, value)
    await session.commit()

    return _to_package_out(package)


# --- settings ---------------------------------------------------------------

class SettingOut(BaseModel):
    key: str
    value: str
    type: str
    description: str | None


def _to_setting_out(s: Setting) -> SettingOut:
    return SettingOut(key=s.key, value=s.value, type=s.type, description=s.description)


@router.get("/settings", response_model=list[SettingOut])
async def list_settings(session: AsyncSession = Depends(get_db)) -> list[SettingOut]:
    rows = (await session.execute(select(Setting).order_by(Setting.key))).scalars().all()
    return [_to_setting_out(s) for s in rows]


class SettingUpdateRequest(BaseModel):
    value: str


@router.patch("/settings/{key}", response_model=SettingOut)
async def update_setting(
    key: str, body: SettingUpdateRequest, session: AsyncSession = Depends(get_db)
) -> SettingOut:
    row = await session.get(Setting, key)
    if row is None:
        raise HTTPException(status_code=404, detail="Настройка не найдена")

    # type/description не меняются при обновлении значения существующего ключа.
    row = await set_setting(session, key, body.value, type_=row.type, description=row.description)
    await session.commit()
    return _to_setting_out(row)


# --- banners ---------------------------------------------------------------

class BannerAdminOut(BaseModel):
    id: int
    title: str
    subtitle: str | None
    badge_text: str | None
    cta_text: str
    image_url: str
    action_type: str
    action_value: str
    sort_order: int
    is_active: bool


def _to_banner_admin_out(b: Banner) -> BannerAdminOut:
    return BannerAdminOut(
        id=b.id, title=b.title, subtitle=b.subtitle, badge_text=b.badge_text, cta_text=b.cta_text,
        image_url=b.image_url, action_type=b.action_type, action_value=b.action_value,
        sort_order=b.sort_order, is_active=b.is_active,
    )


@router.get("/banners", response_model=list[BannerAdminOut])
async def list_banners_admin(session: AsyncSession = Depends(get_db)) -> list[BannerAdminOut]:
    banners = (await session.execute(select(Banner).order_by(Banner.sort_order, Banner.id))).scalars().all()
    return [_to_banner_admin_out(b) for b in banners]


class BannerCreateRequest(BaseModel):
    title: str
    subtitle: str | None = None
    badge_text: str | None = None
    cta_text: str = "Открыть"
    image_url: str
    action_type: Literal["prompt", "link"] = "prompt"
    action_value: str
    sort_order: int = 0
    is_active: bool = True


@router.post("/banners", response_model=BannerAdminOut)
async def create_banner(body: BannerCreateRequest, session: AsyncSession = Depends(get_db)) -> BannerAdminOut:
    banner = Banner(**body.model_dump())
    session.add(banner)
    await session.commit()
    return _to_banner_admin_out(banner)


class BannerUpdateRequest(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    badge_text: str | None = None
    cta_text: str | None = None
    image_url: str | None = None
    action_type: Literal["prompt", "link"] | None = None
    action_value: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


async def _get_banner_or_404(session: AsyncSession, banner_id: int) -> Banner:
    banner = await session.get(Banner, banner_id)
    if banner is None:
        raise HTTPException(status_code=404, detail="Баннер не найден")
    return banner


@router.patch("/banners/{banner_id}", response_model=BannerAdminOut)
async def update_banner(
    banner_id: int, body: BannerUpdateRequest, session: AsyncSession = Depends(get_db)
) -> BannerAdminOut:
    banner = await _get_banner_or_404(session, banner_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(banner, field, value)
    await session.commit()
    return _to_banner_admin_out(banner)


@router.delete("/banners/{banner_id}")
async def delete_banner(banner_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    banner = await _get_banner_or_404(session, banner_id)
    await session.delete(banner)
    await session.commit()
    return {"ok": True}
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/api/test_admin.py -v`
Expected: PASS.

- [ ] **Step 5: Прогнать все api-тесты**

Run: `python -m pytest tests/api/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes/admin.py tests/api/test_admin.py
git add -u app/services/admin_service.py
git commit -m "feat(admin): рерайт admin API v2 (models/packages/users/transactions/credits/settings), удалён admin_service"
```

---

### Task 10: Сиды антифрод-настроек + alembic-миграция

**Files:**
- Modify: `app/db/seed.py` (5 новых строк в `SETTINGS_ROWS`)
- Create: `alembic/versions/f7a8b9c0d1e2_phase5_antifraud_settings.py`
- Modify: `tests/db/test_seed_catalog.py` (тесты фиксируют 5 строк settings — обновить до 10)

**Interfaces:**
- Consumes: модель `Setting`, конвенция идемпотентного сида (`apply_seed` вставляет только отсутствующие ключи), стиль миграций фаз 3-4 (`revision`/`down_revision`, docstring, `op.execute`/`op.bulk_insert`).
- Produces: строки settings, которые читает `load_antifraud_settings` (Task 1) и отдаёт/правит `GET|PATCH /admin/settings` (Task 9).

- [ ] **Step 1: Обновить тесты сидов (падающие)**

В `tests/db/test_seed_catalog.py` заменить `test_five_settings_rows_with_spec_values` на:

```python
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
```

и в `test_apply_seed_inserts_and_is_idempotent` заменить строку `assert settings_count == 5` на `assert settings_count == 10`.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/db/test_seed_catalog.py -v`
Expected: FAIL — `test_settings_rows_with_spec_values` и `test_apply_seed_inserts_and_is_idempotent` (в сиде пока 5 строк).

- [ ] **Step 3: Добавить сиды и миграцию**

В `app/db/seed.py` в конец списка `SETTINGS_ROWS` (после строки с `minimum_text_credits`) добавить:

```python
    # --- antifraud (фаза 5) ---
    dict(key="daily_spend_limit_credits", value="10000", type="int",
         description="Дневной лимит трат на пользователя"),
    dict(key="rate_limit_per_user_per_minute", value="10", type="int",
         description="Rate limit запросов на пользователя"),
    dict(key="rate_limit_per_model_per_minute", value="60", type="int",
         description="Rate limit запросов на модель (глобально)"),
    dict(key="duplicate_cooldown_seconds", value="5", type="int",
         description="Окно блокировки повторного идентичного запроса"),
    dict(key="free_tier_credit_cap", value="100", type="int",
         description="Максимум бесплатных кредитов для непокупавших пользователей"),
```

Создать `alembic/versions/f7a8b9c0d1e2_phase5_antifraud_settings.py` целиком:

```python
"""phase5: seed 5 antifraud settings rows (daily spend limit, per-user and
per-model rate limits, duplicate cooldown, free tier cap). No schema changes:
rate-limit / daily-spend / dedup counters live in Redis; the free-tier cap
reuses existing users columns (total_credits_purchased / total_credits_spent).

Deploy order (entrypoint.sh): `alembic upgrade head` runs BEFORE
`python -m app.db.seed`, and the seed only inserts missing keys, so this
bulk_insert cannot hit a duplicate-key conflict.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_settings_table = sa.table(
    'settings',
    sa.column('key', sa.String),
    sa.column('value', sa.String),
    sa.column('type', sa.String),
    sa.column('description', sa.String),
)

# Ровно те же 5 строк, что в app/db/seed.py (сид фазы 5).
_ANTIFRAUD_ROWS = [
    {"key": "daily_spend_limit_credits", "value": "10000", "type": "int",
     "description": "Дневной лимит трат на пользователя"},
    {"key": "rate_limit_per_user_per_minute", "value": "10", "type": "int",
     "description": "Rate limit запросов на пользователя"},
    {"key": "rate_limit_per_model_per_minute", "value": "60", "type": "int",
     "description": "Rate limit запросов на модель (глобально)"},
    {"key": "duplicate_cooldown_seconds", "value": "5", "type": "int",
     "description": "Окно блокировки повторного идентичного запроса"},
    {"key": "free_tier_credit_cap", "value": "100", "type": "int",
     "description": "Максимум бесплатных кредитов для непокупавших пользователей"},
]


def upgrade() -> None:
    op.bulk_insert(_settings_table, _ANTIFRAUD_ROWS)


def downgrade() -> None:
    for row in _ANTIFRAUD_ROWS:
        op.execute(
            sa.text("DELETE FROM settings WHERE key = :key").bindparams(key=row["key"])
        )
```

- [ ] **Step 4: Убедиться, что тесты и цепочка ревизий в порядке**

Run: `python -m pytest tests/db/test_seed_catalog.py -v`
Expected: PASS.

Run: `python -m alembic heads`
Expected: единственный head — `f7a8b9c0d1e2 (head)`.

- [ ] **Step 5: Commit**

```bash
git add app/db/seed.py alembic/versions/f7a8b9c0d1e2_phase5_antifraud_settings.py tests/db/test_seed_catalog.py
git commit -m "feat(db): сиды и миграция антифрод-настроек (5 строк settings)"
```

---

### Task 11: Regression — `import app.main` проходит + полный прогон тестов

**Files:**
- Modify: `tests/api/test_chat_routes.py:36`, `tests/api/test_generate_routes.py:34-35`, `tests/api/test_payments_routes.py:22-23` (только устаревшие комментарии)

**Interfaces:**
- Consumes: результаты всех предыдущих задач (после Task 9 в `app/` не остаётся модулей, импортирующих удалённые модели).
- Produces: подтверждённый критерий готовности фазы из спеки.

- [ ] **Step 1: Прогнать regression-импорт**

Run (Git Bash):

```bash
BOT_TOKEN="123456:TEST-token" DATABASE_URL="postgresql+asyncpg://test" python -c "import app.main; print('app.main import OK')"
```

Expected: вывод `app.main import OK`, exit code 0. Если падает — чинить причину (это и есть смысл задачи), а не тест.

- [ ] **Step 2: Обновить устаревшие комментарии в тестах**

Комментарии «app.main пока неимпортируем (… чинятся в фазах 3-5)» стали ложными. Заменить:

В `tests/api/test_chat_routes.py` строку:

```python
# app.main пока неимпортируем (admin/generate/payments чинятся в фазах 3-5),
# поэтому собираем минимальное приложение из тестируемых роутеров.
```

на:

```python
# Минимальное приложение из тестируемых роутеров: изолирует тест от
# lifespan/бота/вебхуков app.main (сам app.main импортируем с фазы 5).
```

В `tests/api/test_generate_routes.py` строки:

```python
# app.main пока неимпортируем (admin/key_healthcheck чинятся в фазах 4-5),
# поэтому собираем минимальное приложение из тестируемых роутеров.
```

на:

```python
# Минимальное приложение из тестируемых роутеров: изолирует тест от
# lifespan/бота/вебхуков app.main (сам app.main импортируем с фазы 5).
```

В `tests/api/test_payments_routes.py` строки:

```python
# app.main не импортируем (admin чинится в фазе 5) -- минимальное приложение
# из тестируемого роутера, как в tests/api/test_generate_routes.py.
```

на:

```python
# Минимальное приложение из тестируемого роутера, как в
# tests/api/test_generate_routes.py (сам app.main импортируем с фазы 5).
```

- [ ] **Step 3: Полный прогон всех тестов**

Run: `python -m pytest -q`
Expected: все тесты PASS; два Postgres-теста skipped (без `TEST_DATABASE_URL`) — норма.

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_chat_routes.py tests/api/test_generate_routes.py tests/api/test_payments_routes.py
git commit -m "chore: regression фазы 5 -- import app.main проходит, комментарии актуализированы"
```

---

## Self-Review (выполнено при написании плана)

**Spec coverage:**
- Рерайт 4 файлов: `admin.py` (T9), `admin_service.py` (T9, удаление — обоснование в задаче), `stats_service.py` (T7), `key_healthcheck.py` (T8) ✓
- `antifraud_service.py`: все 5 исключений, `AntifraudSettings`, `load_antifraud_settings`, 6 функций, Redis-ключи и TTL по таблице спеки (T1) ✓
- Разделение семантики rate-limit (INCR = check+record) vs daily-spend (GET-only check + отдельный record после reserve) (T1, тест `test_check_daily_limit_is_read_only`) ✓
- Порядок интеграции 1-4 из спеки в оба generation-сервиса (T4, T5), включая декремент на release/refund во всех местах, где вызываются `settle_request`/`refund_request` (text: settle-diff + provider-error; media: submit-fail, webhook no-url, webhook ERROR, reconcile) ✓
- Маппинг исключений 429/403/402 с точными текстами (T6) ✓
- `credit_service.adjust_credits_admin` (T3), `settings_service.set_setting` (T2) ✓
- Admin-дерево: stats / users(+query) / transactions(+limit,offset) / block,unblock / credits(+/-) / payments+refund (без изменений) / models PATCH (все 8 полей из спеки) / packages / settings GET+PATCH / banners (без изменений) (T9) ✓
- 5 settings-сидов + миграция `down_revision='e6f7a8b9c0d1'` без изменения схемы (T10) ✓
- Тестирование по спеке: test_antifraud_service (T1), FakeRedis get/incr/incrby/expire/decrby в обоих generation-тестах + test_generate_routes (T4/T5), тесты rate-limit/duplicate/free-tier gate/cap/daily-limit/декремент (T4/T5), tests/api/test_admin.py (T9), adjust_credits_admin-тесты (T3), regression `import app.main` (T11) ✓

**Placeholder scan:** плейсхолдеров ("TBD", "добавить обработку ошибок", шагов без кода) нет; каждый код-шаг содержит полный код.

**Type consistency:** имена и сигнатуры сверены между задачами: `AntifraudSettings`/guard-функции (T1 ⇄ T4/T5), исключения (T1 ⇄ T6), `set_setting(session, key, value, *, type_, description)` (T2 ⇄ T9), `adjust_credits_admin(session, user_id, delta, *, reason)` (T3 ⇄ T9), `MonthlyStats.credits_purchases_count` (T7 ⇄ T9 `month_credits_purchases_count`), `FakeRedis` идентичен во всех тестовых файлах.

**Отклонения от буквы спеки (оба — вынужденные, зафиксированы в задачах):**
1. `check_duplicate_request` вызывается с `if not confirm:` (T4/T5): без этого подтверждение дорогого запроса (повтор с `confirm=True` внутри 5-секундного окна после 409) блокировалось бы дедупом. Сама функция — ровно по спеке.
2. Опечатка спеки «Дневной лимit трат…» — в коде «Дневной лимит трат…».
