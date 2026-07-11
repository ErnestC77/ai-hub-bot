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
from app.db.models import AIRequest, CreditTransaction, Payment, Setting, User
from app.services.stats_service import (
    DailyStats,
    ModelUsageStat,
    MonthlyStats,
    UserSpendStat,
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


def _request(user_id, *, status=RequestStatus.completed, provider_cost_usd=0,
             charged_credits=0, model_code="deepseek_v3", created_at=NOW):
    return AIRequest(
        user_id=user_id, provider="openrouter", model_code=model_code,
        category=ModelCategory.text, status=status, prompt_preview="p",
        provider_cost_usd=provider_cost_usd, charged_credits=charged_credits,
        created_at=created_at,
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
        revenue_credits=0, revenue_rub_estimated=0.0, margin_rub=0.0,
        avg_cost_credits=0.0, model_usage=[], top_users_by_spend=[],
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
