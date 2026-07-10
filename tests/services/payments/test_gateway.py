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
