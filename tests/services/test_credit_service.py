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
    user_id = user.id  # captured before rollback: SELECT-then-rollback expires
    # ORM attributes on `user`, and re-reading `user.id` synchronously as a call
    # argument after that would trigger a sync lazy-load (MissingGreenlet) --
    # unrelated to credit_service's own logic, see task-5-report.md.

    with pytest.raises(InsufficientBalanceError) as exc_info:
        await reserve_credits(session, user_id, 150, request_id=None, provider="openrouter", model_code="m")

    assert exc_info.value.balance == 100
    assert exc_info.value.required == 150
    await session.rollback()
    fetched = await session.get(User, user_id)
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


async def test_settle_rejects_already_completed_request(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=40)
    user.credits_balance = 60

    await settle_request(session, request, actual_credits=25)
    await session.commit()
    assert user.credits_balance == 75  # состояние после первого (валидного) settle

    with pytest.raises(ValueError):
        await settle_request(session, request, actual_credits=25)

    assert user.credits_balance == 75  # повторный вызов не тронул баланс


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


async def test_refund_rejects_already_refunded_request(session):
    user = await _make_user(session, balance=100)
    request = await _make_reserved_request(session, user, reserved=40)
    user.credits_balance = 60

    await refund_request(session, request, reason="provider error")
    await session.commit()
    assert user.credits_balance == 100  # состояние после первого (валидного) refund

    with pytest.raises(ValueError):
        await refund_request(session, request, reason="retried webhook")

    assert user.credits_balance == 100  # повторный вызов не начислил кредиты ещё раз


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
