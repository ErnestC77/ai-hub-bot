import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_user, get_db
from app.api.routes import me as me_route
from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel, User


def _text_model(code, *, visible=True, active=True, sort=10):
    return AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text, code=code,
        display_name=code.upper(), provider_model_id=f"x/{code}", tier=ModelTier.economy,
        cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=3,
        is_visible=visible, is_active=active, sort_order=sort,
    )


def _image_model(code):
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.image, code=code,
        display_name=code.upper(), provider_model_id=f"fal-ai/{code}", tier=ModelTier.standard,
        cost_unit=CostUnit.image, min_credits=29, recommended_credits=29,
    )


@pytest.fixture
async def client_and_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as seed:
        seed.add_all([
            User(id=1, telegram_id=1, username="u", credits_balance=100),
            _text_model("deepseek_v3", sort=10),
            _text_model("qwen_max", sort=60),
            _text_model("hidden_text", visible=False, sort=70),
            _image_model("qwen_image"),
        ])
        await seed.commit()

    app = FastAPI()
    app.include_router(me_route.router, prefix="/api")

    # current_user ДОЛЖЕН делить сессию с эндпоинтом, иначе его commit не виден.
    # Делаем current_user зависимым от get_db (тот же контракт, что в проде) --
    # так FastAPI гарантирует одну сессию на запрос и корректный порядок.
    from fastapi import Depends as _Depends

    async def _get_db():
        async with maker() as s:
            yield s

    async def _current_user(session=_Depends(get_db)):
        return (await session.execute(select(User).where(User.id == 1))).scalar_one()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[current_user] = _current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker
    await engine.dispose()


async def test_get_me_falls_back_to_default_model(client_and_session):
    client, _ = client_and_session
    r = await client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["default_model_code"] == "deepseek_v3"


async def test_set_default_model_persists(client_and_session):
    client, maker = client_and_session
    r = await client.put("/api/me/default-model", json={"model_code": "qwen_max"})
    assert r.status_code == 200
    assert r.json()["default_model_code"] == "qwen_max"

    async with maker() as s:
        user = (await s.execute(select(User).where(User.id == 1))).scalar_one()
        assert user.default_model_code == "qwen_max"


async def test_set_default_model_rejects_image_model(client_and_session):
    client, _ = client_and_session
    r = await client.put("/api/me/default-model", json={"model_code": "qwen_image"})
    assert r.status_code == 404  # дефолт чата -- только текстовая модель


async def test_set_default_model_rejects_hidden_model(client_and_session):
    client, _ = client_and_session
    r = await client.put("/api/me/default-model", json={"model_code": "hidden_text"})
    assert r.status_code == 404


async def test_set_default_model_rejects_unknown_code(client_and_session):
    client, _ = client_and_session
    r = await client.put("/api/me/default-model", json={"model_code": "no_such"})
    assert r.status_code == 404
