import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CreditTxType, PaymentProvider, PaymentStatus
from app.db.models import CreditTransaction, Payment, User
from app.services.payments.gateway import GATEWAYS
from app.services.payments.refund_service import refund


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


class _FakeGateway:
    """Мирроринг реального гейтвея: внешний вызов + status=refunded + commit."""

    def __init__(self, provider, *, external_ok=True, raises=None):
        self.provider = provider
        self.external_ok = external_ok
        self.raises = raises
        self.called = False

    async def refund_payment(self, session, payment):
        self.called = True
        if self.raises:
            raise self.raises
        if not self.external_ok:
            return False
        payment.status = PaymentStatus.refunded
        await session.commit()
        return True


async def _make(session, *, status, balance, credits=1000, purchased=1000):
    user = User(telegram_id=1, username="u", credits_balance=balance, total_credits_purchased=purchased)
    session.add(user)
    await session.flush()
    payment = Payment(
        user_id=user.id, credit_package_code="basic", provider=PaymentProvider.yookassa,
        amount=599, currency="RUB", status=status,
        idempotence_key=str(uuid.uuid4()), payload={"credits": credits},
    )
    session.add(payment)
    await session.commit()  # как в проде: платёж/юзер уже закоммичены до refund,
    return user, payment    # поэтому rollback внутри refund откатывает только отзыв


async def _refund_tx_count(session, user_id) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(CreditTransaction).where(
                CreditTransaction.user_id == user_id, CreditTransaction.type == CreditTxType.refund
            )
        )
    ).scalar_one()


async def test_refund_succeeded_revokes_granted_credits(session, monkeypatch):
    user, payment = await _make(session, status=PaymentStatus.succeeded, balance=1000)
    gw = _FakeGateway(PaymentProvider.yookassa)
    monkeypatch.setitem(GATEWAYS, PaymentProvider.yookassa, gw)

    ok = await refund(session, payment)

    assert ok is True
    assert gw.called is True
    assert payment.status == PaymentStatus.refunded
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 0            # 1000 начислено -> 1000 отозвано
    assert fetched.total_credits_purchased == 0
    assert await _refund_tx_count(session, user.id) == 1


async def test_refund_after_spending_goes_negative_anti_farm(session, monkeypatch):
    # Купил 1000, потратил 700 (balance=300), затем возврат -> клавбэк полной суммы.
    user, payment = await _make(session, status=PaymentStatus.succeeded, balance=300)
    monkeypatch.setitem(GATEWAYS, PaymentProvider.yookassa, _FakeGateway(PaymentProvider.yookassa))

    ok = await refund(session, payment)

    assert ok is True
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == -700         # 300 - 1000 (анти-фарм, минус допустим)


async def test_refund_non_succeeded_is_refused(session, monkeypatch):
    user, payment = await _make(session, status=PaymentStatus.pending, balance=1000)
    gw = _FakeGateway(PaymentProvider.yookassa)
    monkeypatch.setitem(GATEWAYS, PaymentProvider.yookassa, gw)

    ok = await refund(session, payment)

    assert ok is False
    assert gw.called is False                      # до гейтвея не дошли
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1000         # кредиты не тронуты
    assert await _refund_tx_count(session, user.id) == 0


async def test_refund_external_failure_rolls_back_credit_revoke(session, monkeypatch):
    user, payment = await _make(session, status=PaymentStatus.succeeded, balance=1000)
    uid = user.id  # захват ДО refund: после его rollback доступ к user.id -- sync lazy-load
    monkeypatch.setitem(
        GATEWAYS, PaymentProvider.yookassa,
        _FakeGateway(PaymentProvider.yookassa, external_ok=False),
    )

    ok = await refund(session, payment)

    assert ok is False
    fetched = await session.get(User, uid)
    assert fetched.credits_balance == 1000         # отзыв откатан
    assert await _refund_tx_count(session, uid) == 0


async def test_refund_crypto_not_implemented_returns_false(session, monkeypatch):
    user, payment = await _make(session, status=PaymentStatus.succeeded, balance=1000)
    payment.provider = PaymentProvider.crypto
    await session.commit()
    uid = user.id  # захват ДО refund (rollback внутри -> sync lazy-load на user.id)
    monkeypatch.setitem(
        GATEWAYS, PaymentProvider.crypto,
        _FakeGateway(PaymentProvider.crypto, raises=NotImplementedError("manual")),
    )

    ok = await refund(session, payment)

    assert ok is False                             # 400, не 500
    fetched = await session.get(User, uid)
    assert fetched.credits_balance == 1000         # отзыв откатан
