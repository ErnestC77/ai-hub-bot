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
