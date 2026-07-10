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

# Минимальное приложение из тестируемого роутера, как в
# tests/api/test_generate_routes.py (сам app.main импортируем с фазы 5).
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
