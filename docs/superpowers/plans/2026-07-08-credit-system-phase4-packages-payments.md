# Credit System Phase 4 — Packages & Payments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken tariff/subscription purchase flow with a credit-package-only payment path (YooKassa + Telegram Stars + crypto stub) and fix `app/worker.py`, wiring in phase 3's stale-reserve reconciliation sweep.

**Architecture:** Payments always reference a `credit_package_code` (the phase-1 DB model `CreditPackage`, which gains a `price_stars` column); activation is a single idempotent function that grants credits via phase-1's `grant_credits` and links the payment through `CreditTransaction.metadata_json`. The `PaymentGateway` ABC loses its tariff method, keeps `create_credit_payment`/`check_payment_status`/`refund_payment`, and gains a third implementation — a manual-confirmation crypto stub. The worker drops subscription-era jobs and adds a `reconcile_stale_media_reserves` job.

**Tech Stack:** Python 3.12, aiogram 3, FastAPI, SQLAlchemy 2 async, Alembic (hand-written migrations), Postgres (prod) / `sqlite+aiosqlite` (tests), APScheduler 3, `yookassa` SDK, pytest + pytest-asyncio (`asyncio_mode = auto`).

**Spec (ground truth):** `docs/superpowers/specs/2026-07-08-credit-system-phase4-packages-payments-design.md`

## Global Constraints

- New Alembic migration MUST have `down_revision = 'd5e6f7a8b9c0'` (current head, `alembic/versions/d5e6f7a8b9c0_phase3_result_url.py`). Hand-written style, like the existing migrations — never `alembic revision --autogenerate`.
- `price_stars` seed values are EXACTLY: start=75, basic=300, plus=645, pro=1495, business=2995 (spec table, PLACEHOLDER rate ≈ `price_rub / 2`, editable by admin in phase 5).
- `PaymentProvider` gains value `crypto = "crypto"`; existing values (`telegram_stars`, `yookassa`, `manual`, `promo`) are untouched.
- No new pip dependencies. The crypto gateway is a stub with no external SDK; `requirements.txt` is not modified.
- Backend only — `frontend-next/` is untouched.
- `app/main.py` is NOT modified. It (and `app/api/routes/admin.py`, `app/services/admin_service.py`, `app/services/stats_service.py`, which still import deleted `Tariff`/`Subscription`/`subscription_service`) stays broken until phase 5. Consequence for tests: NEVER import `app.main` — build a minimal `FastAPI()` app from the router under test (existing pattern in `tests/api/test_generate_routes.py`).
- Phase-1 invariant (docstring of `CreditTransaction`): rows of `credit_transactions` are created ONLY inside `app/services/credit_service.py`. Therefore payment linkage goes through a new optional `metadata` parameter on `grant_credits` — NOT by mutating `CreditTransaction` from `activation.py`.
- Credit purchases use `grant_credits`'s default `tx_type=CreditTxType.purchase` (there is no `CreditTxType.deposit` — the old activation code referenced a deleted enum value). `purchase` also increments `user.total_credits_purchased`, which is correct here.
- All user-facing strings (invoice titles, error details, bot messages) are in Russian, matching existing copy exactly where kept.
- Test env vars for any test file whose import chain reaches `app.config` or `app.bot.instance`: set at the very top of the file, BEFORE other imports: `os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")` (aiogram validates the `digits:rest` token shape at `Bot()` construction — `"test-token"` would crash) and `os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")`.
- Test conventions of this project: no `conftest.py`; each test file has its own `session` fixture over `sqlite+aiosqlite://` with `Base.metadata.create_all`; external boundaries are faked with hand-rolled fakes / `unittest.mock.AsyncMock` via `monkeypatch` (see `tests/api/test_generate_routes.py`).
- `pytest.ini` sets `asyncio_mode = auto` — async tests need no decorator.
- Run tests with `python -m pytest <path> -v` from the repo root `C:\Users\mccaq\ai-hub-bot`.

---

## File Structure

| File | Action | Responsibility after phase 4 |
|---|---|---|
| `app/db/enums.py` | Modify | `PaymentProvider` += `crypto` |
| `app/db/models/credit_packages.py` | Modify | += `price_stars` column |
| `app/db/models/payment.py` | Modify | −`tariff_id`; payment is always about a credit package |
| `alembic/versions/e6f7a8b9c0d1_phase4_price_stars_drop_tariff_id.py` | Create | ADD `credit_packages.price_stars`, backfill 5 seed rows, DROP `payments.tariff_id` |
| `app/db/seed.py` | Modify | 5 package dicts gain `price_stars` |
| `app/services/credit_service.py` | Modify | `grant_credits` gains optional `metadata: dict \| None = None` → `CreditTransaction.metadata_json` |
| `app/services/payments/activation.py` | Rewrite | Idempotent credit-package activation only |
| `app/services/payments/gateway.py` | Modify | ABC without `create_payment`; `create_credit_payment` takes DB `CreditPackage` |
| `app/services/payments/yookassa_service.py` | Rewrite | Credit-package payments via YooKassa SDK |
| `app/services/payments/stars_service.py` | Rewrite | Credit-package invoices via Telegram Stars |
| `app/services/payments/crypto_service.py` | Create | Manual-confirmation stub gateway |
| `app/services/payments/setup.py` | Modify | Registers all 3 gateways |
| `app/webhooks/yookassa.py` | Rewrite | Credits-only activation branch |
| `app/bot/handlers/payments.py` | Modify | Credits-only success message |
| `app/api/routes/payments.py` | Rewrite | DB-backed `/credits/packages`; 3 × `/payments/credits/{provider}/create`; status/history unchanged |
| `app/services/notification_service.py` | Modify | Only `_send` + `notify_credits_purchase` remain |
| `app/worker.py` | Rewrite | 3 jobs: yookassa poll, stale-created cancel, media-reserve reconcile |
| `app/services/media_generation_service.py` | Modify (docstring only) | Remove stale "worker.py is broken" TODO paragraph |
| `tests/db/test_credit_schema_v2.py` | Append | `price_stars` round-trip, `tariff_id` gone, `crypto` enum |
| `tests/db/test_seed_catalog.py` | Append | seed `price_stars` values per spec table |
| `tests/services/test_credit_service.py` | Append | `grant_credits` metadata tests |
| `tests/services/payments/__init__.py` | Create | package marker |
| `tests/services/payments/test_activation.py` | Create | idempotent activation tests |
| `tests/services/payments/test_gateway.py` | Create | YooKassa/Stars/Crypto gateway tests, SDK+bot mocked |
| `tests/api/test_payments_routes.py` | Create | API contract tests over a minimal app |
| `tests/test_worker.py` | Create | poller, reconcile job, scheduler wiring |

Task order matters: Task 1 (schema) unblocks everything; Task 2 (`grant_credits`) unblocks Task 3 (activation); Task 4 (gateway ABC + 2 services) unblocks Task 5 (crypto) and Task 7 (routes); Tasks 6/8 depend on Task 3's new `ActivationResult`.

---

### Task 1: Schema — `price_stars`, drop `tariff_id`, `crypto` provider, migration, seeds

**Files:**
- Modify: `app/db/enums.py:4-8`
- Modify: `app/db/models/credit_packages.py`
- Modify: `app/db/models/payment.py:19-24`
- Create: `alembic/versions/e6f7a8b9c0d1_phase4_price_stars_drop_tariff_id.py`
- Modify: `app/db/seed.py:23-34`
- Test: `tests/db/test_credit_schema_v2.py` (append), `tests/db/test_seed_catalog.py` (append to `test_five_packages_from_tz`)

**Interfaces:**
- Consumes: phase-1 models `CreditPackage`, `Payment`; Alembic head `d5e6f7a8b9c0`.
- Produces: `CreditPackage.price_stars: Mapped[int]` (default 0); `Payment` WITHOUT `tariff_id`; `PaymentProvider.crypto`. Every later task builds `Payment(...)` without a `tariff_id` kwarg and reads `package.price_stars`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/db/test_credit_schema_v2.py` (it already imports `CreditPackage`; extend the `app.db.models` import line with `Payment` and add `from app.db.enums import PaymentProvider` to the enums import list):

```python
async def test_credit_package_price_stars_round_trip(session):
    pkg = CreditPackage(code="stars_pkg", title="STARS", credits=1000, price_rub=149, price_stars=75)
    session.add(pkg)
    await session.commit()

    fetched = await session.get(CreditPackage, pkg.id)
    assert fetched.price_stars == 75


async def test_credit_package_price_stars_defaults_to_zero(session):
    pkg = CreditPackage(code="no_stars", title="NS", credits=100, price_rub=10)
    session.add(pkg)
    await session.commit()

    fetched = await session.get(CreditPackage, pkg.id)
    assert fetched.price_stars == 0


async def test_payment_has_no_tariff_id_and_crypto_provider_exists():
    assert not hasattr(Payment, "tariff_id")
    assert PaymentProvider.crypto.value == "crypto"
```

Append to `tests/db/test_seed_catalog.py`, inside the existing `test_five_packages_from_tz` function body (after the `business` assertion):

```python
    assert by_code["start"]["price_stars"] == 75
    assert by_code["basic"]["price_stars"] == 300
    assert by_code["plus"]["price_stars"] == 645
    assert by_code["pro"]["price_stars"] == 1495
    assert by_code["business"]["price_stars"] == 2995
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/db/test_credit_schema_v2.py tests/db/test_seed_catalog.py -v`
Expected: FAIL — `TypeError: 'price_stars' is an invalid keyword argument for CreditPackage`, `assert not hasattr(Payment, "tariff_id")` fails, `AttributeError: crypto`, `KeyError: 'price_stars'` in seed test.

- [ ] **Step 3: Implement model + enum + seed changes**

In `app/db/enums.py`, add `crypto` to `PaymentProvider`:

```python
class PaymentProvider(str, enum.Enum):
    telegram_stars = "telegram_stars"
    yookassa = "yookassa"
    manual = "manual"
    promo = "promo"
    crypto = "crypto"
```

In `app/db/models/credit_packages.py`, add after `price_rub`:

```python
    price_stars: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

In `app/db/models/payment.py`, replace lines 19-24 (the legacy comment block + the `tariff_id` column + the existing `credit_package_code` line) with this block — the result must contain `credit_package_code` exactly once:

```python
    # Фаза 4: платёж всегда про пакет кредитов. tariff_id/подписки удалены
    # (tariffs снесены в фазе 1, колонка -- миграцией фазы 4).
    credit_package_code: Mapped[str | None] = mapped_column(String(32))
```

(The `Integer` import in `payment.py` stays — check: it is no longer used after removing `tariff_id`, so ALSO remove `Integer` from the `sqlalchemy` import line.)

In `app/db/seed.py`, extend the 5 `CREDIT_PACKAGES` dicts:

```python
CREDIT_PACKAGES = [
    dict(code="start", title="START", credits=1000, price_rub=149, price_stars=75,
         description="Для знакомства с ботом"),
    dict(code="basic", title="BASIC", credits=5000, price_rub=599, price_stars=300,
         description="Для обычного использования"),
    dict(code="plus", title="PLUS", credits=12000, price_rub=1290, price_stars=645,
         description="Для активной работы с текстом и изображениями"),
    dict(code="pro", title="PRO", credits=30000, price_rub=2990, price_stars=1495,
         description="Для частой генерации изображений и видео"),
    dict(code="business", title="BUSINESS", credits=70000, price_rub=5990, price_stars=2995,
         description="Для агентств и heavy users"),
]
```

- [ ] **Step 4: Write the migration**

Create `alembic/versions/e6f7a8b9c0d1_phase4_price_stars_drop_tariff_id.py` (same hand-written style as `d5e6f7a8b9c0_phase3_result_url.py`):

```python
"""phase4: credit_packages.price_stars (Telegram Stars price, PLACEHOLDER rate
~= price_rub / 2, admin-editable in phase 5) + drop dead payments.tariff_id
(tariffs table was removed in phase 1; the FK constraint on this column was
already dropped by the phase-1 migration, so a plain DROP COLUMN suffices).

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Spec table (phase 4): PLACEHOLDER Stars prices for the 5 seeded packages.
_PRICE_STARS = {"start": 75, "basic": 300, "plus": 645, "pro": 1495, "business": 2995}


def upgrade() -> None:
    op.add_column(
        'credit_packages',
        sa.Column('price_stars', sa.Integer(), nullable=False, server_default='0'),
    )
    # Existing rows were seeded before this column existed -- backfill them.
    # (app/db/seed.py only inserts MISSING codes, so it would leave 0 here.)
    for code, stars in _PRICE_STARS.items():
        op.execute(
            sa.text("UPDATE credit_packages SET price_stars = :stars WHERE code = :code")
            .bindparams(stars=stars, code=code)
        )
    op.drop_column('payments', 'tariff_id')


def downgrade() -> None:
    op.add_column('payments', sa.Column('tariff_id', sa.Integer(), nullable=True))
    op.drop_column('credit_packages', 'price_stars')
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/db/test_credit_schema_v2.py tests/db/test_seed_catalog.py -v`
Expected: PASS (all, including the pre-existing tests in both files).

- [ ] **Step 6: Sanity-check the migration chain**

Run: `python -m alembic heads`
Expected output contains: `e6f7a8b9c0d1 (head)`

- [ ] **Step 7: Commit**

```bash
git add app/db/enums.py app/db/models/credit_packages.py app/db/models/payment.py app/db/seed.py alembic/versions/e6f7a8b9c0d1_phase4_price_stars_drop_tariff_id.py tests/db/test_credit_schema_v2.py tests/db/test_seed_catalog.py
git commit -m "feat(phase4): credit_packages.price_stars, drop payments.tariff_id, PaymentProvider.crypto"
```

---

### Task 2: `grant_credits` — optional `metadata` parameter

The spec requires the payment→grant link to live in `CreditTransaction.metadata_json = {"payment_id": ...}`, but phase-1's `grant_credits(session, user_id, amount, *, reason, tx_type=CreditTxType.purchase)` has no way to pass it, and the phase-1 invariant forbids creating/mutating `CreditTransaction` rows outside `credit_service.py`. **Decision: extend `grant_credits` with a keyword-only, optional, backward-compatible `metadata: dict | None = None` parameter.** All existing callers (tests; broken phase-5 `admin.py`) keep working unchanged.

**Files:**
- Modify: `app/services/credit_service.py:167-196`
- Test: `tests/services/test_credit_service.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `async def grant_credits(session: AsyncSession, user_id: int, amount: int, *, reason: str, tx_type: CreditTxType = CreditTxType.purchase, metadata: dict | None = None) -> CreditTransaction` — Task 3 calls it with `metadata={"payment_id": payment.id}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/test_credit_service.py` (uses the file's existing `session` fixture and `_make_user` helper):

```python
async def test_grant_credits_stores_metadata_json(session):
    user = await _make_user(session, balance=0)

    tx = await grant_credits(
        session, user.id, 500, reason="credit package start", metadata={"payment_id": 42}
    )
    await session.commit()

    assert tx.metadata_json == {"payment_id": 42}
    assert tx.type == CreditTxType.purchase
    assert user.credits_balance == 500
    assert user.total_credits_purchased == 500


async def test_grant_credits_metadata_defaults_to_none(session):
    user = await _make_user(session, balance=0)

    tx = await grant_credits(session, user.id, 500, reason="no metadata")
    await session.commit()

    assert tx.metadata_json is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_credit_service.py -v -k metadata`
Expected: FAIL with `TypeError: grant_credits() got an unexpected keyword argument 'metadata'`.

- [ ] **Step 3: Implement**

In `app/services/credit_service.py`, change `grant_credits`'s signature and the `CreditTransaction(...)` construction (only these two spots; body otherwise unchanged):

```python
async def grant_credits(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    reason: str,
    tx_type: CreditTxType = CreditTxType.purchase,
    metadata: dict | None = None,
) -> CreditTransaction:
    """Начисление кредитов: покупка пакета (фаза 4) или админ-корректировка (фаза 5).
    metadata -- контекст начисления (например {"payment_id": ...} из activation.py),
    сохраняется в credit_transactions.metadata_json."""
```

and in the `tx = CreditTransaction(...)` call add:

```python
        metadata_json=metadata,
```

- [ ] **Step 4: Run the full credit-service test file**

Run: `python -m pytest tests/services/test_credit_service.py -v`
Expected: PASS (all existing tests plus the 2 new ones).

- [ ] **Step 5: Commit**

```bash
git add app/services/credit_service.py tests/services/test_credit_service.py
git commit -m "feat(phase4): grant_credits accepts optional metadata for payment linkage"
```

---

### Task 3: Rewrite `activation.py` — credit-package-only idempotent activation

**Files:**
- Rewrite: `app/services/payments/activation.py`
- Create: `tests/services/payments/__init__.py` (empty file)
- Test: `tests/services/payments/test_activation.py` (new)

**Interfaces:**
- Consumes: Task 2's `grant_credits(session, user_id, amount, *, reason, tx_type=..., metadata=...)`; Task 1's `Payment` without `tariff_id`.
- Produces: `@dataclass ActivationResult(credits_granted: int = 0)` and `async def activate_paid_payment(session: AsyncSession, *, payment_id: int | None = None, provider: PaymentProvider | None = None, provider_payment_id: str | None = None, charge_id: str | None = None) -> ActivationResult | None`. Tasks 6 and 8 rely on: return `None` == already-processed/unknown; otherwise `result.credits_granted` (there is NO `.subscription` field anymore).

- [ ] **Step 1: Create the test package and write the failing tests**

Create empty `tests/services/payments/__init__.py`.

Create `tests/services/payments/test_activation.py`:

```python
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CreditTxType, PaymentProvider, PaymentStatus
from app.db.models import CreditTransaction, Payment, User
from app.services.payments.activation import ActivationResult, activate_paid_payment


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _make_user(session, balance: int = 0) -> User:
    user = User(telegram_id=1, username="u", credits_balance=balance)
    session.add(user)
    await session.flush()
    return user


async def _make_payment(session, user: User, **overrides) -> Payment:
    fields = dict(
        user_id=user.id,
        credit_package_code="start",
        provider=PaymentProvider.yookassa,
        provider_payment_id="yk-1",
        amount=149,
        currency="RUB",
        status=PaymentStatus.pending,
        idempotence_key=str(uuid.uuid4()),
        payload={"credits": 1000},
    )
    fields.update(overrides)
    payment = Payment(**fields)
    session.add(payment)
    await session.commit()
    return payment


async def test_activation_grants_credits_and_links_payment_via_metadata(session):
    user = await _make_user(session)
    payment = await _make_payment(session, user)

    result = await activate_paid_payment(session, payment_id=payment.id)

    assert result == ActivationResult(credits_granted=1000)
    fetched_user = await session.get(User, user.id)
    assert fetched_user.credits_balance == 1000
    assert fetched_user.total_credits_purchased == 1000
    assert payment.status == PaymentStatus.succeeded
    assert payment.paid_at is not None

    tx = (await session.execute(select(CreditTransaction))).scalar_one()
    assert tx.type == CreditTxType.purchase
    assert tx.amount == 1000
    assert tx.description == "credit package start"
    assert tx.metadata_json == {"payment_id": payment.id}


async def test_second_activation_is_noop(session):
    user = await _make_user(session)
    payment = await _make_payment(session, user)

    first = await activate_paid_payment(session, payment_id=payment.id)
    second = await activate_paid_payment(session, payment_id=payment.id)

    assert first is not None
    assert second is None
    tx_count = (
        await session.execute(select(func.count()).select_from(CreditTransaction))
    ).scalar_one()
    assert tx_count == 1
    fetched_user = await session.get(User, user.id)
    assert fetched_user.credits_balance == 1000


async def test_activation_by_provider_and_provider_payment_id(session):
    user = await _make_user(session)
    await _make_payment(session, user, provider_payment_id="yk-webhook-7")

    result = await activate_paid_payment(
        session, provider=PaymentProvider.yookassa, provider_payment_id="yk-webhook-7"
    )

    assert result is not None
    assert result.credits_granted == 1000


async def test_charge_id_overwrites_provider_payment_id(session):
    user = await _make_user(session)
    payment = await _make_payment(
        session, user,
        provider=PaymentProvider.telegram_stars, provider_payment_id=None,
        currency="XTR", amount=75, status=PaymentStatus.created,
    )

    result = await activate_paid_payment(session, payment_id=payment.id, charge_id="stars-charge-1")

    assert result is not None
    assert payment.provider_payment_id == "stars-charge-1"


async def test_unknown_payment_returns_none(session):
    assert await activate_paid_payment(session, payment_id=999) is None


async def test_requires_payment_identifier(session):
    with pytest.raises(ValueError):
        await activate_paid_payment(session)


async def test_activation_result_has_no_subscription_field():
    assert not hasattr(ActivationResult(), "subscription")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/payments/test_activation.py -v`
Expected: FAIL at collection — `ImportError` (current `activation.py` imports deleted `Subscription`/`Tariff`/`UsageLimit` and nonexistent `app.services.subscription_service`).

- [ ] **Step 3: Rewrite `app/services/payments/activation.py`** (full replacement)

```python
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import Payment
from app.services.credit_service import grant_credits


@dataclass
class ActivationResult:
    credits_granted: int = 0


async def activate_paid_payment(
    session: AsyncSession,
    *,
    payment_id: int | None = None,
    provider: PaymentProvider | None = None,
    provider_payment_id: str | None = None,
    charge_id: str | None = None,
) -> ActivationResult | None:
    """Единая идемпотентная активация оплаты пакета кредитов
    (Stars/ЮKassa/crypto/manual).

    Один и тот же платёж не может активироваться дважды: платёж выбирается с
    блокировкой строки (FOR UPDATE), и если он уже succeeded -- возвращается
    None без побочных эффектов. Связь платёж→начисление живёт в
    credit_transactions.metadata_json["payment_id"] (дизайн фазы 1).
    """
    query = select(Payment).with_for_update()
    if payment_id is not None:
        query = query.where(Payment.id == payment_id)
    elif provider is not None and provider_payment_id is not None:
        query = query.where(
            Payment.provider == provider, Payment.provider_payment_id == provider_payment_id
        )
    else:
        raise ValueError("provide payment_id or (provider, provider_payment_id)")

    payment = (await session.execute(query)).scalar_one_or_none()
    if payment is None or payment.status == PaymentStatus.succeeded:
        return None

    payment.status = PaymentStatus.succeeded
    payment.paid_at = datetime.now(timezone.utc)
    if charge_id:
        payment.provider_payment_id = charge_id

    credits = int((payment.payload or {}).get("credits", 0))
    if credits > 0:
        await grant_credits(
            session,
            payment.user_id,
            credits,
            reason=f"credit package {payment.credit_package_code}",
            metadata={"payment_id": payment.id},
        )

    await session.commit()
    return ActivationResult(credits_granted=credits)
```

Notes locked in by this task: the `SELECT ... FOR UPDATE` + `status == succeeded` idempotency check is byte-for-byte the phase-old pattern; `tx_type` is the default `CreditTxType.purchase`; a payment with a missing/zero `payload["credits"]` is still marked succeeded (so it can't be re-activated in a loop) but grants nothing and returns `ActivationResult(credits_granted=0)` — callers treat `credits_granted == 0` as "nothing to notify about".

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/payments/test_activation.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/payments/activation.py tests/services/payments/__init__.py tests/services/payments/test_activation.py
git commit -m "feat(phase4): rewrite payment activation as credit-package-only idempotent grant"
```

---

### Task 4: Gateway ABC + YooKassa + Stars under the DB `CreditPackage`

**Files:**
- Modify: `app/services/payments/gateway.py`
- Rewrite: `app/services/payments/yookassa_service.py`
- Rewrite: `app/services/payments/stars_service.py`
- Test: `tests/services/payments/test_gateway.py` (new)

**Interfaces:**
- Consumes: Task 1's `CreditPackage` (fields: `code`, `title`, `credits`, `price_rub`, `price_stars`, `is_active`) and `Payment` without `tariff_id`.
- Produces (used by Tasks 5, 7, 8):
  - `PaymentCreateResult(payment: Payment, kind: Literal["external_url", "telegram_invoice"], confirmation_url: str | None = None, invoice_link: str | None = None)` — unchanged shape.
  - ABC `PaymentGateway` with exactly 3 abstract methods: `create_credit_payment(session, user: User, package: CreditPackage) -> PaymentCreateResult`, `check_payment_status(session, payment) -> PaymentStatus`, `refund_payment(session, payment) -> bool`. `create_payment` (tariff) is GONE.
  - `GATEWAYS: dict[PaymentProvider, PaymentGateway]`, `register_gateway(gateway)` — unchanged.
  - Classes `YooKassaPaymentService` (provider `yookassa`), `TelegramStarsPaymentService` (provider `telegram_stars`).

- [ ] **Step 1: Write the failing tests**

Create `tests/services/payments/test_gateway.py`:

```python
"""Гейтвеи под новой DB-моделью CreditPackage. Внешние границы замоканы по
принятому в проекте паттерну (hand-rolled фейки + monkeypatch):
- yookassa SDK: подмена модульного имени yookassa_service.YooPaymentAPI фейком;
  SDK синхронный и зовётся через asyncio.to_thread, поэтому фейк -- обычные
  синхронные методы;
- aiogram: подмена stars_service.bot объектом с AsyncMock-методами.
"""
import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User
from app.services.payments import stars_service, yookassa_service
from app.services.payments.gateway import PaymentGateway


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def user_and_package(session):
    user = User(id=1, telegram_id=111, username="u")
    package = CreditPackage(code="start", title="START", credits=1000, price_rub=149, price_stars=75)
    session.add_all([user, package])
    await session.commit()
    return user, package


class FakeYooPaymentAPI:
    def __init__(self, status: str = "pending"):
        self.status = status
        self.create_calls: list[tuple[dict, str]] = []

    def create(self, payload: dict, idempotence_key: str):
        self.create_calls.append((payload, idempotence_key))
        return SimpleNamespace(
            id="yk-123",
            status=self.status,
            confirmation=SimpleNamespace(confirmation_url="https://yookassa.example/confirm"),
        )

    def find_one(self, provider_payment_id: str):
        return SimpleNamespace(status=self.status)


@pytest.fixture
def fake_bot(monkeypatch):
    bot = SimpleNamespace(
        create_invoice_link=AsyncMock(return_value="https://t.me/invoice/1"),
        refund_star_payment=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(stars_service, "bot", bot)
    return bot


# --- интерфейс ---

def test_gateway_abc_has_no_tariff_create_payment():
    assert not hasattr(PaymentGateway, "create_payment")
    abstract = PaymentGateway.__abstractmethods__
    assert abstract == {"create_credit_payment", "check_payment_status", "refund_payment"}


# --- YooKassa ---

async def test_yookassa_create_credit_payment_uses_title_and_rub_price(
    session, user_and_package, monkeypatch
):
    user, package = user_and_package
    fake = FakeYooPaymentAPI()
    monkeypatch.setattr(yookassa_service, "YooPaymentAPI", fake)

    service = yookassa_service.YooKassaPaymentService()
    result = await service.create_credit_payment(session, user, package)

    payment = result.payment
    assert result.kind == "external_url"
    assert result.confirmation_url == "https://yookassa.example/confirm"
    assert payment.provider == PaymentProvider.yookassa
    assert payment.credit_package_code == "start"
    assert float(payment.amount) == 149
    assert payment.currency == "RUB"
    assert payment.payload == {"credits": 1000}
    assert payment.provider_payment_id == "yk-123"
    assert payment.status == PaymentStatus.pending
    assert payment.payment_url == "https://yookassa.example/confirm"

    [(api_payload, _idem_key)] = fake.create_calls
    assert api_payload["amount"]["value"] == "149.00"
    assert "START" in api_payload["description"]
    assert api_payload["metadata"]["credit_package_code"] == "start"
    assert api_payload["receipt"]["items"][0]["description"] == "START"


async def test_yookassa_check_payment_status_maps_provider_status(
    session, user_and_package, monkeypatch
):
    user, package = user_and_package
    monkeypatch.setattr(yookassa_service, "YooPaymentAPI", FakeYooPaymentAPI(status="succeeded"))

    service = yookassa_service.YooKassaPaymentService()
    payment = Payment(
        user_id=user.id, credit_package_code="start", provider=PaymentProvider.yookassa,
        provider_payment_id="yk-123", amount=149, currency="RUB",
        status=PaymentStatus.pending, idempotence_key="k1", payload={"credits": 1000},
    )
    session.add(payment)
    await session.commit()

    assert await service.check_payment_status(session, payment) == PaymentStatus.succeeded


# --- Telegram Stars ---

async def test_stars_create_credit_payment_uses_price_stars(session, user_and_package, fake_bot):
    user, package = user_and_package

    service = stars_service.TelegramStarsPaymentService()
    result = await service.create_credit_payment(session, user, package)

    payment = result.payment
    assert result.kind == "telegram_invoice"
    assert result.invoice_link == "https://t.me/invoice/1"
    assert payment.provider == PaymentProvider.telegram_stars
    assert payment.currency == "XTR"
    assert float(payment.amount) == 75
    assert payment.payload == {"credits": 1000}
    assert payment.payment_url == "https://t.me/invoice/1"

    kwargs = fake_bot.create_invoice_link.await_args.kwargs
    assert kwargs["title"] == "START"
    assert kwargs["currency"] == "XTR"
    assert kwargs["payload"] == str(payment.id)
    [price] = kwargs["prices"]
    assert price.amount == 75


async def test_stars_refund_calls_refund_star_payment(session, user_and_package, fake_bot):
    user, package = user_and_package
    payment = Payment(
        user_id=user.id, credit_package_code="start", provider=PaymentProvider.telegram_stars,
        provider_payment_id="chg-1", amount=75, currency="XTR",
        status=PaymentStatus.succeeded, idempotence_key="k2", payload={"credits": 1000},
    )
    session.add(payment)
    await session.commit()

    service = stars_service.TelegramStarsPaymentService()
    ok = await service.refund_payment(session, payment)

    assert ok is True
    assert payment.status == PaymentStatus.refunded
    fake_bot.refund_star_payment.assert_awaited_once_with(
        user_id=111, telegram_payment_charge_id="chg-1"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/payments/test_gateway.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'app.services.credit_packages'` (current gateway/services import the phase-1-deleted dataclass module).

- [ ] **Step 3: Implement `gateway.py`** (full replacement)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User


@dataclass
class PaymentCreateResult:
    payment: Payment
    kind: Literal["external_url", "telegram_invoice"]
    confirmation_url: str | None = None
    invoice_link: str | None = None


class PaymentGateway(ABC):
    provider: PaymentProvider

    @abstractmethod
    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult: ...

    @abstractmethod
    async def check_payment_status(self, session: AsyncSession, payment: Payment) -> PaymentStatus: ...

    @abstractmethod
    async def refund_payment(self, session: AsyncSession, payment: Payment) -> bool: ...


GATEWAYS: dict[PaymentProvider, PaymentGateway] = {}


def register_gateway(gateway: PaymentGateway) -> None:
    GATEWAYS[gateway.provider] = gateway
```

- [ ] **Step 4: Implement `yookassa_service.py`** (full replacement — `create_payment` removed; `package.title` instead of `package.name`; no `tariff_id` kwarg; everything else, including the receipt block and the `asyncio.to_thread` comment, kept)

```python
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from yookassa import Configuration
from yookassa import Payment as YooPaymentAPI
from yookassa import Refund as YooRefundAPI

from app.config import settings
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User
from app.services.payments.gateway import PaymentCreateResult, PaymentGateway

Configuration.configure(settings.yookassa_shop_id, settings.yookassa_secret_key)

_STATUS_MAP = {
    "pending": PaymentStatus.pending,
    "waiting_for_capture": PaymentStatus.pending,
    "succeeded": PaymentStatus.succeeded,
    "canceled": PaymentStatus.canceled,
}


class YooKassaPaymentService(PaymentGateway):
    provider = PaymentProvider.yookassa

    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult:
        idempotence_key = str(uuid.uuid4())
        payment = Payment(
            user_id=user.id,
            credit_package_code=package.code,
            provider=self.provider,
            amount=package.price_rub,
            currency="RUB",
            status=PaymentStatus.created,
            idempotence_key=idempotence_key,
            payload={"credits": package.credits},
        )
        session.add(payment)
        await session.commit()

        # yookassa SDK синхронный (requests) — уводим блокирующий HTTP-вызов в поток,
        # чтобы не стопорить event loop остальных пользователей.
        response = await asyncio.to_thread(
            YooPaymentAPI.create,
            {
                "amount": {"value": f"{package.price_rub:.2f}", "currency": "RUB"},
                "capture": True,
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{settings.payment_return_url}?payment_id={payment.id}",
                },
                "description": f"{package.title} ({package.credits} кредитов)",
                "metadata": {
                    "internal_payment_id": str(payment.id),
                    "telegram_id": str(user.telegram_id),
                    "credit_package_code": package.code,
                },
                "receipt": {
                    "customer": {"email": "support@ai-hub-bot.ru"},
                    "items": [
                        {
                            "description": package.title,
                            "quantity": "1.00",
                            "amount": {"value": f"{package.price_rub:.2f}", "currency": "RUB"},
                            "vat_code": 1,
                            "payment_subject": "service",
                            "payment_mode": "full_payment",
                        }
                    ],
                },
            },
            idempotence_key,
        )

        payment.provider_payment_id = response.id
        payment.payment_url = response.confirmation.confirmation_url
        payment.status = _STATUS_MAP.get(response.status, PaymentStatus.pending)
        await session.commit()

        return PaymentCreateResult(
            payment=payment, kind="external_url", confirmation_url=response.confirmation.confirmation_url
        )

    async def check_payment_status(self, session: AsyncSession, payment: Payment) -> PaymentStatus:
        if not payment.provider_payment_id:
            return payment.status
        response = await asyncio.to_thread(YooPaymentAPI.find_one, payment.provider_payment_id)
        return _STATUS_MAP.get(response.status, payment.status)

    async def refund_payment(self, session: AsyncSession, payment: Payment) -> bool:
        if not payment.provider_payment_id:
            return False

        await asyncio.to_thread(
            YooRefundAPI.create,
            {
                "amount": {"value": f"{payment.amount:.2f}", "currency": payment.currency},
                "payment_id": payment.provider_payment_id,
            },
        )
        payment.status = PaymentStatus.refunded
        await session.commit()
        return True
```

- [ ] **Step 5: Implement `stars_service.py`** (full replacement — `create_payment` removed; `package.title`; no `tariff_id` kwarg)

```python
import uuid

from aiogram.types import LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User
from app.services.payments.gateway import PaymentCreateResult, PaymentGateway


class TelegramStarsPaymentService(PaymentGateway):
    provider = PaymentProvider.telegram_stars

    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult:
        payment = Payment(
            user_id=user.id,
            credit_package_code=package.code,
            provider=self.provider,
            amount=package.price_stars,
            currency="XTR",
            status=PaymentStatus.created,
            idempotence_key=str(uuid.uuid4()),
            payload={"credits": package.credits},
        )
        session.add(payment)
        await session.commit()

        invoice_link = await bot.create_invoice_link(
            title=package.title,
            description=f"{package.credits} кредитов для AI-запросов",
            payload=str(payment.id),
            currency="XTR",
            prices=[LabeledPrice(label=package.title, amount=package.price_stars)],
        )
        payment.payment_url = invoice_link
        await session.commit()

        return PaymentCreateResult(payment=payment, kind="telegram_invoice", invoice_link=invoice_link)

    async def check_payment_status(self, session: AsyncSession, payment: Payment) -> PaymentStatus:
        # У Bot API нет pull-запроса статуса Stars-платежа — источник истины
        # это successful_payment/PreCheckoutQuery, обрабатываемые в bot/handlers/payments.py.
        return payment.status

    async def refund_payment(self, session: AsyncSession, payment: Payment) -> bool:
        if not payment.provider_payment_id:
            return False

        user = await session.get(User, payment.user_id)
        if user is None:
            return False

        ok = await bot.refund_star_payment(
            user_id=user.telegram_id, telegram_payment_charge_id=payment.provider_payment_id
        )
        if ok:
            payment.status = PaymentStatus.refunded
            await session.commit()
        return ok
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/services/payments/ -v`
Expected: PASS (gateway tests + Task 3's activation tests still green).

- [ ] **Step 7: Commit**

```bash
git add app/services/payments/gateway.py app/services/payments/yookassa_service.py app/services/payments/stars_service.py tests/services/payments/test_gateway.py
git commit -m "feat(phase4): gateways speak DB CreditPackage; tariff create_payment removed"
```

---

### Task 5: `CryptoPaymentGateway` stub + registration

Config note (verified against `app/config.py`): the stub needs NO new settings — there is no external API, wallet, or secret; the payment "URL" is a static manual-confirmation instruction constant. If a real processor arrives (post-phase-5), its settings get added then.

**Files:**
- Create: `app/services/payments/crypto_service.py`
- Modify: `app/services/payments/setup.py`
- Test: `tests/services/payments/test_gateway.py` (append)

**Interfaces:**
- Consumes: Task 4's `PaymentGateway` ABC and `PaymentCreateResult`; Task 1's `PaymentProvider.crypto`.
- Produces: `class CryptoPaymentGateway(PaymentGateway)` with `provider = PaymentProvider.crypto`; module constant `CRYPTO_PAYMENT_INSTRUCTION: str`; `register_all_gateways()` now registers 3 gateways — Task 7's `/payments/credits/crypto/create` and Task 8's worker import rely on this.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/payments/test_gateway.py`:

```python
# --- Crypto (заглушка) ---

from app.services.payments.crypto_service import CRYPTO_PAYMENT_INSTRUCTION, CryptoPaymentGateway


async def test_crypto_create_credit_payment_creates_manual_payment(session, user_and_package):
    user, package = user_and_package

    service = CryptoPaymentGateway()
    result = await service.create_credit_payment(session, user, package)

    payment = result.payment
    assert result.kind == "external_url"
    assert result.confirmation_url == CRYPTO_PAYMENT_INSTRUCTION
    assert payment.provider == PaymentProvider.crypto
    assert payment.credit_package_code == "start"
    assert float(payment.amount) == 149
    assert payment.currency == "RUB"
    assert payment.status == PaymentStatus.created
    assert payment.payload == {"credits": 1000}
    assert payment.payment_url == CRYPTO_PAYMENT_INSTRUCTION


async def test_crypto_check_payment_status_reads_db_status(session, user_and_package):
    user, package = user_and_package
    service = CryptoPaymentGateway()
    result = await service.create_credit_payment(session, user, package)

    assert await service.check_payment_status(session, result.payment) == PaymentStatus.created

    result.payment.status = PaymentStatus.succeeded
    await session.commit()
    assert await service.check_payment_status(session, result.payment) == PaymentStatus.succeeded


async def test_crypto_refund_raises_not_implemented(session, user_and_package):
    user, package = user_and_package
    service = CryptoPaymentGateway()
    result = await service.create_credit_payment(session, user, package)

    with pytest.raises(NotImplementedError):
        await service.refund_payment(session, result.payment)


def test_register_all_gateways_includes_all_three_providers():
    from app.services.payments.gateway import GATEWAYS
    from app.services.payments.setup import register_all_gateways

    register_all_gateways()
    assert {
        PaymentProvider.telegram_stars,
        PaymentProvider.yookassa,
        PaymentProvider.crypto,
    } <= set(GATEWAYS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/payments/test_gateway.py -v -k crypto`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'app.services.payments.crypto_service'`.

- [ ] **Step 3: Create `app/services/payments/crypto_service.py`**

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User
from app.services.payments.gateway import PaymentCreateResult, PaymentGateway

# Заглушка (фаза 4): интеграции с реальным крипто-процессором нет.
# Подтверждение оплаты -- ручное: админ начисляет кредиты через grant_credits
# напрямую (или через admin-команду фазы 5), автоматического webhook нет.
CRYPTO_PAYMENT_INSTRUCTION = (
    "Оплата криптовалютой подтверждается вручную: напишите в поддержку "
    "и укажите номер платежа."
)


class CryptoPaymentGateway(PaymentGateway):
    provider = PaymentProvider.crypto

    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult:
        payment = Payment(
            user_id=user.id,
            credit_package_code=package.code,
            provider=self.provider,
            amount=package.price_rub,  # номинал в рублях; реальный курс -- дело процессора (вне фазы 4)
            currency="RUB",
            status=PaymentStatus.created,
            idempotence_key=str(uuid.uuid4()),
            payload={"credits": package.credits},
            payment_url=CRYPTO_PAYMENT_INSTRUCTION,
        )
        session.add(payment)
        await session.commit()

        return PaymentCreateResult(
            payment=payment, kind="external_url", confirmation_url=CRYPTO_PAYMENT_INSTRUCTION
        )

    async def check_payment_status(self, session: AsyncSession, payment: Payment) -> PaymentStatus:
        # Внешнего API нет -- источник истины это текущий статус в БД
        # (меняется активацией/админом, не этим методом).
        return payment.status

    async def refund_payment(self, session: AsyncSession, payment: Payment) -> bool:
        # Возвраты возможны только вручную, пока не подключён реальный
        # крипто-процессор (вне рамок фазы 4; admin-инструменты -- фаза 5).
        raise NotImplementedError(
            "crypto refunds are manual until a real processor is integrated"
        )
```

- [ ] **Step 4: Register it in `app/services/payments/setup.py`** (full replacement)

```python
from app.services.payments.crypto_service import CryptoPaymentGateway
from app.services.payments.gateway import register_gateway
from app.services.payments.stars_service import TelegramStarsPaymentService
from app.services.payments.yookassa_service import YooKassaPaymentService


def register_all_gateways() -> None:
    register_gateway(TelegramStarsPaymentService())
    register_gateway(YooKassaPaymentService())
    register_gateway(CryptoPaymentGateway())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/services/payments/test_gateway.py -v`
Expected: PASS (all, including Task 4's tests).

- [ ] **Step 6: Commit**

```bash
git add app/services/payments/crypto_service.py app/services/payments/setup.py tests/services/payments/test_gateway.py
git commit -m "feat(phase4): CryptoPaymentGateway stub with manual confirmation"
```

---

### Task 6: Strip subscription branches — webhook, bot handler, notifications

No new test files (the spec's Testing section does not list webhook/handler tests; the dead-symbol assertions land in `tests/test_worker.py`, Task 8). Verification here = imports succeed + greps come back empty + prior suites stay green.

**Files:**
- Rewrite: `app/webhooks/yookassa.py`
- Modify: `app/bot/handlers/payments.py:41-48`
- Modify: `app/services/notification_service.py` (delete `notify_payment_success`, `notify_subscription_expiring`, `notify_subscription_expired`, and the now-unused `from datetime import datetime` import)

**Interfaces:**
- Consumes: Task 3's `ActivationResult(credits_granted)`; Task 4's `GATEWAYS`.
- Produces: `app.services.notification_service` exposes ONLY `_send` and `notify_credits_purchase(telegram_id: int, credits: int) -> None` — Task 8's worker imports `notify_credits_purchase`.

- [ ] **Step 1: Rewrite `app/webhooks/yookassa.py`** (full replacement — subscription branch, `Tariff` import, and `notify_payment_success` import removed; everything else, including the "don't trust the webhook body" re-check, kept)

```python
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import Payment, User
from app.db.session import get_session
from app.services.notification_service import notify_credits_purchase
from app.services.payments import GATEWAYS
from app.services.payments.activation import activate_paid_payment

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhooks/yookassa")
async def yookassa_webhook(request: Request) -> dict:
    payload = await request.json()
    object_id = (payload.get("object") or {}).get("id")
    if not object_id:
        logger.warning("yookassa webhook without object.id: %s", payload)
        return {"ok": True}

    async with get_session() as session:
        payment = (
            await session.execute(
                select(Payment).where(
                    Payment.provider == PaymentProvider.yookassa,
                    Payment.provider_payment_id == object_id,
                )
            )
        ).scalar_one_or_none()

        if payment is None:
            logger.warning("yookassa webhook for unknown payment %s", object_id)
            return {"ok": True}

        if payment.status == PaymentStatus.succeeded:
            return {"ok": True}

        try:
            # Не доверяем телу webhook — перечитываем статус напрямую из API ЮKassa.
            real_status = await GATEWAYS[PaymentProvider.yookassa].check_payment_status(session, payment)
        except Exception as exc:
            logger.exception("failed to verify yookassa payment %s", object_id)
            raise HTTPException(status_code=500) from exc

        if real_status == PaymentStatus.succeeded:
            result = await activate_paid_payment(
                session, provider=PaymentProvider.yookassa, provider_payment_id=object_id
            )
            logger.info("yookassa payment %s activated -> result=%s", object_id, result)

            if result and result.credits_granted:
                user = await session.get(User, payment.user_id)
                if user:
                    await notify_credits_purchase(user.telegram_id, result.credits_granted)
        elif real_status == PaymentStatus.canceled:
            payment.status = PaymentStatus.canceled
            await session.commit()

    return {"ok": True}
```

- [ ] **Step 2: Trim `app/bot/handlers/payments.py`**

Replace the tail of `handle_successful_payment` (the `if result is None / elif result.subscription / elif result.credits_granted` block) with:

```python
    if result is None:
        await message.answer("Оплата получена, но уже была обработана ранее.")
    elif result.credits_granted:
        await message.answer(f"✅ Оплата прошла! Начислено {result.credits_granted} кредитов.")
```

Nothing else in the file changes (`handle_pre_checkout` is already tariff-free).

- [ ] **Step 3: Trim `app/services/notification_service.py`** (full replacement)

```python
from app.bot.instance import bot
from app.bot.keyboards import webapp_open_kb
from app.config import settings


async def _send(telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(
            telegram_id, text, reply_markup=webapp_open_kb("Открыть AI Hub", settings.frontend_url)
        )
    except Exception:
        # Пользователь мог заблокировать бота -- не критично.
        pass


async def notify_credits_purchase(telegram_id: int, credits: int) -> None:
    await _send(telegram_id, f"✅ Оплата прошла! Начислено {credits} кредитов.")
```

- [ ] **Step 4: Verify imports and absence of dead references**

Run (bash):
```bash
BOT_TOKEN="123456:TEST-token" DATABASE_URL="postgresql+asyncpg://test" python -c "import app.webhooks.yookassa, app.bot.handlers.payments, app.services.notification_service; print('imports ok')"
```
Expected: `imports ok`

Run: `grep -rn "result.subscription\|notify_payment_success\|notify_subscription" app/webhooks app/bot app/services/notification_service.py`
Expected: no matches. (Do NOT grep all of `app/` yet — `app/worker.py` still references the deleted notification functions until Task 8; the whole-tree sweep happens in Task 9.)

Run: `python -m pytest tests/services/payments/ tests/services/test_credit_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/webhooks/yookassa.py app/bot/handlers/payments.py app/services/notification_service.py
git commit -m "feat(phase4): credits-only yookassa webhook, stars handler, notifications"
```

---

### Task 7: Rewrite `app/api/routes/payments.py` + API tests

**Files:**
- Rewrite: `app/api/routes/payments.py`
- Test: `tests/api/test_payments_routes.py` (new — the old payments coverage was already non-functional; there is no existing payments test file to replace)

**Interfaces:**
- Consumes: Task 4/5's `GATEWAYS` and `create_credit_payment(session, user, package)`; Task 1's `CreditPackage`; existing deps `current_user`, `get_db` from `app/api/deps.py`.
- Produces (API contract per spec, mounted by the untouched `app/main.py` under `/api`):
  - `GET /api/credits/packages` → `list[CreditPackageOut]`, `CreditPackageOut(code: str, title: str, credits: int, price_rub: float, price_stars: int)` — active packages from the DB, ordered by `price_rub`.
  - `POST /api/payments/credits/{yookassa,stars,crypto}/create` with body `{"package_code": str}` → `CreatePaymentResponse(payment_id: int, invoice_link: str | None, confirmation_url: str | None)`.
  - `GET /api/payments/{payment_id}/status` → `PaymentStatusOut(payment_id, status)` — unchanged contract.
  - `GET /api/payments/history` → `list[PaymentHistoryItem(id, provider, amount, currency, status, created_at)]` — unchanged contract.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_payments_routes.py`:

```python
import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
# postgresql+asyncpg:// (не голый postgresql://): app.api.deps -> app.db.session
# строит create_async_engine при импорте модуля.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_user, get_db
from app.api.routes import payments as payments_routes
from app.db.base import Base
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User
from app.services.payments import GATEWAYS, PaymentCreateResult

# app.main не импортируем (admin чинится в фазе 5) -- минимальное приложение
# из тестируемого роутера, как в tests/api/test_generate_routes.py.
app = FastAPI()
app.include_router(payments_routes.router, prefix="/api")

_test_user = User(
    id=1, telegram_id=1, username="u", first_name="U", is_admin=False,
    default_model_code=None, credits_balance=0,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_user():
    return _test_user


class FakeGateway:
    """Пишет реальный Payment в БД (роуту нужен payment.id), внешних вызовов нет."""

    def __init__(self, provider: PaymentProvider, kind: str = "external_url", fail: bool = False):
        self.provider = provider
        self.kind = kind
        self.fail = fail
        self.calls: list[str] = []

    async def create_credit_payment(self, session, user, package):
        if self.fail:
            raise RuntimeError("gateway boom")
        self.calls.append(package.code)
        payment = Payment(
            user_id=user.id, credit_package_code=package.code, provider=self.provider,
            amount=package.price_rub, currency="RUB", status=PaymentStatus.created,
            idempotence_key=str(uuid.uuid4()), payload={"credits": package.credits},
        )
        session.add(payment)
        await session.commit()
        if self.kind == "telegram_invoice":
            return PaymentCreateResult(
                payment=payment, kind="telegram_invoice", invoice_link="https://t.me/invoice/1"
            )
        return PaymentCreateResult(
            payment=payment, kind="external_url", confirmation_url="https://pay.example/confirm"
        )

    async def check_payment_status(self, session, payment):
        return PaymentStatus.succeeded

    async def refund_payment(self, session, payment):
        return True


@pytest.fixture
async def db_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(User(id=1, telegram_id=1, username="u"))
        s.add(User(id=2, telegram_id=2, username="other"))
        s.add(CreditPackage(code="start", title="START", credits=1000, price_rub=149, price_stars=75))
        s.add(CreditPackage(code="basic", title="BASIC", credits=5000, price_rub=599, price_stars=300))
        s.add(CreditPackage(
            code="legacy", title="LEGACY", credits=1, price_rub=1, price_stars=1, is_active=False
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
    app.dependency_overrides[current_user] = _fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# --- GET /api/credits/packages ---

async def test_packages_returns_active_only_from_db(client):
    response = await client.get("/api/credits/packages")

    assert response.status_code == 200
    body = response.json()
    assert [p["code"] for p in body] == ["start", "basic"]  # inactive скрыт, сортировка по цене
    assert body[0] == {
        "code": "start", "title": "START", "credits": 1000, "price_rub": 149.0, "price_stars": 75,
    }


# --- POST /api/payments/credits/{provider}/create ---

async def test_create_stars_payment_returns_invoice_link(client, monkeypatch):
    fake = FakeGateway(PaymentProvider.telegram_stars, kind="telegram_invoice")
    monkeypatch.setitem(GATEWAYS, PaymentProvider.telegram_stars, fake)

    response = await client.post("/api/payments/credits/stars/create", json={"package_code": "start"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["payment_id"], int)
    assert body["invoice_link"] == "https://t.me/invoice/1"
    assert body["confirmation_url"] is None
    assert fake.calls == ["start"]


async def test_create_yookassa_payment_returns_confirmation_url(client, monkeypatch):
    fake = FakeGateway(PaymentProvider.yookassa)
    monkeypatch.setitem(GATEWAYS, PaymentProvider.yookassa, fake)

    response = await client.post("/api/payments/credits/yookassa/create", json={"package_code": "basic"})

    assert response.status_code == 200
    body = response.json()
    assert body["confirmation_url"] == "https://pay.example/confirm"
    assert body["invoice_link"] is None
    assert fake.calls == ["basic"]


async def test_create_crypto_payment_returns_confirmation_url(client, monkeypatch):
    fake = FakeGateway(PaymentProvider.crypto)
    monkeypatch.setitem(GATEWAYS, PaymentProvider.crypto, fake)

    response = await client.post("/api/payments/credits/crypto/create", json={"package_code": "start"})

    assert response.status_code == 200
    assert response.json()["confirmation_url"] == "https://pay.example/confirm"


async def test_create_unknown_package_is_404(client, monkeypatch):
    fake = FakeGateway(PaymentProvider.yookassa)
    monkeypatch.setitem(GATEWAYS, PaymentProvider.yookassa, fake)

    response = await client.post("/api/payments/credits/yookassa/create", json={"package_code": "nope"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Пакет кредитов не найден"
    assert fake.calls == []


async def test_create_inactive_package_is_404(client, monkeypatch):
    monkeypatch.setitem(GATEWAYS, PaymentProvider.yookassa, FakeGateway(PaymentProvider.yookassa))

    response = await client.post("/api/payments/credits/yookassa/create", json={"package_code": "legacy"})

    assert response.status_code == 404


async def test_gateway_failure_maps_to_502(client, monkeypatch):
    monkeypatch.setitem(
        GATEWAYS, PaymentProvider.yookassa, FakeGateway(PaymentProvider.yookassa, fail=True)
    )

    response = await client.post("/api/payments/credits/yookassa/create", json={"package_code": "start"})

    assert response.status_code == 502
    assert response.json()["detail"] == "Не удалось создать платёж, попробуйте позже"


async def test_removed_tariff_endpoints_are_gone(client):
    assert (await client.post("/api/payments/stars/create", json={"tariff_code": "x"})).status_code == 404
    assert (await client.post("/api/payments/yookassa/create", json={"tariff_code": "x"})).status_code == 404


# --- GET /api/payments/{id}/status ---

async def test_status_returns_gateway_status(client, db_sessionmaker, monkeypatch):
    monkeypatch.setitem(GATEWAYS, PaymentProvider.yookassa, FakeGateway(PaymentProvider.yookassa))
    async with db_sessionmaker() as s:
        payment = Payment(
            user_id=1, credit_package_code="start", provider=PaymentProvider.yookassa,
            amount=149, currency="RUB", status=PaymentStatus.pending,
            idempotence_key=str(uuid.uuid4()), payload={"credits": 1000},
        )
        s.add(payment)
        await s.commit()
        payment_id = payment.id

    response = await client.get(f"/api/payments/{payment_id}/status")

    assert response.status_code == 200
    assert response.json() == {"payment_id": payment_id, "status": "succeeded"}


async def test_status_404_for_foreign_payment(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        payment = Payment(
            user_id=2, credit_package_code="start", provider=PaymentProvider.yookassa,
            amount=149, currency="RUB", status=PaymentStatus.pending,
            idempotence_key=str(uuid.uuid4()), payload={"credits": 1000},
        )
        s.add(payment)
        await s.commit()
        payment_id = payment.id

    response = await client.get(f"/api/payments/{payment_id}/status")

    assert response.status_code == 404


# --- GET /api/payments/history ---

async def test_history_returns_own_payments_newest_first(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        for i in range(2):
            s.add(Payment(
                user_id=1, credit_package_code="start", provider=PaymentProvider.telegram_stars,
                amount=75, currency="XTR", status=PaymentStatus.succeeded,
                idempotence_key=str(uuid.uuid4()), payload={"credits": 1000},
            ))
        s.add(Payment(
            user_id=2, credit_package_code="start", provider=PaymentProvider.yookassa,
            amount=149, currency="RUB", status=PaymentStatus.pending,
            idempotence_key=str(uuid.uuid4()), payload={"credits": 1000},
        ))
        await s.commit()

    response = await client.get("/api/payments/history")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2  # только свои
    assert {item["provider"] for item in body} == {"telegram_stars"}
    assert set(body[0]) == {"id", "provider", "amount", "currency", "status", "created_at"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_payments_routes.py -v`
Expected: FAIL at collection — current `app/api/routes/payments.py` imports the deleted `app.services.credit_packages` and `app.services.subscription_service` (`ModuleNotFoundError`).

- [ ] **Step 3: Rewrite `app/api/routes/payments.py`** (full replacement)

```python
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.enums import PaymentProvider
from app.db.models import CreditPackage, Payment, User
from app.services.payments import GATEWAYS

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(current_user)])


class CreditPackageOut(BaseModel):
    code: str
    title: str
    credits: int
    price_rub: float
    price_stars: int


class CreateCreditPaymentRequest(BaseModel):
    package_code: str


class CreatePaymentResponse(BaseModel):
    payment_id: int
    invoice_link: str | None = None
    confirmation_url: str | None = None


class PaymentStatusOut(BaseModel):
    payment_id: int
    status: str


class PaymentHistoryItem(BaseModel):
    id: int
    provider: str
    amount: float
    currency: str
    status: str
    created_at: str


@router.get("/credits/packages", response_model=list[CreditPackageOut])
async def get_credit_packages(session: AsyncSession = Depends(get_db)) -> list[CreditPackageOut]:
    packages = (
        await session.execute(
            select(CreditPackage)
            .where(CreditPackage.is_active.is_(True))
            .order_by(CreditPackage.price_rub)
        )
    ).scalars().all()
    return [
        CreditPackageOut(
            code=p.code, title=p.title, credits=p.credits,
            price_rub=float(p.price_rub), price_stars=p.price_stars,
        )
        for p in packages
    ]


async def _get_credit_package_or_404(session: AsyncSession, package_code: str) -> CreditPackage:
    package = (
        await session.execute(
            select(CreditPackage).where(
                CreditPackage.code == package_code, CreditPackage.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="Пакет кредитов не найден")
    return package


async def _create_credit_payment(
    provider: PaymentProvider, package_code: str, user: User, session: AsyncSession
) -> CreatePaymentResponse:
    package = await _get_credit_package_or_404(session, package_code)
    try:
        result = await GATEWAYS[provider].create_credit_payment(session, user, package)
    except Exception:
        logger.exception("%s create_credit_payment failed", provider.value)
        raise HTTPException(status_code=502, detail="Не удалось создать платёж, попробуйте позже")

    return CreatePaymentResponse(
        payment_id=result.payment.id,
        invoice_link=result.invoice_link,
        confirmation_url=result.confirmation_url,
    )


@router.post("/payments/credits/stars/create", response_model=CreatePaymentResponse)
async def create_stars_credit_payment(
    body: CreateCreditPaymentRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    return await _create_credit_payment(PaymentProvider.telegram_stars, body.package_code, user, session)


@router.post("/payments/credits/yookassa/create", response_model=CreatePaymentResponse)
async def create_yookassa_credit_payment(
    body: CreateCreditPaymentRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    return await _create_credit_payment(PaymentProvider.yookassa, body.package_code, user, session)


@router.post("/payments/credits/crypto/create", response_model=CreatePaymentResponse)
async def create_crypto_credit_payment(
    body: CreateCreditPaymentRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    return await _create_credit_payment(PaymentProvider.crypto, body.package_code, user, session)


@router.get("/payments/{payment_id}/status", response_model=PaymentStatusOut)
async def get_payment_status(
    payment_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> PaymentStatusOut:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Платёж не найден")

    gateway = GATEWAYS.get(payment.provider)
    status = await gateway.check_payment_status(session, payment) if gateway else payment.status
    return PaymentStatusOut(payment_id=payment.id, status=status.value)


@router.get("/payments/history", response_model=list[PaymentHistoryItem])
async def get_payment_history(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[PaymentHistoryItem]:
    payments = (
        await session.execute(
            select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(50)
        )
    ).scalars().all()

    return [
        PaymentHistoryItem(
            id=p.id,
            provider=p.provider.value,
            amount=float(p.amount),
            currency=p.currency,
            status=p.status.value,
            created_at=p.created_at.isoformat(),
        )
        for p in payments
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_payments_routes.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/payments.py tests/api/test_payments_routes.py
git commit -m "feat(phase4): DB-backed credit packages API, crypto create endpoint, tariff endpoints removed"
```

---

### Task 8: Fix `app/worker.py` + wire in the phase-3 reconciliation sweep

**Files:**
- Rewrite: `app/worker.py`
- Modify: `app/services/media_generation_service.py:275-277` (stale docstring paragraph only)
- Test: `tests/test_worker.py` (new)

**Interfaces:**
- Consumes: Task 3's `activate_paid_payment`/`ActivationResult(credits_granted)`; Task 5's `register_all_gateways` (3 gateways); Task 6's `notify_credits_purchase(telegram_id, credits)`; phase 3's `refund_stale_reserved_requests(session: AsyncSession, *, older_than_minutes: int = RECONCILE_STALE_AFTER_MINUTES) -> int` from `app/services/media_generation_service.py`.
- Produces: `poll_pending_yookassa_payments()`, `cancel_stale_created_payments()`, `reconcile_stale_media_reserves()`, `create_scheduler() -> AsyncIOScheduler` with exactly 3 jobs (ids `poll_pending_yookassa` @2min, `cancel_stale_created_payments` @24h, `reconcile_stale_media_reserves` @5min — spec allows 5–10min).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_worker.py`:

```python
import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.worker as worker
from app.db.base import Base
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import Payment, User


@pytest.fixture
async def db_sessionmaker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _test_session():
        async with maker() as s:
            yield s

    # worker открывает сессии через get_session (вне DI) -- подменяем её,
    # тот же приём, что и для fal-вебхука в tests/api/test_generate_routes.py.
    monkeypatch.setattr(worker, "get_session", _test_session)
    yield maker
    await engine.dispose()


def _pending_payment(minutes_old: int = 10, credits: int = 1000) -> Payment:
    return Payment(
        user_id=1, credit_package_code="start", provider=PaymentProvider.yookassa,
        provider_payment_id="yk-1", amount=149, currency="RUB",
        status=PaymentStatus.pending, idempotence_key=str(uuid.uuid4()),
        payload={"credits": credits},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_old),
    )


class FakeYooGateway:
    def __init__(self, status):
        self.status = status

    async def check_payment_status(self, session, payment):
        if isinstance(self.status, Exception):
            raise self.status
        return self.status


# --- poll_pending_yookassa_payments ---

async def test_poll_activates_succeeded_payment_and_notifies(db_sessionmaker, monkeypatch):
    async with db_sessionmaker() as s:
        s.add(User(id=1, telegram_id=111, username="u", credits_balance=0))
        s.add(_pending_payment())
        await s.commit()

    monkeypatch.setitem(
        worker.GATEWAYS, PaymentProvider.yookassa, FakeYooGateway(PaymentStatus.succeeded)
    )
    notify = AsyncMock()
    monkeypatch.setattr(worker, "notify_credits_purchase", notify)

    await worker.poll_pending_yookassa_payments()

    async with db_sessionmaker() as s:
        user = await s.get(User, 1)
        assert user.credits_balance == 1000
        payment = await s.get(Payment, 1)
        assert payment.status == PaymentStatus.succeeded
    notify.assert_awaited_once_with(111, 1000)


async def test_poll_marks_canceled_payment(db_sessionmaker, monkeypatch):
    async with db_sessionmaker() as s:
        s.add(User(id=1, telegram_id=111, username="u"))
        s.add(_pending_payment())
        await s.commit()

    monkeypatch.setitem(
        worker.GATEWAYS, PaymentProvider.yookassa, FakeYooGateway(PaymentStatus.canceled)
    )
    monkeypatch.setattr(worker, "notify_credits_purchase", AsyncMock())

    await worker.poll_pending_yookassa_payments()

    async with db_sessionmaker() as s:
        payment = await s.get(Payment, 1)
        assert payment.status == PaymentStatus.canceled


async def test_poll_skips_payment_on_gateway_error(db_sessionmaker, monkeypatch):
    async with db_sessionmaker() as s:
        s.add(User(id=1, telegram_id=111, username="u", credits_balance=0))
        s.add(_pending_payment())
        await s.commit()

    monkeypatch.setitem(
        worker.GATEWAYS, PaymentProvider.yookassa, FakeYooGateway(RuntimeError("api down"))
    )
    notify = AsyncMock()
    monkeypatch.setattr(worker, "notify_credits_purchase", notify)

    await worker.poll_pending_yookassa_payments()  # не должно упасть

    async with db_sessionmaker() as s:
        payment = await s.get(Payment, 1)
        assert payment.status == PaymentStatus.pending
    notify.assert_not_awaited()


# --- reconcile_stale_media_reserves ---

async def test_reconcile_calls_refund_stale_reserved_requests(db_sessionmaker, monkeypatch):
    refund = AsyncMock(return_value=2)
    monkeypatch.setattr(worker, "refund_stale_reserved_requests", refund)

    await worker.reconcile_stale_media_reserves()

    assert refund.await_count == 1


# --- расписание ---

def test_scheduler_has_exactly_three_jobs():
    scheduler = worker.create_scheduler()
    ids = {job.id for job in scheduler.get_jobs()}
    assert ids == {
        "poll_pending_yookassa",
        "cancel_stale_created_payments",
        "reconcile_stale_media_reserves",
    }


def test_subscription_era_symbols_are_gone():
    import app.services.notification_service as ns

    assert not hasattr(worker, "expire_subscriptions")
    assert not hasattr(worker, "warn_expiring_subscriptions")
    for legacy in ("notify_payment_success", "notify_subscription_expiring", "notify_subscription_expired"):
        assert not hasattr(ns, legacy)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_worker.py -v`
Expected: FAIL at collection — current `app/worker.py` imports deleted `Subscription`/`Tariff` from `app.db.models` (`ImportError`).

- [ ] **Step 3: Rewrite `app/worker.py`** (full replacement)

```python
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import Payment, User
from app.db.session import get_session
from app.services.media_generation_service import refund_stale_reserved_requests
from app.services.notification_service import notify_credits_purchase
from app.services.payments import GATEWAYS
from app.services.payments.activation import activate_paid_payment
from app.services.payments.setup import register_all_gateways

logger = logging.getLogger(__name__)

register_all_gateways()


async def poll_pending_yookassa_payments() -> None:
    """Страховка на случай потерянного webhook ЮKassa: опрашиваем зависшие
    pending-платежи и активируем оплаченные (только пакеты кредитов, фаза 4)."""
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        pending = (
            await session.execute(
                select(Payment).where(
                    Payment.provider == PaymentProvider.yookassa,
                    Payment.status == PaymentStatus.pending,
                    Payment.created_at < now - timedelta(minutes=3),
                    Payment.created_at > now - timedelta(hours=24),
                )
            )
        ).scalars().all()

        gateway = GATEWAYS[PaymentProvider.yookassa]
        for payment in pending:
            try:
                real_status = await gateway.check_payment_status(session, payment)
            except Exception:
                logger.exception("poll: failed to check yookassa payment %s", payment.id)
                continue

            if real_status == PaymentStatus.succeeded:
                result = await activate_paid_payment(session, payment_id=payment.id)
                if result and result.credits_granted:
                    user = await session.get(User, payment.user_id)
                    if user:
                        await notify_credits_purchase(user.telegram_id, result.credits_granted)
            elif real_status == PaymentStatus.canceled:
                payment.status = PaymentStatus.canceled
                await session.commit()


async def cancel_stale_created_payments() -> None:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        stale = (
            await session.execute(
                select(Payment).where(
                    Payment.status == PaymentStatus.created,
                    Payment.created_at < now - timedelta(hours=24),
                )
            )
        ).scalars().all()

        for payment in stale:
            payment.status = PaymentStatus.canceled

        if stale:
            await session.commit()


async def reconcile_stale_media_reserves() -> None:
    """Возврат кредитов за image/video-запросы, по которым вебхук fal.ai так и
    не пришёл (фаза 3 оставила refund_stale_reserved_requests готовой к
    подключению сюда; сама функция коммитит транзакцию)."""
    async with get_session() as session:
        refunded = await refund_stale_reserved_requests(session)
    if refunded:
        logger.info("reconcile: refunded %d stale media reserves", refunded)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll_pending_yookassa_payments, "interval", minutes=2, id="poll_pending_yookassa")
    scheduler.add_job(cancel_stale_created_payments, "interval", hours=24, id="cancel_stale_created_payments")
    scheduler.add_job(reconcile_stale_media_reserves, "interval", minutes=5, id="reconcile_stale_media_reserves")
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("worker started")
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Update the stale docstring in `app/services/media_generation_service.py`**

In the docstring of `refund_stale_reserved_requests`, replace this paragraph:

```
    Запускается периодически (см. TODO в app/worker.py -- сам worker.py сейчас
    сломан импортами удалённых Tariff/Subscription, чинится в фазах 4-5;
    функция уже готова к подключению туда, как только это исправят).
```

with:

```
    Запускается периодически из app/worker.py (job reconcile_stale_media_reserves,
    подключён в фазе 4).
```

No code changes in this file — docstring only.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker.py tests/services/test_media_generation_service.py -v`
Expected: PASS (new worker tests; media service tests unaffected by the docstring edit).

- [ ] **Step 6: Commit**

```bash
git add app/worker.py app/services/media_generation_service.py tests/test_worker.py
git commit -m "feat(phase4): fix worker -- drop subscription jobs, credits-only poller, wire media-reserve reconciliation"
```

---

### Task 9: Final verification sweep

**Files:**
- No production changes. Fix-forward only if a check below fails.

**Interfaces:**
- Consumes: everything above.
- Produces: green suite + confirmation that no phase-4 file references subscription-era symbols.

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests -q`
Expected: ALL PASS, 0 failures (includes untouched phases 1–3 suites: pricing, credit service, text/media generation, chat/generate routes, seeds, schema).

- [ ] **Step 2: Sweep for dead subscription-era references in phase-4 scope**

Run:
```bash
grep -rn "result.subscription\|from app.services.credit_packages\|subscription_service" app/services/payments app/webhooks app/bot app/api/routes/payments.py app/worker.py app/services/notification_service.py
```
Expected: no matches.

Run: `grep -rln "Tariff\|UsageLimit" app/`
Expected: matches ONLY in `app/api/routes/admin.py`, `app/services/admin_service.py`, `app/services/stats_service.py` (explicitly phase-5 scope, untouched by this plan; `app/main.py` therefore still cannot be imported — unchanged, known status quo).

- [ ] **Step 3: Confirm migration chain one more time**

Run: `python -m alembic heads`
Expected: single head `e6f7a8b9c0d1 (head)`.

- [ ] **Step 4: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "fix(phase4): post-sweep corrections"
```

---

## Self-Review Record

- **Spec coverage:** Migration + `price_stars` seeds (Task 1) ✅; `PaymentProvider.crypto` (Task 1) ✅; activation rewrite with preserved idempotent claim + `metadata_json` payment link (Tasks 2–3) ✅; gateway ABC without `create_payment`, DB `CreditPackage` type (Task 4) ✅; YooKassa/Stars rewritten under `title`/`price_stars` (Task 4) ✅; `crypto_service.py` stub with `Payment(status=created)` + instruction in `payment_url`, status-from-DB, `NotImplementedError` refund, manual confirmation (Task 5) ✅; webhook + bot handler subscription branches removed (Task 6) ✅; API surface — DB-backed `/credits/packages` with `CreditPackageOut(code, title, credits, price_rub, price_stars)`, `POST /api/payments/credits/{yookassa,stars,crypto}/create` returning `{payment_id, invoice_link?, confirmation_url?}`, status/history contracts unchanged (Task 7) ✅; notification dead code removed, `notify_credits_purchase` kept as-is (Task 6) ✅; worker — subscription jobs deleted, poller on new `ActivationResult`, `cancel_stale_created_payments` untouched, `reconcile_stale_media_reserves` every 5 min (Task 8) ✅; all five spec-listed test files (Tasks 1, 2/3, 4/5, 7, 8) ✅. Out of scope per spec: real crypto processor, admin commands, frontend-next — not planned. ✅
- **Placeholder scan:** no TBD/TODO-later steps; every code step has full file or exact-diff content; the only "PLACEHOLDER" words are quotes of the spec's own placeholder-pricing convention. ✅
- **Type consistency:** `grant_credits(..., metadata: dict | None = None)` defined in Task 2 = consumed in Task 3; `ActivationResult(credits_granted: int = 0)` defined in Task 3 = consumed in Tasks 6/8; `create_credit_payment(session, user: User, package: CreditPackage) -> PaymentCreateResult` defined in Task 4 = implemented in Tasks 4/5, faked with the same signature in Tasks 7/8 tests; `refund_stale_reserved_requests(session, *, older_than_minutes=...) -> int` matches `app/services/media_generation_service.py:267-269`. ✅
