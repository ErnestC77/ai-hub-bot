import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
# postgresql+asyncpg:// (не голый postgresql://): app.api.deps -> app.db.session
# строит create_async_engine при импорте модуля.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_user, get_db
from app.api.routes import referral as referral_routes
from app.db.base import Base
from app.db.models import Referral, Setting, User

app = FastAPI()
app.include_router(referral_routes.router, prefix="/api")

_test_user = User(
    id=1, telegram_id=1, username="u", first_name="U", is_admin=False,
    default_model_code=None, credits_balance=0,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_user():
    return _test_user


@pytest.fixture
async def db_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(User(id=1, telegram_id=1, username="u"))
        s.add(User(id=2, telegram_id=2, username="friend"))
        s.add(Setting(key="referral_bonus_referrer_credits", value="30", type="int"))
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


async def test_referral_me_returns_earned_credits_and_bonus_amount(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add(Referral(referrer_user_id=1, referred_user_id=2, bonus_granted=True, bonus_credits=30))
        await s.commit()

    response = await client.get("/api/referral/me")

    assert response.status_code == 200
    body = response.json()
    assert body["referred_count"] == 1
    assert body["bonus_count"] == 1
    assert body["earned_credits"] == 30
    assert body["bonus_amount"] == 30  # текущая настройка -- для промо-строки
    assert body["link"].endswith(f"?start=ref_{_test_user.telegram_id}")


async def test_referral_me_defaults_when_no_referrals(client):
    response = await client.get("/api/referral/me")

    assert response.status_code == 200
    body = response.json()
    assert body["referred_count"] == 0
    assert body["bonus_count"] == 0
    assert body["earned_credits"] == 0  # coalesce, не NULL
    assert body["bonus_amount"] == 30
