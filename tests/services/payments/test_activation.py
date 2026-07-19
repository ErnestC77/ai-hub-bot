import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CreditTxType, PaymentProvider, PaymentStatus
from app.db.models import CreditTransaction, Payment, Setting, User
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


# --- бонус первой покупки -------------------------------------------------

async def _enable_first_purchase_bonus(session, percent: str = "30", cap: str = "1500") -> None:
    session.add(Setting(key="first_purchase_bonus_percent", value=percent, type="int",
                        description="test"))
    session.add(Setting(key="first_purchase_bonus_cap", value=cap, type="int",
                        description="test"))
    await session.commit()


async def test_first_purchase_gets_bonus(session):
    await _enable_first_purchase_bonus(session)
    user = await _make_user(session)
    payment = await _make_payment(session, user)  # START, 1000 кредитов

    result = await activate_paid_payment(session, payment_id=payment.id)

    assert result == ActivationResult(credits_granted=1000, bonus_credits=300)
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1300
    # Бонус НЕ должен считаться покупкой (total растёт только на пакет).
    assert fetched.total_credits_purchased == 1000

    types = {
        tx.type for tx in (await session.execute(select(CreditTransaction))).scalars().all()
    }
    assert types == {CreditTxType.purchase, CreditTxType.first_purchase_bonus}


async def test_bonus_capped_for_big_packages(session):
    await _enable_first_purchase_bonus(session)
    user = await _make_user(session)
    payment = await _make_payment(session, user, payload={"credits": 70000})  # BUSINESS

    result = await activate_paid_payment(session, payment_id=payment.id)

    # 30% было бы 21000 и увело бы пакет в минус по марже; кап режет до 1500.
    assert result.bonus_credits == 1500


async def test_second_purchase_gets_no_bonus(session):
    await _enable_first_purchase_bonus(session)
    user = await _make_user(session)
    first = await _make_payment(session, user, provider_payment_id="yk-1")
    await activate_paid_payment(session, payment_id=first.id)

    second = await _make_payment(session, user, provider_payment_id="yk-2")
    result = await activate_paid_payment(session, payment_id=second.id)

    assert result.bonus_credits == 0
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1300 + 1000  # бонус только с первой


async def test_welcome_bonus_does_not_disable_first_purchase_bonus(session):
    """Welcome/referral идут не-purchase типами и не должны съедать право
    на бонус первой покупки (total_credits_purchased остаётся 0)."""
    await _enable_first_purchase_bonus(session)
    user = await _make_user(session, balance=220)  # как после welcome
    payment = await _make_payment(session, user)

    result = await activate_paid_payment(session, payment_id=payment.id)

    assert result.bonus_credits == 300


async def test_bonus_disabled_when_percent_zero(session):
    await _enable_first_purchase_bonus(session, percent="0")
    user = await _make_user(session)
    payment = await _make_payment(session, user)

    result = await activate_paid_payment(session, payment_id=payment.id)

    assert result.bonus_credits == 0
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1000
