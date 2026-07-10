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
