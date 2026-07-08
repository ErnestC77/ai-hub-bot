# Credit System v2 — Phase 1: Foundation (DB + Credit Engine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tariff/subscription/ModelConfig schema with the new credit-ledger foundation: stored `users.credits_balance`, immutable `credit_transactions` audit log, new `ai_models`/`credit_packages`/`settings` tables, pure pricing functions, and a row-locked credit engine (`reserve/settle/refund/grant`).

**Architecture:** One Alembic migration performs the full cutover (alter `users`, data-migrate balances from the old ledger, drop 4 legacy tables, recreate `credit_transactions`/`ai_requests`, create 3 new tables, swap Postgres enum types). A new pure module `app/services/pricing.py` computes credits from provider prices; a rewritten `app/services/credit_service.py` is the ONLY code allowed to mutate `users.credits_balance`, always under `SELECT ... FOR UPDATE`. No provider integrations, no bot commands, no admin, no payments — those are phases 2–6.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async (typed `Mapped[...]` / `mapped_column` style), Alembic, asyncpg (Postgres), aiosqlite (unit tests), pytest + pytest-asyncio (`asyncio_mode = auto` in `pytest.ini`).

## Global Constraints

- **Spec ground truth:** `docs/superpowers/specs/2026-07-08-credit-system-phase1-foundation-design.md`. Full business ТЗ: `C:\Users\mccaq\Desktop\promt.md`. When in doubt, the spec wins.
- **Pricing constants (seed values, verbatim from spec):** `usd_to_rub_rate = 80`, `rub_per_credit = 0.10`, `provider_fee_multiplier = 1.15`, `margin_multiplier = 2.5`, `minimum_text_credits = 3`.
- **Hard floors (verbatim from spec/ТЗ):** image edit minimum **100** credits; video minimum **500** credits; text minimum `max(model.min_credits, minimum_text_credits)`.
- **Credit packages (verbatim from ТЗ):** START 1000/149₽ «Для знакомства с ботом», BASIC 5000/599₽ «Для обычного использования», PLUS 12000/1290₽ «Для активной работы с текстом и изображениями», PRO 30000/2990₽ «Для частой генерации изображений и видео», BUSINESS 70000/5990₽ «Для агентств и heavy users».
- **Credits are `int` everywhere** (columns `Integer`, function returns `int`). `CreditTransaction.amount` is **signed**: reserve/spend negative; purchase/refund/release positive.
- **`users.credits_balance` may ONLY be mutated inside `app/services/credit_service.py`**, always after locking the row with `SELECT ... FOR UPDATE`. `credit_transactions` is an append-only audit log with `balance_before`/`balance_after` snapshots.
- **No new pip dependencies.** Everything needed is already in `requirements.txt` (sqlalchemy, asyncpg, alembic, aiosqlite, pytest, pytest-asyncio).
- **Follow existing code style:** SQLAlchemy 2.0 typed models like `app/db/models/user.py`, per-test-file `session` fixture on `sqlite+aiosqlite://` like `tests/services/test_access_service.py`, Russian comments are the codebase convention and are fine.
- **Known accepted breakage (per approved phasing):** after Phase 1, legacy request-path modules have broken imports because the models/enums they use are deleted. They are rewritten in phases 2–4 and MUST NOT be modified in this plan. Only requirement: `pytest` collects and passes (obsolete tests that import those modules are deleted in Task 1). **Full inventory, confirmed by the Phase 1 final whole-branch review** (the list below is the complete set found by scanning the final tree, wider than originally estimated — phase 2 planning should treat this as the checklist of modules to un-break, not just the originally-named subset):
  - `app/services/generation_service.py`, `app/services/access_service.py`, `app/services/cost_service.py`
  - `app/api/routes/*`, `app/worker.py`, `app/main.py`
  - `app/services/ai/ai_router.py`, `app/services/ai/base.py`, `app/services/ai/deepseek_service.py`, `app/services/ai/claude_service.py`, `app/services/ai/image_service.py`, `app/services/ai/openai_service.py`, `app/services/ai/gemini_service.py` (all import `ModelConfig`)
  - `app/services/stats_service.py` (`Subscription`, `SubscriptionStatus`)
  - `app/services/admin_service.py` (`Subscription`, `Tariff`, `SubscriptionStatus`)
  - `app/services/keys/key_healthcheck.py` (`ModelConfig`)
  - `app/webhooks/yookassa.py`, `app/services/payments/gateway.py`, `app/services/payments/activation.py`, `app/services/payments/stars_service.py`, `app/services/payments/yookassa_service.py` (`Tariff`, `Subscription`, `UsageLimit`)
  - The app cannot boot end-to-end until phases 2–4 rewire these; this is expected — Phase 1 only had to keep `pytest` green.
- **Out of scope (do not build):** OpenRouterClient, FalClient, bot commands (`/balance`, `/buy`, `/models`), admin commands, PaymentProvider, anti-fraud (rate limits, idempotency keys, daily spend limit), `/admin_stats`.
- Commit after every task; conventional-commit style messages (`feat:`, `test:`, `chore:`).

---

## File Structure Map

| File | Action | Responsibility |
|---|---|---|
| `app/db/enums.py` | Rewrite | New `ModelProvider(openrouter/fal)`, `ModelCategory(text/image/video)`, `ModelTier`, `CostUnit`, `RequestStatus(pending..refunded)`, `CreditTxType(purchase..admin_adjustment)`; keep `PaymentProvider`, `PaymentStatus`; drop `SubscriptionStatus` |
| `app/db/models/ai_models.py` | Create | `AiModel` — model catalog (replaces `ModelConfig`) |
| `app/db/models/credit_packages.py` | Create | `CreditPackage` DB model (replaces `app/services/credit_packages.py` dataclass) |
| `app/db/models/settings.py` | Create | `Setting` — key/value business knobs (NOT `app/config.py` env `Settings` — that stays untouched) |
| `app/db/models/user.py` | Modify | `+credits_balance`, `+total_credits_purchased`, `+total_credits_spent`, `active_model` → `default_model_code` |
| `app/db/models/credit_transaction.py` | Rewrite | Signed ledger with balance snapshots, provider/model/request links, `metadata_json` |
| `app/db/models/ai_request.py` | Rewrite | Billing-oriented request row (`prompt_preview`, reserve/charge columns, `insufficient_balance_after_usage`) |
| `app/db/models/payment.py` | Modify (minimal) | Drop the `ForeignKey("tariffs.id")` from `tariff_id` (tariffs table is deleted); column stays until phase 4 |
| `app/db/models/model_config.py`, `tariff.py`, `subscription.py`, `usage_limit.py` | Delete | Replaced/removed per spec |
| `app/db/models/__init__.py` | Modify | Export new set of models |
| `app/services/subscription_service.py`, `limit_service.py`, `limit_fields.py`, `credit_packages.py` | Delete | Removed per spec |
| `alembic/versions/b2c3d4e5f6a7_phase1_credit_system_v2.py` | Create | The single cutover migration |
| `app/services/pricing.py` | Create | Pure functions `calculate_text_credits`, `calculate_image_credits`, `calculate_video_credits` + `PricingSettings` dataclass |
| `app/services/settings_service.py` | Create | `get_setting(session, key, *, cast, default)` + `load_pricing_settings(session)` |
| `app/services/credit_service.py` | Rewrite | `reserve_credits`, `settle_request`, `refund_request`, `grant_credits`, `InsufficientBalanceError` |
| `app/db/seed.py` | Rewrite | 5 settings, 5 packages, 20 ai_models, banners kept as-is |
| `tests/db/test_credit_schema_v2.py` | Create | Round-trip test for the new model layer |
| `tests/services/test_pricing.py` | Create | All pricing formulas + edge cases |
| `tests/services/test_settings_service.py` | Create | `get_setting` / `load_pricing_settings` |
| `tests/services/test_credit_service.py` | Create | Engine unit tests (sqlite) + concurrent-reserve integration test (real Postgres) |
| `tests/db/test_seed_catalog.py` | Create | Seed catalog assertions + idempotency |
| `tests/services/test_access_service.py`, `tests/services/test_generation_service.py`, `tests/api/test_generate_routes.py`, `tests/db/test_piapi_schema.py`, `tests/db/test_seed_piapi_catalog.py` | Delete | They import deleted models/services (`Tariff`, `ModelConfig`, `generation_service`, `app.main`, old seed) and cannot collect after the cutover |

---

### Task 1: Schema layer cutover — new enums and models, delete legacy files

**Files:**
- Modify: `app/db/enums.py` (full rewrite; currently 54 lines, keep only `PaymentProvider` lines 10–15 and `PaymentStatus` lines 17–23 unchanged)
- Create: `app/db/models/ai_models.py`, `app/db/models/credit_packages.py`, `app/db/models/settings.py`
- Modify: `app/db/models/user.py` (line 15 `active_model` renamed + 3 new columns), `app/db/models/credit_transaction.py` (full rewrite), `app/db/models/ai_request.py` (full rewrite), `app/db/models/payment.py` (line 21: `tariff_id` loses its FK), `app/db/models/__init__.py`
- Delete: `app/db/models/model_config.py`, `app/db/models/tariff.py`, `app/db/models/subscription.py`, `app/db/models/usage_limit.py`, `app/services/subscription_service.py`, `app/services/limit_service.py`, `app/services/limit_fields.py`, `app/services/credit_packages.py`
- Delete (obsolete tests that import deleted code): `tests/services/test_access_service.py`, `tests/services/test_generation_service.py`, `tests/api/test_generate_routes.py`, `tests/db/test_piapi_schema.py`, `tests/db/test_seed_piapi_catalog.py`
- Test: `tests/db/test_credit_schema_v2.py`

**Interfaces:**
- Consumes: `Base`, `TimestampMixin` from `app/db/base.py` (unchanged).
- Produces (all later tasks rely on these exact names):
  - Enums in `app.db.enums`: `ModelProvider(openrouter, fal)`, `ModelCategory(text, image, video)`, `ModelTier(economy, standard, premium, pro, ultra)`, `CostUnit(tokens, image, megapixel, second, video)`, `RequestStatus(pending, reserved, processing, completed, failed, refunded)`, `CreditTxType(purchase, spend, refund, reserve, release, admin_adjustment)`.
  - Models in `app.db.models`: `AiModel` (table `ai_models`), `CreditPackage` (table `credit_packages`), `Setting` (table `settings`), plus updated `User`, `CreditTransaction`, `AIRequest`; `Banner`, `Payment`, `Referral` untouched in behavior.
  - `User` fields: `credits_balance: int`, `total_credits_purchased: int`, `total_credits_spent: int`, `default_model_code: str | None`.
  - `AIRequest` fields: `provider: str`, `model_code: str`, `category: ModelCategory`, `status: RequestStatus`, `prompt_preview: str`, `input_tokens/output_tokens: int`, `estimated_credits/reserved_credits/charged_credits: int`, `provider_cost_usd`, `provider_response_id: str | None`, `error_message: str | None`, `insufficient_balance_after_usage: bool`, `created_at`, `completed_at: datetime | None`.
  - `CreditTransaction` fields: `type: CreditTxType`, `amount: int` (signed), `balance_before: int`, `balance_after: int`, `provider: str | None`, `model_code: str | None`, `request_id: int | None`, `description: str | None`, `metadata_json: dict | None`, `created_at`.

- [ ] **Step 1: Write the failing schema round-trip test**

Create `tests/db/test_credit_schema_v2.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import (
    CostUnit,
    CreditTxType,
    ModelCategory,
    ModelProvider,
    ModelTier,
    RequestStatus,
)
from app.db.models import AiModel, AIRequest, CreditPackage, CreditTransaction, Setting, User


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_user_new_credit_columns_default_to_zero(session):
    user = User(telegram_id=1, username="u", default_model_code=None)
    session.add(user)
    await session.commit()

    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 0
    assert fetched.total_credits_purchased == 0
    assert fetched.total_credits_spent == 0
    assert fetched.default_model_code is None
    assert not hasattr(fetched, "active_model")


async def test_ai_model_round_trip(session):
    model = AiModel(
        provider=ModelProvider.openrouter,
        category=ModelCategory.text,
        code="deepseek_v3",
        display_name="DeepSeek V3",
        provider_model_id="deepseek/deepseek-chat",
        tier=ModelTier.economy,
        input_price_usd_per_1m_tokens=0.27,
        output_price_usd_per_1m_tokens=1.10,
        fixed_cost_usd=0,
        cost_unit=CostUnit.tokens,
        min_credits=3,
        recommended_credits=3,
        max_context_tokens=128000,
        is_active=True,
        is_visible=True,
        sort_order=10,
    )
    session.add(model)
    await session.commit()

    fetched = await session.get(AiModel, model.id)
    assert fetched.code == "deepseek_v3"
    assert fetched.tier == ModelTier.economy
    assert fetched.cost_unit == CostUnit.tokens
    assert float(fetched.input_price_usd_per_1m_tokens) == 0.27


async def test_credit_package_round_trip(session):
    pkg = CreditPackage(code="start", title="START", credits=1000, price_rub=149, description="Для знакомства с ботом")
    session.add(pkg)
    await session.commit()

    fetched = await session.get(CreditPackage, pkg.id)
    assert fetched.credits == 1000
    assert fetched.is_active is True


async def test_setting_round_trip(session):
    session.add(Setting(key="usd_to_rub_rate", value="80", type="float", description="Курс USD→RUB"))
    await session.commit()

    fetched = await session.get(Setting, "usd_to_rub_rate")
    assert fetched.value == "80"
    assert fetched.type == "float"


async def test_ai_request_and_transaction_round_trip(session):
    user = User(telegram_id=2)
    session.add(user)
    await session.flush()

    request = AIRequest(
        user_id=user.id,
        provider="openrouter",
        model_code="deepseek_v3",
        category=ModelCategory.text,
        status=RequestStatus.reserved,
        prompt_preview="напиши хокку про кредиты"[:200],
        estimated_credits=10,
        reserved_credits=10,
    )
    session.add(request)
    await session.flush()

    tx = CreditTransaction(
        user_id=user.id,
        type=CreditTxType.reserve,
        amount=-10,
        balance_before=100,
        balance_after=90,
        provider="openrouter",
        model_code="deepseek_v3",
        request_id=request.id,
        description="reserve for request",
        metadata_json={"input_tokens": 2000, "output_tokens": 1000},
    )
    session.add(tx)
    await session.commit()

    fetched_req = await session.get(AIRequest, request.id)
    assert fetched_req.status == RequestStatus.reserved
    assert fetched_req.insufficient_balance_after_usage is False
    assert fetched_req.charged_credits == 0
    assert fetched_req.completed_at is None

    fetched_tx = await session.get(CreditTransaction, tx.id)
    assert fetched_tx.amount == -10
    assert fetched_tx.balance_before == 100
    assert fetched_tx.balance_after == 90
    assert fetched_tx.request_id == request.id
    assert fetched_tx.metadata_json == {"input_tokens": 2000, "output_tokens": 1000}


async def test_legacy_models_are_gone():
    import app.db.models as models

    for legacy in ("ModelConfig", "Tariff", "Subscription", "UsageLimit"):
        assert not hasattr(models, legacy)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/db/test_credit_schema_v2.py -v`
Expected: FAIL at import time — `ImportError: cannot import name 'AiModel' from 'app.db.models'` (and `CostUnit`/`ModelTier` missing from `app.db.enums`).

- [ ] **Step 3: Rewrite `app/db/enums.py`**

Replace the entire file with:

```python
import enum


class PaymentProvider(str, enum.Enum):
    telegram_stars = "telegram_stars"
    yookassa = "yookassa"
    manual = "manual"
    promo = "promo"


class PaymentStatus(str, enum.Enum):
    created = "created"
    pending = "pending"
    succeeded = "succeeded"
    canceled = "canceled"
    refunded = "refunded"
    failed = "failed"


class ModelProvider(str, enum.Enum):
    openrouter = "openrouter"
    fal = "fal"


class ModelCategory(str, enum.Enum):
    text = "text"
    image = "image"
    video = "video"


class ModelTier(str, enum.Enum):
    economy = "economy"
    standard = "standard"
    premium = "premium"
    pro = "pro"
    ultra = "ultra"


class CostUnit(str, enum.Enum):
    tokens = "tokens"
    image = "image"
    megapixel = "megapixel"
    second = "second"
    video = "video"


class RequestStatus(str, enum.Enum):
    pending = "pending"
    reserved = "reserved"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


class CreditTxType(str, enum.Enum):
    purchase = "purchase"
    spend = "spend"
    refund = "refund"
    reserve = "reserve"
    release = "release"
    admin_adjustment = "admin_adjustment"
```

(`SubscriptionStatus` is deleted; old `ModelCategory.fast/medium/premium`, old `ModelProvider.openai/...`, old `CreditTxType.deposit/...`, old `RequestStatus.processing/success/error` value sets are replaced.)

- [ ] **Step 4: Create the three new model files**

Create `app/db/models/ai_models.py`:

```python
from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier


class AiModel(Base, TimestampMixin):
    """Каталог AI-моделей (замена ModelConfig). Все цены/кредиты редактируются
    через будущую админку (фаза 5) -- бизнес-логика не привязана к конкретной модели."""

    __tablename__ = "ai_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[ModelProvider] = mapped_column()
    category: Mapped[ModelCategory] = mapped_column()
    code: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    provider_model_id: Mapped[str] = mapped_column(String(128))
    tier: Mapped[ModelTier] = mapped_column()

    input_price_usd_per_1m_tokens: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    output_price_usd_per_1m_tokens: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    fixed_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    cost_unit: Mapped[CostUnit] = mapped_column()

    min_credits: Mapped[int] = mapped_column(Integer, default=0)
    recommended_credits: Mapped[int] = mapped_column(Integer, default=0)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=8000)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
```

Create `app/db/models/credit_packages.py`:

```python
from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CreditPackage(Base, TimestampMixin):
    """Пакеты кредитов (замена dataclass-списка app/services/credit_packages.py).
    Использование в оплате -- фаза 4; здесь только таблица + сиды."""

    __tablename__ = "credit_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(64))
    credits: Mapped[int] = mapped_column(Integer)
    price_rub: Mapped[float] = mapped_column(Numeric(10, 2))
    description: Mapped[str | None] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

Create `app/db/models/settings.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Setting(Base):
    """Бизнес-настройки (курс, маржа, цена кредита), редактируемые через будущую
    админку (фаза 5). НЕ путать с app.config.Settings -- те читают .env (API-ключи)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(8))  # int / float / str / bool
    description: Mapped[str | None] = mapped_column(String(256))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 5: Update `user.py`, rewrite `credit_transaction.py` and `ai_request.py`, adjust `payment.py`**

Replace `app/db/models/user.py` with:

```python
from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(8))
    default_model_code: Mapped[str | None] = mapped_column(String(64))

    # Хранимый баланс -- единственный источник истины для balance >= amount.
    # Обновляется ТОЛЬКО функциями app/services/credit_service.py под SELECT ... FOR UPDATE.
    credits_balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_credits_purchased: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_credits_spent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
```

Replace `app/db/models/credit_transaction.py` with:

```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import CreditTxType


class CreditTransaction(Base):
    """Неизменяемый аудит-лог кредитов. amount -- ПОДПИСАННОЕ значение:
    reserve/spend -- отрицательные; purchase/refund/release -- положительные.
    Строки создаются только внутри app/services/credit_service.py."""

    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    type: Mapped[CreditTxType] = mapped_column()
    amount: Mapped[int] = mapped_column(Integer)
    balance_before: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)

    provider: Mapped[str | None] = mapped_column(String(32))  # "openrouter" / "fal" / None
    model_code: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("ai_requests.id"))
    description: Mapped[str | None] = mapped_column(String(256))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Replace `app/db/models/ai_request.py` with:

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import ModelCategory, RequestStatus


class AIRequest(Base):
    """Биллинговая запись AI-запроса. Полные prompt/answer не хранятся --
    только prompt_preview (обрезка до 200 символов)."""

    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    provider: Mapped[str] = mapped_column(String(32))  # "openrouter" / "fal"
    model_code: Mapped[str] = mapped_column(String(64))
    category: Mapped[ModelCategory] = mapped_column()
    status: Mapped[RequestStatus] = mapped_column(default=RequestStatus.pending)

    prompt_preview: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    estimated_credits: Mapped[int] = mapped_column(Integer, default=0)
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0)
    charged_credits: Mapped[int] = mapped_column(Integer, default=0)
    provider_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)

    provider_response_id: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    # actual > reserved и баланса на доплату не хватило -- см. credit_service.settle_request.
    insufficient_balance_after_usage: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

In `app/db/models/payment.py` replace line 21:

```python
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"))
```

with:

```python
    # Легаси-колонка: таблица tariffs удалена в фазе 1 (кредитная система v2),
    # FK снят миграцией. Колонка и весь платёжный флоу переписываются в фазе 4.
    tariff_id: Mapped[int | None] = mapped_column(Integer)
```

`Integer` is not currently imported in `payment.py` — update its `sqlalchemy` import (line 3) to: `from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint`.

Replace `app/db/models/__init__.py` with:

```python
from app.db.models.ai_models import AiModel
from app.db.models.ai_request import AIRequest
from app.db.models.banner import Banner
from app.db.models.credit_packages import CreditPackage
from app.db.models.credit_transaction import CreditTransaction
from app.db.models.payment import Payment
from app.db.models.referral import Referral
from app.db.models.settings import Setting
from app.db.models.user import User

__all__ = [
    "AiModel",
    "AIRequest",
    "Banner",
    "CreditPackage",
    "CreditTransaction",
    "Payment",
    "Referral",
    "Setting",
    "User",
]
```

- [ ] **Step 6: Delete the legacy model/service files and obsolete tests**

```bash
git rm app/db/models/model_config.py app/db/models/tariff.py app/db/models/subscription.py app/db/models/usage_limit.py
git rm app/services/subscription_service.py app/services/limit_service.py app/services/limit_fields.py app/services/credit_packages.py
git rm tests/services/test_access_service.py tests/services/test_generation_service.py tests/api/test_generate_routes.py tests/db/test_piapi_schema.py tests/db/test_seed_piapi_catalog.py
```

Rationale for the test deletions: each of these imports code that no longer exists after this task (`Tariff`, `UsageLimit`, `ModelConfig`, old `CreditTxType.deposit`, `app.main` → `generation_service` → `limit_service`, old `seed.MODEL_CONFIGS`), so pytest collection itself would fail. They test features that are deleted (tariffs/limits) or rewritten in phases 2–3 (generation flow, PiAPI catalog).

- [ ] **Step 7: Run the new test to verify it passes**

Run: `python -m pytest tests/db/test_credit_schema_v2.py -v`
Expected: PASS (6 tests).

- [ ] **Step 8: Run the whole suite to verify collection is clean**

Run: `python -m pytest tests/ -v`
Expected: PASS. Remaining tests are `tests/db/test_credit_schema_v2.py`, `tests/services/ai/test_piapi_client.py`, `tests/services/keys/test_piapi_key.py` (the last two do not import DB models — verified). NOTE: `app/db/seed.py` still references deleted `ModelConfig`/`Tariff` after this task; nothing imports it from tests until Task 7 rewrites it — do not fix it here.

- [ ] **Step 9: Commit**

```bash
git add app/db/enums.py app/db/models/ tests/db/test_credit_schema_v2.py
git commit -m "feat: credit system v2 schema layer - new enums/models, drop tariffs/subscriptions/limits/model_configs"
```

---

### Task 2: Alembic cutover migration `phase1_credit_system_v2`

**Files:**
- Create: `alembic/versions/b2c3d4e5f6a7_phase1_credit_system_v2.py`

**Interfaces:**
- Consumes: current head revision `a1f2c3d4e5f6` (see `alembic/versions/a1f2c3d4e5f6_add_piapi_schema.py:14`); the Task 1 model metadata (migration DDL must match it exactly so `alembic` and `Base.metadata.create_all` agree).
- Produces: DB schema for all later tasks and for production deploy. Postgres enum type names: `modelprovider`, `modelcategory`, `modeltier`, `costunit`, `credittxtype`, `requeststatus` (old types with colliding names are dropped first).

- [ ] **Step 1: Write the migration**

Create `alembic/versions/b2c3d4e5f6a7_phase1_credit_system_v2.py`. Style follows the project's existing hand-adjusted migrations (see `alembic/versions/a1f2c3d4e5f6_add_piapi_schema.py`):

```python
"""phase1 credit system v2: users balance columns + rename, data-migrate balances,
drop tariffs/subscriptions/usage_limits/model_configs, recreate credit_transactions
and ai_requests, create ai_models/credit_packages/settings, swap enum types.

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1f2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(*values: str, name: str) -> postgresql.ENUM:
    # create_type=False: типы создаются явно ниже, чтобы один тип (modelcategory)
    # можно было использовать в двух таблицах без повторного CREATE TYPE.
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    # --- 1. users: новые колонки + rename active_model -> default_model_code ---
    op.add_column('users', sa.Column('credits_balance', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('total_credits_purchased', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('total_credits_spent', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('users', 'active_model', new_column_name='default_model_code')

    # --- 2. data migration: перенести балансы из старого леджера ДО его дропа ---
    # (проект не запущен в платном режиме, но шаг делается безусловно -- на dev/staging
    # могут быть тестовые данные). Старый amount -- Numeric(10,2), баланс -- int.
    op.execute(
        """
        UPDATE users SET credits_balance = COALESCE(
            (SELECT CAST(SUM(ct.amount) AS INTEGER)
             FROM credit_transactions ct
             WHERE ct.user_id = users.id),
            0
        )
        """
    )

    # --- 3. payments.tariff_id: тарифы удаляются, FK снимается (колонка остаётся до фазы 4) ---
    op.drop_constraint('payments_tariff_id_fkey', 'payments', type_='foreignkey')

    # --- 4. drop старых таблиц (в порядке FK-зависимостей) ---
    op.drop_table('usage_limits')
    op.drop_table('subscriptions')
    op.drop_table('credit_transactions')
    op.drop_table('ai_requests')
    op.drop_table('tariffs')
    op.drop_table('model_configs')

    # --- 5. drop старых enum-типов (имена переиспользуются новыми наборами значений) ---
    for type_name in ('subscriptionstatus', 'modelcategory', 'modelprovider', 'credittxtype', 'requeststatus'):
        op.execute(f'DROP TYPE IF EXISTS {type_name}')

    # --- 6. новые enum-типы ---
    op.execute("CREATE TYPE modelprovider AS ENUM ('openrouter', 'fal')")
    op.execute("CREATE TYPE modelcategory AS ENUM ('text', 'image', 'video')")
    op.execute("CREATE TYPE modeltier AS ENUM ('economy', 'standard', 'premium', 'pro', 'ultra')")
    op.execute("CREATE TYPE costunit AS ENUM ('tokens', 'image', 'megapixel', 'second', 'video')")
    op.execute(
        "CREATE TYPE credittxtype AS ENUM "
        "('purchase', 'spend', 'refund', 'reserve', 'release', 'admin_adjustment')"
    )
    op.execute(
        "CREATE TYPE requeststatus AS ENUM "
        "('pending', 'reserved', 'processing', 'completed', 'failed', 'refunded')"
    )

    # --- 7. новые таблицы ---
    op.create_table(
        'ai_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', _enum('openrouter', 'fal', name='modelprovider'), nullable=False),
        sa.Column('category', _enum('text', 'image', 'video', name='modelcategory'), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=False),
        sa.Column('provider_model_id', sa.String(length=128), nullable=False),
        sa.Column('tier', _enum('economy', 'standard', 'premium', 'pro', 'ultra', name='modeltier'), nullable=False),
        sa.Column('input_price_usd_per_1m_tokens', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0'),
        sa.Column('output_price_usd_per_1m_tokens', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0'),
        sa.Column('fixed_cost_usd', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0'),
        sa.Column('cost_unit', _enum('tokens', 'image', 'megapixel', 'second', 'video', name='costunit'), nullable=False),
        sa.Column('min_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recommended_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_context_tokens', sa.Integer(), nullable=False, server_default='8000'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_visible', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'credit_packages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=64), nullable=False),
        sa.Column('credits', sa.Integer(), nullable=False),
        sa.Column('price_rub', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.String(length=128), nullable=False),
        sa.Column('type', sa.String(length=8), nullable=False),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    # ai_requests -- ДО credit_transactions (на него ссылается request_id).
    op.create_table(
        'ai_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model_code', sa.String(length=64), nullable=False),
        sa.Column('category', _enum('text', 'image', 'video', name='modelcategory'), nullable=False),
        sa.Column(
            'status',
            _enum('pending', 'reserved', 'processing', 'completed', 'failed', 'refunded', name='requeststatus'),
            nullable=False,
        ),
        sa.Column('prompt_preview', sa.String(length=200), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reserved_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('charged_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('provider_cost_usd', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0'),
        sa.Column('provider_response_id', sa.String(length=128), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('insufficient_balance_after_usage', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_requests_user_id'), 'ai_requests', ['user_id'], unique=False)
    op.create_table(
        'credit_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column(
            'type',
            _enum('purchase', 'spend', 'refund', 'reserve', 'release', 'admin_adjustment', name='credittxtype'),
            nullable=False,
        ),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('balance_before', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('model_code', sa.String(length=64), nullable=True),
        sa.Column('request_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['request_id'], ['ai_requests.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_credit_transactions_user_id'), 'credit_transactions', ['user_id'], unique=False)


def downgrade() -> None:
    # Cutover-миграция уничтожает данные старых таблиц (tariffs/subscriptions/
    # usage_limits/model_configs и старый леджер) -- честного отката не существует.
    raise NotImplementedError(
        "phase1_credit_system_v2 is a destructive cutover migration and cannot be downgraded; "
        "restore from a DB backup instead"
    )
```

- [ ] **Step 2: Verify the migration renders as SQL (offline mode, no DB needed)**

Run: `alembic upgrade a1f2c3d4e5f6:b2c3d4e5f6a7 --sql`
Expected: full SQL script printed without Python errors; it must contain (in this order): `ALTER TABLE users ADD COLUMN credits_balance`, the `UPDATE users SET credits_balance = COALESCE(...)` statement, `DROP TABLE usage_limits`, `DROP TYPE IF EXISTS modelcategory`, `CREATE TYPE modelcategory AS ENUM ('text', 'image', 'video')`, `CREATE TABLE ai_models`, `CREATE TABLE ai_requests`, `CREATE TABLE credit_transactions`.

- [ ] **Step 3: Apply against a real Postgres if one is reachable (dev/staging DATABASE_URL)**

Run: `alembic upgrade head`
Expected: `Running upgrade a1f2c3d4e5f6 -> b2c3d4e5f6a7`. Then verify: `alembic current` shows `b2c3d4e5f6a7 (head)`. If no local Postgres is available, the offline render in Step 2 plus the real-Postgres test in Task 6 (which builds the same schema from `Base.metadata`) are the verification; note it in the task report.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/b2c3d4e5f6a7_phase1_credit_system_v2.py
git commit -m "feat: alembic cutover migration phase1_credit_system_v2"
```

---

### Task 3: Pricing functions — `app/services/pricing.py`

**Files:**
- Create: `app/services/pricing.py`
- Test: `tests/services/test_pricing.py`

**Interfaces:**
- Consumes: `AiModel` (fields `input_price_usd_per_1m_tokens`, `output_price_usd_per_1m_tokens`, `cost_unit`, `min_credits`, `recommended_credits`, `code`), `CostUnit` enum — from Task 1. `AiModel` instances are used detached (no DB needed).
- Produces (used by Task 4 and by phases 2–3):
  - `@dataclass(frozen=True) class PricingSettings` with fields `usd_to_rub_rate: float = 80.0`, `rub_per_credit: float = 0.10`, `provider_fee_multiplier: float = 1.15`, `margin_multiplier: float = 2.5`, `minimum_text_credits: int = 3`.
  - `def calculate_text_credits(model: AiModel, input_tokens: int, output_tokens: int, *, settings: PricingSettings) -> int`
  - `def calculate_image_credits(model: AiModel, quantity: int, megapixels: float, *, is_edit: bool = False) -> int`
  - `def calculate_video_credits(model: AiModel, duration_seconds: int) -> int`
  - Constants `IMAGE_EDIT_MULTIPLIER = 1.5`, `IMAGE_EDIT_MIN_CREDITS = 100`, `VIDEO_MIN_CREDITS = 500`, `VIDEO_BASE_SECONDS = 5`.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_pricing.py`:

```python
import pytest

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.pricing import (
    PricingSettings,
    calculate_image_credits,
    calculate_text_credits,
    calculate_video_credits,
)

SETTINGS = PricingSettings()  # дефолты = стартовые settings из ТЗ


def _text_model(input_price: float, output_price: float, min_credits: int) -> AiModel:
    return AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text, code="m",
        display_name="M", provider_model_id="x/m", tier=ModelTier.standard,
        input_price_usd_per_1m_tokens=input_price, output_price_usd_per_1m_tokens=output_price,
        cost_unit=CostUnit.tokens, min_credits=min_credits, recommended_credits=min_credits,
    )


def _media_model(cost_unit: CostUnit, recommended: int, min_credits: int,
                 category: ModelCategory = ModelCategory.image) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=category, code="m",
        display_name="M", provider_model_id="fal-ai/m", tier=ModelTier.standard,
        input_price_usd_per_1m_tokens=0, output_price_usd_per_1m_tokens=0,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
    )


# --- calculate_text_credits: формула шагов 1-8 из ТЗ ---

def test_text_formula_steps_1_to_8():
    # apiCostUsd = 2000/1e6*3 + 1000/1e6*15 = 0.021; rub = 0.021*80 = 1.68;
    # gross = 1.68*1.15 = 1.932; user = 1.932*2.5 = 4.83; ceil(4.83/0.10) = 49.
    model = _text_model(input_price=3.0, output_price=15.0, min_credits=5)
    assert calculate_text_credits(model, 2000, 1000, settings=SETTINGS) == 49


def test_text_ceil_rounds_up():
    # apiCostUsd = 1043/1e6*10 = 0.01043; user = 0.01043*80*1.15*2.5 = 2.39890 rub;
    # /0.10 = 23.989 -> ceil = 24.
    model = _text_model(input_price=10.0, output_price=0.0, min_credits=1)
    assert calculate_text_credits(model, 1043, 0, settings=SETTINGS) == 24


def test_text_model_min_credits_floor():
    # Сырые credits = 1, но model.min_credits = 5 форсирует минимум.
    model = _text_model(input_price=0.1, output_price=0.0, min_credits=5)
    assert calculate_text_credits(model, 100, 0, settings=SETTINGS) == 5


def test_text_global_minimum_text_credits_floor():
    # Нулевая цена -> 0 кредитов, но глобальный minimum_text_credits = 3.
    model = _text_model(input_price=0.0, output_price=0.0, min_credits=1)
    assert calculate_text_credits(model, 500, 500, settings=SETTINGS) == 3


def test_text_uses_settings_overrides():
    model = _text_model(input_price=3.0, output_price=15.0, min_credits=5)
    doubled = PricingSettings(usd_to_rub_rate=160.0)
    # Тот же расчёт, но курс x2: 4.83*2 = 9.66 rub -> ceil(96.6) = 97.
    assert calculate_text_credits(model, 2000, 1000, settings=doubled) == 97


# --- calculate_image_credits ---

def test_image_cost_unit_image_multiplies_quantity():
    model = _media_model(CostUnit.image, recommended=75, min_credits=75)
    assert calculate_image_credits(model, quantity=2, megapixels=1.0) == 150


def test_image_cost_unit_megapixel_ceils():
    # 1 * 1.25 MP * 50 = 62.5 -> ceil = 63 (1.25 точно представимо в float).
    model = _media_model(CostUnit.megapixel, recommended=50, min_credits=50)
    assert calculate_image_credits(model, quantity=1, megapixels=1.25) == 63


def test_image_megapixel_respects_model_min_credits():
    # 1 * 0.5 MP * 50 = 25 < min_credits 50 -> 50.
    model = _media_model(CostUnit.megapixel, recommended=50, min_credits=50)
    assert calculate_image_credits(model, quantity=1, megapixels=0.5) == 50


def test_image_edit_multiplier_with_minimum_100():
    # base 50 -> x1.5 = 75 -> но минимум image edit = 100.
    model = _media_model(CostUnit.image, recommended=50, min_credits=50)
    assert calculate_image_credits(model, quantity=1, megapixels=1.0, is_edit=True) == 100


def test_image_edit_multiplier_above_minimum():
    # base 100 -> x1.5 = 150 > 100.
    model = _media_model(CostUnit.image, recommended=100, min_credits=100)
    assert calculate_image_credits(model, quantity=1, megapixels=1.0, is_edit=True) == 150


def test_image_rejects_non_image_cost_unit():
    model = _media_model(CostUnit.tokens, recommended=50, min_credits=50)
    with pytest.raises(ValueError):
        calculate_image_credits(model, quantity=1, megapixels=1.0)


# --- calculate_video_credits ---

def test_video_cost_unit_second_scales_by_duration():
    # ceil(7/5 * 600) = ceil(840.0) = 840.
    model = _media_model(CostUnit.second, recommended=600, min_credits=600, category=ModelCategory.video)
    assert calculate_video_credits(model, duration_seconds=7) == 840


def test_video_short_duration_floors_to_model_min():
    # ceil(3/5 * 600) = 360 < min_credits 600 -> 600.
    model = _media_model(CostUnit.second, recommended=600, min_credits=600, category=ModelCategory.video)
    assert calculate_video_credits(model, duration_seconds=3) == 600


def test_video_cost_unit_video_is_flat():
    model = _media_model(CostUnit.video, recommended=500, min_credits=500, category=ModelCategory.video)
    assert calculate_video_credits(model, duration_seconds=30) == 500


def test_video_global_minimum_500():
    # recommended 300, min_credits 0 -> глобальный минимум видео 500.
    model = _media_model(CostUnit.video, recommended=300, min_credits=0, category=ModelCategory.video)
    assert calculate_video_credits(model, duration_seconds=5) == 500


def test_video_rejects_non_video_cost_unit():
    model = _media_model(CostUnit.image, recommended=500, min_credits=500, category=ModelCategory.video)
    with pytest.raises(ValueError):
        calculate_video_credits(model, duration_seconds=5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_pricing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.pricing'`.

- [ ] **Step 3: Implement `app/services/pricing.py`**

```python
"""Чистые функции расчёта кредитов (формулы 1:1 из ТЗ). Никаких DB-записей --
настройки передаются снаружи (см. app/services/settings_service.py)."""

import math
from dataclasses import dataclass

from app.db.enums import CostUnit
from app.db.models import AiModel

IMAGE_EDIT_MULTIPLIER = 1.5
IMAGE_EDIT_MIN_CREDITS = 100
VIDEO_MIN_CREDITS = 500
VIDEO_BASE_SECONDS = 5  # recommended_credits видео-моделей заданы "за 5 секунд"


@dataclass(frozen=True)
class PricingSettings:
    """Снимок бизнес-настроек из таблицы settings. Дефолты = стартовый сид
    (защита от пустой БД до первого сида)."""

    usd_to_rub_rate: float = 80.0
    rub_per_credit: float = 0.10
    provider_fee_multiplier: float = 1.15
    margin_multiplier: float = 2.5
    minimum_text_credits: int = 3


def calculate_text_credits(
    model: AiModel, input_tokens: int, output_tokens: int, *, settings: PricingSettings
) -> int:
    # Шаги 1-8 из ТЗ.
    input_cost_usd = input_tokens / 1_000_000 * float(model.input_price_usd_per_1m_tokens)
    output_cost_usd = output_tokens / 1_000_000 * float(model.output_price_usd_per_1m_tokens)
    api_cost_usd = input_cost_usd + output_cost_usd
    api_cost_rub = api_cost_usd * settings.usd_to_rub_rate
    gross_cost_rub = api_cost_rub * settings.provider_fee_multiplier
    user_price_rub = gross_cost_rub * settings.margin_multiplier
    credits = math.ceil(user_price_rub / settings.rub_per_credit)
    return max(credits, model.min_credits, settings.minimum_text_credits)


def calculate_image_credits(
    model: AiModel, quantity: int, megapixels: float, *, is_edit: bool = False
) -> int:
    if model.cost_unit == CostUnit.image:
        credits = quantity * model.recommended_credits
    elif model.cost_unit == CostUnit.megapixel:
        credits = math.ceil(quantity * megapixels * model.recommended_credits)
    else:
        raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для image")
    credits = max(credits, model.min_credits)
    if is_edit:
        credits = max(math.ceil(credits * IMAGE_EDIT_MULTIPLIER), IMAGE_EDIT_MIN_CREDITS)
    return credits


def calculate_video_credits(model: AiModel, duration_seconds: int) -> int:
    if model.cost_unit == CostUnit.second:
        credits = math.ceil(duration_seconds / VIDEO_BASE_SECONDS * model.recommended_credits)
    elif model.cost_unit == CostUnit.video:
        credits = model.recommended_credits
    else:
        raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для video")
    return max(credits, model.min_credits, VIDEO_MIN_CREDITS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_pricing.py -v`
Expected: PASS (16 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/pricing.py tests/services/test_pricing.py
git commit -m "feat: pure credit pricing functions (text/image/video)"
```

---

### Task 4: Settings helper — `app/services/settings_service.py`

**Files:**
- Create: `app/services/settings_service.py`
- Test: `tests/services/test_settings_service.py`

**Interfaces:**
- Consumes: `Setting` model (Task 1); `PricingSettings` from `app.services.pricing` (Task 3).
- Produces (used by phases 2–5 and by seed-aware code):
  - `async def get_setting(session: AsyncSession, key: str, *, cast: Callable[[str], T] = str, default: T | None = None) -> T | None` — returns `cast(row.value)` or `default` when the row is missing (protection against an unseeded DB).
  - `async def load_pricing_settings(session: AsyncSession) -> PricingSettings` — reads the 5 pricing keys, falling back to `PricingSettings()` defaults per-key.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_settings_service.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.models import Setting
from app.services.pricing import PricingSettings
from app.services.settings_service import get_setting, load_pricing_settings


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_get_setting_returns_cast_value(session):
    session.add(Setting(key="usd_to_rub_rate", value="80", type="float"))
    await session.commit()

    value = await get_setting(session, "usd_to_rub_rate", cast=float)
    assert value == 80.0
    assert isinstance(value, float)


async def test_get_setting_missing_key_returns_default(session):
    assert await get_setting(session, "no_such_key", cast=int, default=42) == 42
    assert await get_setting(session, "no_such_key") is None


async def test_load_pricing_settings_empty_db_uses_defaults(session):
    assert await load_pricing_settings(session) == PricingSettings()


async def test_load_pricing_settings_reads_overrides(session):
    session.add(Setting(key="margin_multiplier", value="3.0", type="float"))
    session.add(Setting(key="minimum_text_credits", value="5", type="int"))
    await session.commit()

    loaded = await load_pricing_settings(session)
    assert loaded.margin_multiplier == 3.0
    assert loaded.minimum_text_credits == 5
    assert loaded.usd_to_rub_rate == 80.0  # остальные -- дефолты
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_settings_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.settings_service'`.

- [ ] **Step 3: Implement `app/services/settings_service.py`**

```python
"""Тонкий helper над таблицей settings (бизнес-настройки: курс, маржа, цена кредита).
НЕ путать с app.config.Settings (env/.env: API-ключи, DATABASE_URL и т.п.)."""

from typing import Callable, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting
from app.services.pricing import PricingSettings

T = TypeVar("T")


async def get_setting(
    session: AsyncSession,
    key: str,
    *,
    cast: Callable[[str], T] = str,
    default: T | None = None,
) -> T | None:
    """Читает settings.value по ключу и приводит cast'ом. Если строки нет
    (БД ещё не засижена) -- возвращает default."""
    row = await session.get(Setting, key)
    if row is None:
        return default
    return cast(row.value)


async def load_pricing_settings(session: AsyncSession) -> PricingSettings:
    defaults = PricingSettings()
    return PricingSettings(
        usd_to_rub_rate=await get_setting(session, "usd_to_rub_rate", cast=float, default=defaults.usd_to_rub_rate),
        rub_per_credit=await get_setting(session, "rub_per_credit", cast=float, default=defaults.rub_per_credit),
        provider_fee_multiplier=await get_setting(
            session, "provider_fee_multiplier", cast=float, default=defaults.provider_fee_multiplier
        ),
        margin_multiplier=await get_setting(
            session, "margin_multiplier", cast=float, default=defaults.margin_multiplier
        ),
        minimum_text_credits=await get_setting(
            session, "minimum_text_credits", cast=int, default=defaults.minimum_text_credits
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_settings_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/settings_service.py tests/services/test_settings_service.py
git commit -m "feat: settings table helper get_setting + load_pricing_settings"
```

---

### Task 5: Credit engine rewrite — `app/services/credit_service.py`

**Files:**
- Modify: `app/services/credit_service.py` (full rewrite of the current 47-line file; old `get_balance`/`spend_credits` and `CreditTxType.deposit` usage are removed)
- Test: `tests/services/test_credit_service.py`

**Interfaces:**
- Consumes: `User`, `AIRequest`, `CreditTransaction`, `CreditTxType`, `RequestStatus` (Task 1).
- Produces (phases 2–4 call these; signatures are fixed by the spec):
  - `class InsufficientBalanceError(Exception)` with attributes `balance: int`, `required: int`.
  - `async def reserve_credits(session: AsyncSession, user_id: int, amount: int, *, request_id: int | None, provider: str, model_code: str) -> CreditTransaction`
  - `async def settle_request(session: AsyncSession, request: AIRequest, actual_credits: int) -> CreditTransaction | None` — returns `None` when no adjustment transaction is needed (`actual == reserved`, or extra charge skipped for insufficient balance).
  - `async def refund_request(session: AsyncSession, request: AIRequest, *, reason: str) -> CreditTransaction`
  - `async def grant_credits(session: AsyncSession, user_id: int, amount: int, *, reason: str, tx_type: CreditTxType = CreditTxType.purchase) -> CreditTransaction`
  - **Transaction contract:** functions `flush()` but never `commit()` — the caller owns the transaction (so phase 2–3 flows can create the `AIRequest` and reserve in one atomic transaction). Row locks are held until the caller commits/rolls back.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/services/test_credit_service.py`:

```python
import asyncio
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import CreditTxType, ModelCategory, RequestStatus
from app.db.models import AIRequest, CreditTransaction, User
from app.services.credit_service import (
    InsufficientBalanceError,
    grant_credits,
    refund_request,
    reserve_credits,
    settle_request,
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


async def _make_user(session, balance: int) -> User:
    user = User(telegram_id=1, username="u", credits_balance=balance)
    session.add(user)
    await session.flush()
    return user


async def _make_reserved_request(session, user: User, reserved: int) -> AIRequest:
    request = AIRequest(
        user_id=user.id,
        provider="openrouter",
        model_code="deepseek_v3",
        category=ModelCategory.text,
        status=RequestStatus.reserved,
        prompt_preview="test prompt",
        estimated_credits=reserved,
        reserved_credits=reserved,
    )
    session.add(request)
    await session.flush()
    return request


async def _tx_count(session) -> int:
    return (await session.execute(select(func.count()).select_from(CreditTransaction))).scalar_one()


# --- reserve_credits ---

async def test_reserve_debits_balance_and_writes_reserve_tx(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=0)

    tx = await reserve_credits(
        session, user.id, 40, request_id=request.id, provider="openrouter", model_code="deepseek_v3"
    )
    await session.commit()

    assert user.credits_balance == 60
    assert tx.type == CreditTxType.reserve
    assert tx.amount == -40
    assert tx.balance_before == 100
    assert tx.balance_after == 60
    assert tx.provider == "openrouter"
    assert tx.model_code == "deepseek_v3"
    assert tx.request_id == request.id


async def test_reserve_insufficient_balance_raises_and_writes_nothing(session):
    user = await _make_user(session, balance=100)
    await session.commit()

    with pytest.raises(InsufficientBalanceError) as exc_info:
        await reserve_credits(session, user.id, 150, request_id=None, provider="openrouter", model_code="m")

    assert exc_info.value.balance == 100
    assert exc_info.value.required == 150
    await session.rollback()
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 100
    assert await _tx_count(session) == 0


async def test_reserve_rejects_non_positive_amount(session):
    user = await _make_user(session, balance=100)
    with pytest.raises(ValueError):
        await reserve_credits(session, user.id, 0, request_id=None, provider="openrouter", model_code="m")


# --- settle_request ---

async def test_settle_actual_less_than_reserved_releases_difference(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=40)
    user.credits_balance = 60  # состояние после reserve

    tx = await settle_request(session, request, actual_credits=25)
    await session.commit()

    assert tx.type == CreditTxType.release
    assert tx.amount == 15
    assert tx.balance_before == 60
    assert tx.balance_after == 75
    assert user.credits_balance == 75
    assert request.charged_credits == 25
    assert request.status == RequestStatus.completed
    assert request.completed_at is not None
    assert request.insufficient_balance_after_usage is False
    assert user.total_credits_spent == 25


async def test_settle_actual_more_than_reserved_charges_extra(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=40)
    user.credits_balance = 60

    tx = await settle_request(session, request, actual_credits=55)
    await session.commit()

    assert tx.type == CreditTxType.spend
    assert tx.amount == -15
    assert user.credits_balance == 45
    assert request.charged_credits == 55
    assert request.status == RequestStatus.completed
    assert user.total_credits_spent == 55


async def test_settle_extra_charge_with_insufficient_balance_flags_request(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=100)
    user.credits_balance = 0  # весь баланс ушёл в reserve

    tx = await settle_request(session, request, actual_credits=120)
    await session.commit()

    assert tx is None  # доплата 0 -- транзакция не создаётся
    assert user.credits_balance == 0
    assert request.charged_credits == 100  # = reserved_credits
    assert request.insufficient_balance_after_usage is True
    assert request.status == RequestStatus.completed
    assert user.total_credits_spent == 100


async def test_settle_actual_equals_reserved_needs_no_adjustment(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=40)
    user.credits_balance = 60

    tx = await settle_request(session, request, actual_credits=40)
    await session.commit()

    assert tx is None
    assert user.credits_balance == 60
    assert request.charged_credits == 40
    assert request.status == RequestStatus.completed
    assert await _tx_count(session) == 0


# --- refund_request ---

async def test_refund_after_reserve_returns_reserved_credits(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=40)
    user.credits_balance = 60

    tx = await refund_request(session, request, reason="provider error")
    await session.commit()

    assert tx.type == CreditTxType.refund
    assert tx.amount == 40
    assert tx.balance_before == 60
    assert tx.balance_after == 100
    assert tx.description == "provider error"
    assert user.credits_balance == 100
    assert request.status == RequestStatus.refunded
    assert request.charged_credits == 0


async def test_refund_after_settle_returns_charged_credits(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=40)
    user.credits_balance = 60
    await settle_request(session, request, actual_credits=55)  # balance 45, spent 55

    tx = await refund_request(session, request, reason="late provider failure")
    await session.commit()

    assert tx.amount == 55
    assert user.credits_balance == 100
    assert user.total_credits_spent == 0  # возврат снимает учтённое списание
    assert request.status == RequestStatus.refunded


# --- grant_credits ---

async def test_grant_purchase_credits_balance_and_totals(session):
    user = await _make_user(session, balance=10)

    tx = await grant_credits(session, user.id, 500, reason="package BASIC")
    await session.commit()

    assert tx.type == CreditTxType.purchase
    assert tx.amount == 500
    assert tx.balance_before == 10
    assert tx.balance_after == 510
    assert tx.description == "package BASIC"
    assert user.credits_balance == 510
    assert user.total_credits_purchased == 500


async def test_grant_admin_adjustment_does_not_touch_purchased_total(session):
    user = await _make_user(session, balance=0)

    await grant_credits(session, user.id, 50, reason="компенсация", tx_type=CreditTxType.admin_adjustment)
    await session.commit()

    assert user.credits_balance == 50
    assert user.total_credits_purchased == 0


async def test_grant_rejects_non_positive_amount(session):
    user = await _make_user(session, balance=0)
    with pytest.raises(ValueError):
        await grant_credits(session, user.id, -5, reason="nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_credit_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'InsufficientBalanceError' from 'app.services.credit_service'` (the old module still has `get_balance`/`spend_credits` and imports the now-removed `CreditTxType.deposit`, so the import may fail even earlier — either failure is acceptable).

- [ ] **Step 3: Rewrite `app/services/credit_service.py`**

Replace the entire file with:

```python
"""Движок кредитов. ЕДИНСТВЕННОЕ место, где можно менять users.credits_balance.

Правила (из спеки фазы 1):
- каждая операция лочит строку users через SELECT ... FOR UPDATE;
- credit_transactions -- неизменяемый аудит-лог со снимками balance_before/after;
- функции делают flush(), но НЕ commit() -- транзакцией владеет вызывающий код
  (фазы 2-3 создают AIRequest и резервируют кредиты в одной транзакции).
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType, RequestStatus
from app.db.models import AIRequest, CreditTransaction, User


class InsufficientBalanceError(Exception):
    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required
        super().__init__(f"credits balance {balance} < required {required}")


async def _lock_user(session: AsyncSession, user_id: int) -> User:
    # На SQLite (юнит-тесты) FOR UPDATE игнорируется диалектом; на Postgres --
    # честная блокировка строки до конца транзакции вызывающего кода.
    return (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one()


async def reserve_credits(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    request_id: int | None,
    provider: str,
    model_code: str,
) -> CreditTransaction:
    """Удерживает amount кредитов до запроса. При нехватке баланса кидает
    InsufficientBalanceError и НИЧЕГО не пишет."""
    if amount <= 0:
        raise ValueError(f"reserve amount must be positive, got {amount}")

    user = await _lock_user(session, user_id)
    if user.credits_balance < amount:
        raise InsufficientBalanceError(balance=user.credits_balance, required=amount)

    balance_before = user.credits_balance
    user.credits_balance = balance_before - amount
    tx = CreditTransaction(
        user_id=user_id,
        type=CreditTxType.reserve,
        amount=-amount,
        balance_before=balance_before,
        balance_after=user.credits_balance,
        provider=provider,
        model_code=model_code,
        request_id=request_id,
    )
    session.add(tx)
    await session.flush()
    return tx


async def settle_request(
    session: AsyncSession, request: AIRequest, actual_credits: int
) -> CreditTransaction | None:
    """Шаги 6-9 reserve-flow из ТЗ: пересчёт по фактическому расходу после ответа
    провайдера. Возвращает корректирующую транзакцию (release/spend) или None,
    если корректировка не нужна / доплата невозможна."""
    if actual_credits < 0:
        raise ValueError(f"actual_credits must be >= 0, got {actual_credits}")

    user = await _lock_user(session, request.user_id)
    reserved = request.reserved_credits
    tx: CreditTransaction | None = None
    charged = reserved

    if actual_credits < reserved:
        # Вернуть разницу на баланс.
        diff = reserved - actual_credits
        balance_before = user.credits_balance
        user.credits_balance = balance_before + diff
        tx = CreditTransaction(
            user_id=user.id,
            type=CreditTxType.release,
            amount=diff,
            balance_before=balance_before,
            balance_after=user.credits_balance,
            provider=request.provider,
            model_code=request.model_code,
            request_id=request.id,
        )
        session.add(tx)
        charged = actual_credits
    elif actual_credits > reserved:
        diff = actual_credits - reserved
        if user.credits_balance >= diff:
            balance_before = user.credits_balance
            user.credits_balance = balance_before - diff
            tx = CreditTransaction(
                user_id=user.id,
                type=CreditTxType.spend,
                amount=-diff,
                balance_before=balance_before,
                balance_after=user.credits_balance,
                provider=request.provider,
                model_code=request.model_code,
                request_id=request.id,
            )
            session.add(tx)
            charged = actual_credits
        else:
            # Баланса на доплату нет: списываем 0 доплаты, оставляем charged=reserved
            # и помечаем запрос флагом -- это НЕ ошибка.
            request.insufficient_balance_after_usage = True

    request.charged_credits = charged
    request.status = RequestStatus.completed
    request.completed_at = datetime.now(timezone.utc)
    user.total_credits_spent += charged
    await session.flush()
    return tx


async def refund_request(
    session: AsyncSession, request: AIRequest, *, reason: str
) -> CreditTransaction:
    """Полный возврат при ошибке провайдера: reserved_credits, либо
    charged_credits, если запрос уже был рассчитан (settle)."""
    user = await _lock_user(session, request.user_id)
    already_settled = request.status == RequestStatus.completed
    refund_amount = request.charged_credits if already_settled else request.reserved_credits

    balance_before = user.credits_balance
    user.credits_balance = balance_before + refund_amount
    if already_settled:
        user.total_credits_spent = max(user.total_credits_spent - refund_amount, 0)

    tx = CreditTransaction(
        user_id=user.id,
        type=CreditTxType.refund,
        amount=refund_amount,
        balance_before=balance_before,
        balance_after=user.credits_balance,
        provider=request.provider,
        model_code=request.model_code,
        request_id=request.id,
        description=reason,
    )
    session.add(tx)
    request.status = RequestStatus.refunded
    request.charged_credits = 0  # итоговое списание по запросу -- ноль
    await session.flush()
    return tx


async def grant_credits(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    reason: str,
    tx_type: CreditTxType = CreditTxType.purchase,
) -> CreditTransaction:
    """Начисление кредитов: покупка пакета (фаза 4) или админ-корректировка (фаза 5).
    В фазе 1 -- только функция + тесты, без вызывающего кода."""
    if amount <= 0:
        raise ValueError(f"grant amount must be positive, got {amount}")

    user = await _lock_user(session, user_id)
    balance_before = user.credits_balance
    user.credits_balance = balance_before + amount
    if tx_type == CreditTxType.purchase:
        user.total_credits_purchased += amount

    tx = CreditTransaction(
        user_id=user_id,
        type=tx_type,
        amount=amount,
        balance_before=balance_before,
        balance_after=user.credits_balance,
        description=reason,
    )
    session.add(tx)
    await session.flush()
    return tx
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_credit_service.py -v`
Expected: PASS (12 tests; the Postgres concurrency test does not exist yet — Task 6).

- [ ] **Step 5: Commit**

```bash
git add app/services/credit_service.py tests/services/test_credit_service.py
git commit -m "feat: row-locked credit engine (reserve/settle/refund/grant)"
```

---

### Task 6: Concurrent-reserve row-lock integration test (real Postgres)

**Files:**
- Modify: `tests/services/test_credit_service.py` (append the concurrency test at the end of the file)

**Interfaces:**
- Consumes: `reserve_credits`, `InsufficientBalanceError` (Task 5); `Base.metadata` (Task 1).
- Produces: proof that `SELECT ... FOR UPDATE` prevents double-spend under concurrency, per the spec's Testing section. Runs only when env var `TEST_DATABASE_URL` points at a disposable Postgres 16 database (e.g. `postgresql+asyncpg://postgres:postgres@localhost:5432/ai_hub_test`); otherwise skipped with a clear reason. **The test drops and recreates all tables in that database — never point it at a real dev/prod DB.**

- [ ] **Step 1: Write the test (appended to `tests/services/test_credit_service.py`)**

```python
# --- Конкурентный reserve: интеграционный тест с реальным Postgres ---
# SQLite игнорирует FOR UPDATE, поэтому блокировку строки можно проверить только
# на настоящей БД. Задайте TEST_DATABASE_URL на ОДНОРАЗОВУЮ базу, например:
#   postgresql+asyncpg://postgres:postgres@localhost:5432/ai_hub_test
# Тест делает drop_all/create_all -- не указывайте рабочую базу.

POSTGRES_TEST_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="TEST_DATABASE_URL not set; row-lock test requires a real Postgres",
)
async def test_concurrent_reserve_cannot_overdraw_balance():
    engine = create_async_engine(POSTGRES_TEST_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async with maker() as s:
            user = User(telegram_id=999, username="racer", credits_balance=100)
            s.add(user)
            await s.commit()
            user_id = user.id

        async def try_reserve() -> CreditTransaction:
            # Отдельная сессия = отдельное соединение = отдельная транзакция.
            async with maker() as s:
                async with s.begin():
                    return await reserve_credits(
                        s, user_id, 60, request_id=None, provider="openrouter", model_code="deepseek_v3"
                    )

        results = await asyncio.gather(try_reserve(), try_reserve(), return_exceptions=True)

        errors = [r for r in results if isinstance(r, InsufficientBalanceError)]
        successes = [r for r in results if isinstance(r, CreditTransaction)]
        assert len(successes) == 1, f"exactly one reserve must win, got results: {results!r}"
        assert len(errors) == 1, f"the loser must get InsufficientBalanceError, got: {results!r}"

        async with maker() as s:
            fetched = await s.get(User, user_id)
            assert fetched.credits_balance == 40  # 100 - 60, второй reserve не прошёл
            tx_total = (
                await s.execute(select(func.count()).select_from(CreditTransaction))
            ).scalar_one()
            assert tx_total == 1
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
```

(`os`, `asyncio`, `select`, `func`, `create_async_engine`, `async_sessionmaker`, `Base`, `User`, `CreditTransaction`, `reserve_credits`, `InsufficientBalanceError` are already imported at the top of this file from Task 5 Step 1.)

- [ ] **Step 2: Run without Postgres to verify the skip is clean**

Run: `python -m pytest tests/services/test_credit_service.py -v`
Expected: 12 passed, 1 skipped (`TEST_DATABASE_URL not set`).

- [ ] **Step 3: Run against a real Postgres**

Start a disposable Postgres 16, e.g. `docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=postgres --name ai-hub-test-pg postgres:16` (or use any empty throwaway database). Then in PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/postgres"
python -m pytest tests/services/test_credit_service.py::test_concurrent_reserve_cannot_overdraw_balance -v
```

Expected: PASS. The second `reserve_credits` blocks on the row lock until the first transaction commits, re-reads `credits_balance = 40`, and raises `InsufficientBalanceError`. If Docker/Postgres is genuinely unavailable in the environment, record that in the task report — the test must still exist and skip cleanly.

- [ ] **Step 4: Commit**

```bash
git add tests/services/test_credit_service.py
git commit -m "test: concurrent reserve row-lock integration test against real Postgres"
```

---

### Task 7: Seed rewrite — packages, settings, model catalog

**Files:**
- Modify: `app/db/seed.py` (full rewrite; old `TARIFFS`/`MODEL_CONFIGS` lists are removed, `BANNERS` list at current lines 155–186 is kept verbatim)
- Test: `tests/db/test_seed_catalog.py`

**Interfaces:**
- Consumes: `AiModel`, `CreditPackage`, `Setting`, `Banner` models; enums (Task 1); `get_session` from `app.db.session` (unchanged).
- Produces:
  - Module-level constants `SETTINGS_ROWS: list[dict]`, `CREDIT_PACKAGES: list[dict]`, `AI_MODELS: list[dict]`, `BANNERS: list[dict]` (tests inspect these statically, same pattern as the deleted `test_seed_piapi_catalog.py`).
  - `async def apply_seed(session: AsyncSession) -> None` — idempotent insert-if-missing, testable with any session.
  - `async def seed() -> None` — opens a session via `get_session()` and calls `apply_seed` (same entrypoint shape as today: `python -m app.db.seed`).

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_seed_catalog.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/db/test_seed_catalog.py -v`
Expected: FAIL — `ImportError: cannot import name 'AI_MODELS' from 'app.db.seed'` (the old seed module still references deleted `ModelConfig`/`Tariff`, so it may fail on its own imports first — either failure is acceptable).

- [ ] **Step 3: Rewrite `app/db/seed.py`**

Replace the entire file with (BANNERS block is copied verbatim from the current file lines 155–186):

```python
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel, Banner, CreditPackage, Setting
from app.db.session import get_session

SETTINGS_ROWS = [
    dict(key="usd_to_rub_rate", value="80", type="float",
         description="Внутренний курс USD→RUB (с запасом; редактируется админкой, фаза 5)"),
    dict(key="rub_per_credit", value="0.10", type="float",
         description="Номинальная стоимость 1 кредита в рублях"),
    dict(key="provider_fee_multiplier", value="1.15", type="float",
         description="Надбавка за комиссии OpenRouter/fal.ai поверх API-цены"),
    dict(key="margin_multiplier", value="2.5", type="float",
         description="Множитель целевой маржи"),
    dict(key="minimum_text_credits", value="3", type="int",
         description="Минимальное списание за любой текстовый запрос"),
]

CREDIT_PACKAGES = [
    dict(code="start", title="START", credits=1000, price_rub=149,
         description="Для знакомства с ботом"),
    dict(code="basic", title="BASIC", credits=5000, price_rub=599,
         description="Для обычного использования"),
    dict(code="plus", title="PLUS", credits=12000, price_rub=1290,
         description="Для активной работы с текстом и изображениями"),
    dict(code="pro", title="PRO", credits=30000, price_rub=2990,
         description="Для частой генерации изображений и видео"),
    dict(code="business", title="BUSINESS", credits=70000, price_rub=5990,
         description="Для агентств и heavy users"),
]

# ВНИМАНИЕ (по ТЗ): provider_model_id и input/output-цены ниже -- ПЛЕЙСХОЛДЕРЫ.
# Уточнить реальные ID и цены OpenRouter/fal.ai перед продакшн-запуском (фазы 2-3).
# Пока цены = 0 -> списание текстовых моделей идёт по min_credits (защитный минимум).
_TEXT = dict(provider=ModelProvider.openrouter, category=ModelCategory.text, cost_unit=CostUnit.tokens,
             input_price_usd_per_1m_tokens=0, output_price_usd_per_1m_tokens=0, fixed_cost_usd=0,
             max_context_tokens=128000, is_active=True, is_visible=True)
_MEDIA = dict(provider=ModelProvider.fal, input_price_usd_per_1m_tokens=0, output_price_usd_per_1m_tokens=0,
              fixed_cost_usd=0, max_context_tokens=4000, is_active=True, is_visible=True)

AI_MODELS = [
    # --- TEXT (OpenRouter), 12 моделей из ТЗ ---
    dict(**_TEXT, code="deepseek_v3", display_name="DeepSeek V3", tier=ModelTier.economy,
         provider_model_id="deepseek/deepseek-chat",  # PLACEHOLDER
         min_credits=3, recommended_credits=3, sort_order=10),
    dict(**_TEXT, code="llama_3_1_8b", display_name="Llama 3.1 8B", tier=ModelTier.economy,
         provider_model_id="meta-llama/llama-3.1-8b-instruct",  # PLACEHOLDER
         min_credits=3, recommended_credits=3, sort_order=20),
    dict(**_TEXT, code="qwen_plus", display_name="Qwen Plus", tier=ModelTier.economy,
         provider_model_id="qwen/qwen-plus",  # PLACEHOLDER
         min_credits=3, recommended_credits=6, sort_order=30),
    dict(**_TEXT, code="mistral_large", display_name="Mistral Large", tier=ModelTier.economy,
         provider_model_id="mistralai/mistral-large",  # PLACEHOLDER
         min_credits=3, recommended_credits=6, sort_order=40),
    dict(**_TEXT, code="gpt_mini", display_name="GPT Mini", tier=ModelTier.standard,
         provider_model_id="openai/gpt-4o-mini",  # PLACEHOLDER
         min_credits=5, recommended_credits=6, sort_order=50),
    dict(**_TEXT, code="qwen_max", display_name="Qwen Max", tier=ModelTier.standard,
         provider_model_id="qwen/qwen-max",  # PLACEHOLDER
         min_credits=10, recommended_credits=15, sort_order=60),
    dict(**_TEXT, code="grok", display_name="Grok", tier=ModelTier.standard,
         provider_model_id="x-ai/grok-2",  # PLACEHOLDER
         min_credits=10, recommended_credits=15, sort_order=70),
    dict(**_TEXT, code="gpt_premium", display_name="GPT Premium", tier=ModelTier.premium,
         provider_model_id="openai/gpt-4o",  # PLACEHOLDER
         min_credits=20, recommended_credits=30, sort_order=80),
    dict(**_TEXT, code="gemini_flash", display_name="Gemini Flash", tier=ModelTier.premium,
         provider_model_id="google/gemini-flash-1.5",  # PLACEHOLDER
         min_credits=20, recommended_credits=30, sort_order=90),
    dict(**_TEXT, code="gemini_pro", display_name="Gemini Pro", tier=ModelTier.premium,
         provider_model_id="google/gemini-pro-1.5",  # PLACEHOLDER
         min_credits=30, recommended_credits=40, sort_order=100),
    dict(**_TEXT, code="claude_sonnet", display_name="Claude Sonnet", tier=ModelTier.pro,
         provider_model_id="anthropic/claude-3.5-sonnet",  # PLACEHOLDER
         min_credits=40, recommended_credits=50, sort_order=110),
    dict(**_TEXT, code="claude_opus", display_name="Claude Opus", tier=ModelTier.ultra,
         provider_model_id="anthropic/claude-3-opus",  # PLACEHOLDER
         min_credits=70, recommended_credits=90, sort_order=120),
    # --- IMAGE (fal.ai), 4 модели из ТЗ ---
    dict(**_MEDIA, category=ModelCategory.image, code="qwen_image", display_name="Qwen Image",
         tier=ModelTier.economy, cost_unit=CostUnit.megapixel,
         provider_model_id="fal-ai/qwen-image",  # PLACEHOLDER
         min_credits=50, recommended_credits=50, sort_order=130),
    dict(**_MEDIA, category=ModelCategory.image, code="seedream", display_name="Seedream",
         tier=ModelTier.standard, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/bytedance/seedream/v3",  # PLACEHOLDER
         min_credits=75, recommended_credits=75, sort_order=140),
    dict(**_MEDIA, category=ModelCategory.image, code="flux_kontext_pro", display_name="Flux Kontext Pro",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/flux-pro/kontext",  # PLACEHOLDER
         min_credits=100, recommended_credits=100, sort_order=150),
    dict(**_MEDIA, category=ModelCategory.image, code="nano_banana", display_name="Nano Banana",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/nano-banana",  # PLACEHOLDER
         min_credits=100, recommended_credits=100, sort_order=160),
    # --- VIDEO (fal.ai), 4 модели из ТЗ (recommended_credits -- цена за 5 секунд) ---
    dict(**_MEDIA, category=ModelCategory.video, code="ovi_video", display_name="Ovi Video",
         tier=ModelTier.economy, cost_unit=CostUnit.video,
         provider_model_id="fal-ai/ovi",  # PLACEHOLDER
         min_credits=500, recommended_credits=500, sort_order=170),
    dict(**_MEDIA, category=ModelCategory.video, code="wan_video", display_name="Wan Video",
         tier=ModelTier.standard, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/wan/v2.2",  # PLACEHOLDER
         min_credits=600, recommended_credits=600, sort_order=180),
    dict(**_MEDIA, category=ModelCategory.video, code="kling_video", display_name="Kling Video",
         tier=ModelTier.premium, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/kling-video/v2",  # PLACEHOLDER
         min_credits=850, recommended_credits=850, sort_order=190),
    dict(**_MEDIA, category=ModelCategory.video, code="veo_video", display_name="Veo Video",
         tier=ModelTier.ultra, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/veo3",  # PLACEHOLDER
         min_credits=4800, recommended_credits=4800, sort_order=200),
]

# Banner-сиды переносятся как есть (не относятся к кредитной системе).
BANNERS = [
    dict(
        title="ChatGPT, Claude и Gemini в одном чате",
        subtitle="Переключайтесь между моделями одним тапом",
        badge_text="Новое",
        cta_text="Попробовать",
        image_url="https://picsum.photos/seed/ai-hub-banner-1/800/450",
        action_type="prompt",
        action_value="Расскажи, что ты умеешь и чем можешь помочь",
        sort_order=0,
    ),
    dict(
        title="Генерация изображений",
        subtitle="Опишите идею словами — получите картинку",
        badge_text="Popular",
        cta_text="Создать картинку",
        image_url="https://picsum.photos/seed/ai-hub-banner-2/800/450",
        action_type="prompt",
        action_value="Сгенерируй изображение: ",
        sort_order=1,
    ),
    dict(
        title="Кредиты поверх тарифа",
        subtitle="Докупайте запросы, когда лимит закончился",
        badge_text=None,
        cta_text="Подробнее",
        image_url="https://picsum.photos/seed/ai-hub-banner-3/800/450",
        action_type="prompt",
        action_value="Как работают кредиты в этом боте?",
        sort_order=2,
    ),
]


async def apply_seed(session: AsyncSession) -> None:
    """Идемпотентный сид: вставляет только отсутствующие строки (по естественному ключу)."""
    existing_settings = {row[0] for row in (await session.execute(select(Setting.key))).all()}
    for data in SETTINGS_ROWS:
        if data["key"] not in existing_settings:
            session.add(Setting(**data))

    existing_packages = {row[0] for row in (await session.execute(select(CreditPackage.code))).all()}
    for data in CREDIT_PACKAGES:
        if data["code"] not in existing_packages:
            session.add(CreditPackage(**data))

    existing_models = {row[0] for row in (await session.execute(select(AiModel.code))).all()}
    for data in AI_MODELS:
        if data["code"] not in existing_models:
            session.add(AiModel(**data))

    existing_banner_titles = {row[0] for row in (await session.execute(select(Banner.title))).all()}
    for data in BANNERS:
        if data["title"] not in existing_banner_titles:
            session.add(Banner(**data))

    await session.commit()


async def seed() -> None:
    async with get_session() as session:
        await apply_seed(session)


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/db/test_seed_catalog.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: all tests pass (schema, pricing, settings, credit service, seed, piapi_client, piapi_key), 1 skipped if `TEST_DATABASE_URL` is unset.

- [ ] **Step 6: Commit**

```bash
git add app/db/seed.py tests/db/test_seed_catalog.py
git commit -m "feat: seed credit packages, pricing settings and 20-model catalog"
```

---

## Spec coverage checklist (self-review, completed)

| Spec section | Covered by |
|---|---|
| `users` alterations (+3 columns, rename `active_model`→`default_model_code`) | Task 1 (model), Task 2 (migration step 1) |
| Data migration: `SUM(credit_transactions.amount)` → `credits_balance`, unconditional | Task 2 (migration step 2) |
| `credit_transactions` recreated (signed amount, snapshots, no `payment_id` FK) | Task 1, Task 2 |
| `ai_requests` recreated (+`insufficient_balance_after_usage`) | Task 1, Task 2 |
| `ai_models` — exact ТЗ field list | Task 1, Task 2 |
| `credit_packages` table replacing dataclass file | Task 1, Task 2, Task 7 (seeds) |
| `settings` table + `get_setting` helper with empty-DB default | Task 1, Task 2, Task 4 |
| Deleted models/services/enums; `Banner`/`Payment`/`Referral` untouched (Payment: FK-only removal forced by `DROP TABLE tariffs`) | Task 1, Task 2 |
| One migration `phase1_credit_system_v2`, steps 1–6, enum types swapped | Task 2 |
| Credit engine: 4 functions + `InsufficientBalanceError`, all under `FOR UPDATE`, balance never touched elsewhere | Task 5 |
| `pricing.py`: 3 pure functions, ТЗ formulas, floors (min_credits / edit 100 / video 500) | Task 3 |
| Seed: 5 packages, 5 settings, 20 models with placeholder provider ids/prices, banners as-is | Task 7 |
| Tests: pricing edge cases; reserve-insufficient; settle 3 branches; refund; concurrent reserve on real DB | Tasks 3, 5, 6 |
| Out of scope items untouched (providers, bot commands, admin, payments, anti-fraud) | Global Constraints |
