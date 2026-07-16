import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
# postgresql+asyncpg:// (not plain postgresql://): this test imports app.api.deps,
# which imports app.db.session, which builds a real create_async_engine(settings.database_url)
# at *module import time*. A driverless "postgresql://" URL makes SQLAlchemy pick the sync
# psycopg2 dialect and raise InvalidRequestError immediately on import (confirmed locally --
# psycopg2 is installed in this env). No actual connection is attempted here (get_db is
# overridden with an in-memory sqlite session in the `client` fixture below), so the URL only
# needs to parse to an async-capable dialect.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_user, get_db
from app.api.routes import chat, me
from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelOptionKind, ModelProvider, ModelTier
from app.db.models import AiModel, ModelOption, User
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
from app.services.text_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    ModelUnavailableError,
    RequestInProgressError,
    TextGenerationResult,
)

# Минимальное приложение из тестируемых роутеров: изолирует тест от
# lifespan/бота/вебхуков app.main (сам app.main импортируем с фазы 5).
app = FastAPI()
app.include_router(chat.router, prefix="/api")
app.include_router(me.router, prefix="/api")

_test_user = User(
    id=1, telegram_id=1, username="u", first_name="U", is_admin=False,
    default_model_code=None, credits_balance=100,
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


def _text_model(code, *, sort_order, tier=ModelTier.economy, is_active=True, is_visible=True,
                category=ModelCategory.text) -> AiModel:
    return AiModel(
        provider=ModelProvider.openrouter, category=category, code=code,
        display_name=code.upper(), provider_model_id=f"vendor/{code}", tier=tier,
        cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=5,
        is_active=is_active, is_visible=is_visible, sort_order=sort_order,
    )


def _option(model_id, kind, code, *, sort_order, multiplier=1.0, is_default=False,
            is_active=True) -> ModelOption:
    return ModelOption(
        model_id=model_id, kind=kind, code=code, label=code,
        provider_params={}, credits_multiplier=multiplier,
        is_default=is_default, is_active=is_active, sort_order=sort_order,
    )


# --- GET /api/models ---

async def test_models_returns_visible_active_text_models_sorted(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add_all([
            _text_model("second", sort_order=20),
            _text_model("first", sort_order=10),
            _text_model("hidden", sort_order=30, is_visible=False),
            _text_model("inactive", sort_order=40, is_active=False),
            _text_model("image", sort_order=50, category=ModelCategory.image),
        ])
        await s.commit()

    response = await client.get("/api/models")

    assert response.status_code == 200
    payload = response.json()
    assert [m["code"] for m in payload] == ["first", "second"]
    assert payload[0] == {
        "code": "first",
        "display_name": "FIRST",
        "tier": "economy",
        "min_credits": 3,
        "recommended_credits": 5,
        "options": [],  # у модели без опций -- пустой список, не отсутствие ключа
    }
    # provider_model_id никогда не уходит наружу (ТЗ).
    assert "provider_model_id" not in response.text


async def test_models_category_image_returns_only_visible_active_image_models(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add_all([
            _text_model("txt", sort_order=10),
            _text_model("img_b", sort_order=30, category=ModelCategory.image),
            _text_model("img_a", sort_order=20, category=ModelCategory.image, tier=ModelTier.standard),
            _text_model("img_hidden", sort_order=40, category=ModelCategory.image, is_visible=False),
            _text_model("vid", sort_order=50, category=ModelCategory.video),
        ])
        await s.commit()

    response = await client.get("/api/models", params={"category": "image"})

    assert response.status_code == 200
    payload = response.json()
    assert [m["code"] for m in payload] == ["img_a", "img_b"]  # sort_order, text/video/hidden отфильтрованы
    assert payload[0] == {
        "code": "img_a",
        "display_name": "IMG_A",
        "tier": "standard",
        "min_credits": 3,
        "recommended_credits": 5,
        "options": [],
    }


async def test_models_invalid_category_is_422(client):
    # FastAPI валидирует enum-query сам: невалидное значение -> 422
    # (спека в скобках говорит "400", фактическое поведение FastAPI -- 422).
    response = await client.get("/api/models", params={"category": "audio"})
    assert response.status_code == 422


async def test_models_endpoint_exposes_options(client, db_sessionmaker):
    # Фронт рисует сегменты ИЗ ПРИШЕДШИХ опций: у модели без ручки размера
    # (nano_banana) секции качества не будет вовсе.
    async with db_sessionmaker() as s:
        s.add_all([
            _text_model("kling_video", sort_order=10, category=ModelCategory.video),
            _text_model("nano_banana", sort_order=20, category=ModelCategory.video),
        ])
        await s.flush()
        kling = (await s.execute(
            select(AiModel).where(AiModel.code == "kling_video")
        )).scalar_one()
        s.add_all([
            _option(kling.id, ModelOptionKind.duration, "5s", sort_order=1,
                    multiplier=1.0, is_default=True),
            _option(kling.id, ModelOptionKind.duration, "10s", sort_order=2,
                    multiplier=2.0),
        ])
        await s.commit()

    body = (await client.get("/api/models", params={"category": "video"})).json()

    kling = next(m for m in body if m["code"] == "kling_video")
    assert [o["code"] for o in kling["options"]] == ["5s", "10s"]
    assert kling["options"][0]["is_default"] is True
    assert kling["options"][0]["kind"] == "duration"
    assert float(kling["options"][1]["credits_multiplier"]) == 2.0

    nano_banana = next(m for m in body if m["code"] == "nano_banana")
    assert nano_banana["options"] == []
    # provider_params клиенту не отдаём -- ни в каком виде.
    assert "provider_params" not in (await client.get(
        "/api/models", params={"category": "video"}
    )).text


async def test_models_endpoint_hides_inactive_options(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add(_text_model("wan_video", sort_order=10, category=ModelCategory.video))
        await s.flush()
        wan = (await s.execute(
            select(AiModel).where(AiModel.code == "wan_video")
        )).scalar_one()
        s.add_all([
            _option(wan.id, ModelOptionKind.quality, "480p", sort_order=1, is_default=True),
            _option(wan.id, ModelOptionKind.quality, "720p", sort_order=2, is_active=False),
        ])
        await s.commit()

    body = (await client.get("/api/models", params={"category": "video"})).json()

    wan = next(m for m in body if m["code"] == "wan_video")
    assert [o["code"] for o in wan["options"]] == ["480p"]


# --- POST /api/chat ---

async def test_chat_success_returns_answer_and_billing(client, monkeypatch):
    mock = AsyncMock(return_value=TextGenerationResult(answer="привет", charged_credits=5, balance_after=95))
    monkeypatch.setattr(chat, "generate_text", mock)

    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})

    assert response.status_code == 200
    assert response.json() == {"answer": "привет", "charged_credits": 5, "balance_after": 95}
    # confirm по умолчанию False и прокидывается в сервис.
    assert mock.await_args.kwargs["confirm"] is False


async def test_chat_passes_confirm_true(client, monkeypatch):
    mock = AsyncMock(return_value=TextGenerationResult(answer="ok", charged_credits=110, balance_after=390))
    monkeypatch.setattr(chat, "generate_text", mock)

    response = await client.post(
        "/api/chat", json={"model_code": "claude_opus", "prompt": "hi", "confirm": True}
    )

    assert response.status_code == 200
    assert mock.await_args.kwargs["confirm"] is True


async def test_chat_confirmation_required_maps_to_409_with_estimate(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=ConfirmationRequiredError(138)))

    response = await client.post("/api/chat", json={"model_code": "claude_opus", "prompt": "hi"})

    assert response.status_code == 409
    assert response.json() == {"estimated_credits": 138}  # ровно это тело, без "detail"


async def test_chat_request_in_progress_maps_to_409_detail(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=RequestInProgressError()))

    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})

    assert response.status_code == 409
    payload = response.json()
    assert "estimated_credits" not in payload  # отличимо от confirmation-409
    assert payload["detail"] == "Дождитесь ответа на предыдущий запрос."


async def test_chat_insufficient_balance_maps_to_402(client, monkeypatch):
    monkeypatch.setattr(
        chat, "generate_text",
        AsyncMock(side_effect=InsufficientBalanceError(balance=5, required=7)),
    )

    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})

    assert response.status_code == 402
    assert response.json()["detail"] == "Недостаточно кредитов"


async def test_chat_unknown_model_maps_to_404(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=ModelNotFoundError("nope")))
    response = await client.post("/api/chat", json={"model_code": "nope", "prompt": "hi"})
    assert response.status_code == 404


async def test_chat_unavailable_model_maps_to_404(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=ModelUnavailableError("dead")))
    response = await client.post("/api/chat", json={"model_code": "dead", "prompt": "hi"})
    assert response.status_code == 404


async def test_chat_provider_error_maps_to_502(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=AIError("boom")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Модель временно недоступна, попробуйте позже"


async def test_chat_duplicate_request_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=DuplicateRequestError("dup")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком быстрый повтор запроса, подождите пару секунд"


async def test_chat_rate_limit_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=RateLimitExceededError("rl")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много запросов, попробуйте через минуту"


async def test_chat_tier_not_allowed_maps_to_403(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=TierNotAllowedError("tier")))
    response = await client.post("/api/chat", json={"model_code": "claude_opus", "prompt": "hi"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Эта модель доступна после первой покупки пакета"


async def test_chat_free_tier_limit_maps_to_402(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=FreeTierLimitExceededError("cap")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 402
    assert response.json()["detail"] == "Бесплатный лимит исчерпан, купите пакет кредитов"


async def test_chat_daily_spend_limit_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=DailySpendLimitExceededError("daily")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Дневной лимит трат исчерпан, попробуйте завтра"


async def test_chat_empty_prompt_is_422(client):
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": ""})
    assert response.status_code == 422


# --- GET /api/me ---

async def test_me_returns_simplified_profile_with_default_model(client):
    response = await client.get("/api/me")

    assert response.status_code == 200
    assert response.json() == {
        "telegram_id": 1,
        "username": "u",
        "first_name": "U",
        "is_admin": False,
        "default_model_code": "deepseek_v3",  # у _test_user не задана -> дефолт из ТЗ
        "credits_balance": 100,
        "total_credits_purchased": 0,
        "total_credits_spent": 0,
    }


async def test_me_keeps_explicit_default_model(client):
    _test_user.default_model_code = "claude_sonnet"
    try:
        response = await client.get("/api/me")
        assert response.json()["default_model_code"] == "claude_sonnet"
    finally:
        _test_user.default_model_code = None


async def test_subscription_me_is_gone(client):
    response = await client.get("/api/subscription/me")
    assert response.status_code == 404
