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
