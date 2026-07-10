import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
# postgresql+asyncpg:// (не голый postgresql://): app.api.deps -> app.db.session
# строит create_async_engine при импорте модуля -- см. комментарий в
# tests/api/test_chat_routes.py.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_admin, get_db
from app.api.routes import admin
from app.db.base import Base
from app.db.enums import CostUnit, CreditTxType, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel, CreditPackage, CreditTransaction, Setting, User

app = FastAPI()
app.include_router(admin.router, prefix="/api")

_admin_user = User(
    id=99, telegram_id=99, username="admin", first_name="A", is_admin=True,
    default_model_code=None, credits_balance=0,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_admin():
    return _admin_user


@pytest.fixture
async def db_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(User(
            id=1, telegram_id=100, username="alice", first_name="Alice",
            credits_balance=100, total_credits_purchased=1000, total_credits_spent=900,
        ))
        s.add(AiModel(
            provider=ModelProvider.openrouter, category=ModelCategory.text,
            code="deepseek_v3", display_name="DeepSeek V3",
            provider_model_id="deepseek/deepseek-chat", tier=ModelTier.economy,
            cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=3, sort_order=10,
        ))
        s.add(CreditPackage(
            code="start", title="START", credits=1000, price_rub=149, price_stars=75,
        ))
        s.add(Setting(
            key="margin_multiplier", value="2.5", type="float",
            description="Множитель целевой маржи",
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
    app.dependency_overrides[current_admin] = _fake_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# --- GET /api/admin/stats ---

async def test_stats_returns_v2_shape(client):
    response = await client.get("/api/admin/stats")

    assert response.status_code == 200
    assert response.json() == {
        "today_new_users": 1,  # alice создана "сейчас" (server_default now)
        "today_payments_count": 0,
        "today_payments_amount_rub": 0.0,
        "today_ai_requests": 0,
        "today_api_cost_usd": 0.0,
        "today_errors": 0,
        "month_revenue_rub": 0.0,
        "month_credits_purchases_count": 0,
    }


# --- users ---

async def test_get_user_returns_credit_fields(client):
    response = await client.get("/api/admin/users/100")

    assert response.status_code == 200
    assert response.json() == {
        "telegram_id": 100,
        "username": "alice",
        "first_name": "Alice",
        "is_admin": False,
        "is_blocked": False,
        "credits_balance": 100,
        "total_credits_purchased": 1000,
        "total_credits_spent": 900,
    }


async def test_get_unknown_user_is_404(client):
    response = await client.get("/api/admin/users/777")
    assert response.status_code == 404


async def test_users_search_by_username(client):
    response = await client.get("/api/admin/users", params={"query": "ali"})
    assert response.status_code == 200
    assert [u["telegram_id"] for u in response.json()] == [100]


async def test_block_and_unblock_user(client):
    blocked = await client.post("/api/admin/users/100/block")
    assert blocked.status_code == 200
    assert blocked.json()["is_blocked"] is True

    unblocked = await client.post("/api/admin/users/100/unblock")
    assert unblocked.json()["is_blocked"] is False


# --- POST /api/admin/users/{telegram_id}/credits ---

async def test_adjust_credits_positive_amount(client, db_sessionmaker):
    response = await client.post("/api/admin/users/100/credits", json={"amount": 50})

    assert response.status_code == 200
    body = response.json()
    assert body["credits_balance"] == 150
    assert body["total_credits_purchased"] == 1000  # totals не трогаются
    assert body["total_credits_spent"] == 900

    async with db_sessionmaker() as s:
        [tx] = (await s.execute(select(CreditTransaction))).scalars().all()
        assert tx.type == CreditTxType.admin_adjustment
        assert tx.amount == 50


async def test_adjust_credits_negative_amount(client):
    response = await client.post("/api/admin/users/100/credits", json={"amount": -60})
    assert response.status_code == 200
    assert response.json()["credits_balance"] == 40


async def test_adjust_credits_below_zero_is_400(client):
    response = await client.post("/api/admin/users/100/credits", json={"amount": -101})
    assert response.status_code == 400
    assert response.json()["detail"] == "Недостаточно кредитов для списания"


async def test_adjust_credits_zero_is_422(client):
    response = await client.post("/api/admin/users/100/credits", json={"amount": 0})
    assert response.status_code == 422


# --- GET /api/admin/users/{telegram_id}/transactions ---

async def test_transactions_paginated_newest_first(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        for i, amount in enumerate([10, 20, 30], start=1):
            s.add(CreditTransaction(
                user_id=1, type=CreditTxType.purchase, amount=amount,
                balance_before=0, balance_after=amount, description=f"tx{i}",
            ))
        await s.commit()

    page1 = await client.get("/api/admin/users/100/transactions", params={"limit": 2})
    assert page1.status_code == 200
    assert [tx["amount"] for tx in page1.json()] == [30, 20]  # новейшие первыми
    assert page1.json()[0]["type"] == "purchase"

    page2 = await client.get(
        "/api/admin/users/100/transactions", params={"limit": 2, "offset": 2}
    )
    assert [tx["amount"] for tx in page2.json()] == [10]


# --- models ---

async def test_models_list_returns_catalog_fields(client):
    response = await client.get("/api/admin/models")

    assert response.status_code == 200
    [model] = response.json()
    assert model == {
        "code": "deepseek_v3",
        "provider": "openrouter",
        "category": "text",
        "tier": "economy",
        "display_name": "DeepSeek V3",
        "provider_model_id": "deepseek/deepseek-chat",
        "input_price_usd_per_1m_tokens": 0.0,
        "output_price_usd_per_1m_tokens": 0.0,
        "min_credits": 3,
        "recommended_credits": 3,
        "is_active": True,
        "is_visible": True,
        "sort_order": 10,
    }


async def test_patch_model_updates_editable_fields(client, db_sessionmaker):
    response = await client.patch("/api/admin/models/deepseek_v3", json={
        "is_active": False,
        "recommended_credits": 9,
        "input_price_usd_per_1m_tokens": 0.5,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False
    assert body["recommended_credits"] == 9
    assert body["input_price_usd_per_1m_tokens"] == 0.5

    async with db_sessionmaker() as s:
        row = (await s.execute(select(AiModel).where(AiModel.code == "deepseek_v3"))).scalar_one()
        assert row.is_active is False
        assert row.recommended_credits == 9


async def test_patch_unknown_model_is_404(client):
    response = await client.patch("/api/admin/models/nope", json={"is_active": False})
    assert response.status_code == 404


# --- packages ---

async def test_packages_list_and_patch(client, db_sessionmaker):
    listed = await client.get("/api/admin/packages")
    assert listed.status_code == 200
    assert [p["code"] for p in listed.json()] == ["start"]

    patched = await client.patch("/api/admin/packages/start", json={
        "price_stars": 99, "credits": 1200, "is_active": False,
    })
    assert patched.status_code == 200
    body = patched.json()
    assert body["price_stars"] == 99
    assert body["credits"] == 1200
    assert body["is_active"] is False

    async with db_sessionmaker() as s:
        row = (await s.execute(select(CreditPackage).where(CreditPackage.code == "start"))).scalar_one()
        assert row.price_stars == 99


async def test_patch_unknown_package_is_404(client):
    response = await client.patch("/api/admin/packages/nope", json={"credits": 1})
    assert response.status_code == 404


# --- settings ---

async def test_settings_list_returns_rows(client):
    response = await client.get("/api/admin/settings")
    assert response.status_code == 200
    assert response.json() == [{
        "key": "margin_multiplier",
        "value": "2.5",
        "type": "float",
        "description": "Множитель целевой маржи",
    }]


async def test_patch_setting_updates_value_keeps_type(client, db_sessionmaker):
    response = await client.patch(
        "/api/admin/settings/margin_multiplier", json={"value": "3.0"}
    )

    assert response.status_code == 200
    assert response.json()["value"] == "3.0"
    assert response.json()["type"] == "float"

    async with db_sessionmaker() as s:
        row = await s.get(Setting, "margin_multiplier")
        assert row.value == "3.0"
        assert row.type == "float"


async def test_patch_unknown_setting_is_404(client):
    response = await client.patch("/api/admin/settings/no_such_key", json={"value": "1"})
    assert response.status_code == 404


async def test_patch_int_setting_with_non_numeric_value_is_422_and_unchanged(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add(Setting(
            key="minimum_text_credits", value="3", type="int",
            description="Минимум кредитов за текстовый запрос",
        ))
        await s.commit()

    response = await client.patch(
        "/api/admin/settings/minimum_text_credits", json={"value": "free"}
    )
    assert response.status_code == 422

    async with db_sessionmaker() as s:
        row = await s.get(Setting, "minimum_text_credits")
        assert row.value == "3"  # значение не должно было измениться


async def test_patch_int_setting_with_valid_numeric_value_succeeds(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add(Setting(
            key="minimum_text_credits", value="3", type="int",
            description="Минимум кредитов за текстовый запрос",
        ))
        await s.commit()

    response = await client.patch(
        "/api/admin/settings/minimum_text_credits", json={"value": "5"}
    )
    assert response.status_code == 200
    assert response.json()["value"] == "5"

    async with db_sessionmaker() as s:
        row = await s.get(Setting, "minimum_text_credits")
        assert row.value == "5"


async def test_patch_bool_setting_rejects_invalid_value(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add(Setting(
            key="fake_flag", value="true", type="bool", description="тестовый флаг",
        ))
        await s.commit()

    response = await client.patch("/api/admin/settings/fake_flag", json={"value": "maybe"})
    assert response.status_code == 422

    ok = await client.patch("/api/admin/settings/fake_flag", json={"value": "false"})
    assert ok.status_code == 200
    assert ok.json()["value"] == "false"


# --- старые tariff-эндпойнты удалены ---

async def test_tariffs_endpoints_are_gone(client):
    assert (await client.get("/api/admin/tariffs")).status_code == 404
    assert (
        await client.post("/api/admin/users/100/grant", json={"tariff_code": "x"})
    ).status_code == 404
    assert (await client.post("/api/admin/users/100/cancel-subscription")).status_code == 404
    assert (
        await client.post("/api/admin/users/100/grant-credits", json={"amount": 1})
    ).status_code == 404
