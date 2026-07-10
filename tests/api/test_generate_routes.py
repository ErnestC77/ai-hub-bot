import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
# postgresql+asyncpg:// (не голый postgresql://): app.api.deps -> app.db.session
# строит create_async_engine при импорте модуля -- см. комментарий в
# tests/api/test_chat_routes.py.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_user, get_db
from app.api.routes import generate
from app.config import settings
from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier, RequestStatus
from app.db.models import AIRequest, AiModel, User
from app.services import antifraud_service as afs
from app.services import media_generation_service as mgs
from app.services.ai.base import AIError
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
from app.services.credit_service import InsufficientBalanceError
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
)
from app.webhooks import fal as fal_webhook

# Минимальное приложение из тестируемых роутеров: изолирует тест от
# lifespan/бота/вебхуков app.main (сам app.main импортируем с фазы 5).
app = FastAPI()
app.include_router(generate.router, prefix="/api")
app.include_router(fal_webhook.router)

_test_user = User(
    id=1, telegram_id=1, username="u", first_name="U", is_admin=False,
    default_model_code=None, credits_balance=1000,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_user():
    return _test_user


class FakeRedis:
    """In-memory Redis: set(nx)/get/delete/incr/incrby/decrby/expire.

    locked=True отклоняет ТОЛЬКО попытку взять ai_lock:* (эмуляция занятого
    per-user лока) -- antifraud-ключи (dup:*, rate_limit:*, daily_spend:*)
    живут как обычно. Тот же класс скопирован из test_text_generation_service.py.
    """

    def __init__(self, locked: bool = False):
        self.locked = locked
        self.deleted: list[str] = []
        self.store: dict[str, str] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def set(self, key, value, nx=False, ex=None):
        if key.startswith("ai_lock:") and self.locked:
            return None
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.expire_calls.append((key, ex))
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)

    async def incr(self, key):
        return await self.incrby(key, 1)

    async def incrby(self, key, amount):
        value = int(self.store.get(key, "0")) + int(amount)
        self.store[key] = str(value)
        return value

    async def decrby(self, key, amount):
        return await self.incrby(key, -int(amount))

    async def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))
        return True


class FakeKeyManager:
    def get_key(self, provider, purpose):
        return f"key-{provider.value}-{purpose.value}"


class FakeFalClient:
    """См. tests/services/test_media_generation_service.py: fake -- одновременно
    и фабрика (__call__ возвращает self), и клиент."""

    def __init__(self, request_id: str = "fal-req-1"):
        self.request_id = request_id
        self.image_calls: list[dict] = []
        self.video_calls: list[dict] = []

    def __call__(self, api_key: str):
        return self

    async def submit_image(self, model, prompt, *, image_url=None, webhook_url):
        self.image_calls.append({
            "model": model.code, "prompt": prompt,
            "image_url": image_url, "webhook_url": webhook_url,
        })
        return self.request_id

    async def submit_video(self, model, prompt, *, duration_seconds, webhook_url):
        self.video_calls.append({
            "model": model.code, "prompt": prompt,
            "duration_seconds": duration_seconds, "webhook_url": webhook_url,
        })
        return self.request_id


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


@pytest.fixture
async def real_service(db_sessionmaker, monkeypatch):
    """Интеграционный режим: реальные start_media_generation/handle_fal_webhook,
    фейки только на границах (Redis, fal HTTP, key manager, сессия вебхука)."""
    fal = FakeFalClient()
    fake_redis = FakeRedis()
    monkeypatch.setattr(mgs, "redis_client", fake_redis)
    monkeypatch.setattr(afs, "redis_client", fake_redis)
    monkeypatch.setattr(mgs, "FalClient", fal)
    monkeypatch.setattr(mgs, "get_key_manager", lambda: FakeKeyManager())
    monkeypatch.setattr(settings, "backend_public_url", "https://backend.example.com")
    monkeypatch.setattr(settings, "fal_webhook_secret", "whsec")

    @asynccontextmanager
    async def _test_session():
        async with db_sessionmaker() as s:
            yield s

    # Вебхук открывает СВОЮ сессию через get_session (вне DI) -- подменяем её.
    monkeypatch.setattr(fal_webhook, "get_session", _test_session)

    async with db_sessionmaker() as s:
        s.add(User(id=1, telegram_id=1, username="u", credits_balance=1000))
        s.add(AiModel(
            provider=ModelProvider.fal, category=ModelCategory.image, code="img",
            display_name="IMG", provider_model_id="fal-ai/flux/dev",
            tier=ModelTier.standard, cost_unit=CostUnit.image,
            min_credits=0, recommended_credits=100,
        ))
        await s.commit()
    return fal


def _stub_request() -> AIRequest:
    return AIRequest(
        id=7, user_id=1, provider="fal", model_code="img",
        category=ModelCategory.image, status=RequestStatus.reserved,
        prompt_preview="a bear", estimated_credits=100, reserved_credits=100,
    )


# --- POST /api/generate: контракт и маппинг ошибок (сервис замокан) ---

async def test_generate_success_returns_request_id_and_estimate(client, monkeypatch):
    mock = AsyncMock(return_value=_stub_request())
    monkeypatch.setattr(generate, "start_media_generation", mock)

    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "a bear"})

    assert response.status_code == 200
    assert response.json() == {"request_id": 7, "estimated_credits": 100}
    assert mock.await_args.kwargs == {"image_url": None, "duration_seconds": None, "confirm": False}


async def test_generate_passes_media_params(client, monkeypatch):
    mock = AsyncMock(return_value=_stub_request())
    monkeypatch.setattr(generate, "start_media_generation", mock)

    response = await client.post("/api/generate", json={
        "model_code": "vid", "prompt": "a bear", "image_url": "https://x/in.png",
        "duration_seconds": 10, "confirm": True,
    })

    assert response.status_code == 200
    assert mock.await_args.kwargs == {
        "image_url": "https://x/in.png", "duration_seconds": 10, "confirm": True,
    }


async def test_generate_request_schema_has_no_credit_cost_override():
    # Security-фикс фазы 3: клиентского поля стоимости в схеме нет вообще.
    assert "credit_cost_override" not in generate.GenerateRequest.model_fields


async def test_generate_unknown_model_maps_to_404(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=ModelNotFoundError("nope"))
    )
    response = await client.post("/api/generate", json={"model_code": "nope", "prompt": "hi"})
    assert response.status_code == 404
    assert response.json()["detail"] == "model not found"


async def test_generate_confirmation_required_maps_to_409_with_estimate(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation",
        AsyncMock(side_effect=ConfirmationRequiredError(1500)),
    )
    response = await client.post("/api/generate", json={"model_code": "vid", "prompt": "hi"})
    assert response.status_code == 409
    assert response.json() == {"estimated_credits": 1500}  # ровно это тело, без "detail"


async def test_generate_request_in_progress_maps_to_409_detail(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=RequestInProgressError())
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 409
    payload = response.json()
    assert "estimated_credits" not in payload
    assert payload["detail"] == "Дождитесь ответа на предыдущий запрос."


async def test_generate_insufficient_balance_maps_to_402(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation",
        AsyncMock(side_effect=InsufficientBalanceError(balance=5, required=100)),
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 402
    assert response.json()["detail"] == "Недостаточно кредитов"


async def test_generate_provider_error_maps_to_502(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=AIError("boom"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Модель временно недоступна, попробуйте позже"


async def test_generate_duplicate_request_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=DuplicateRequestError("dup"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком быстрый повтор запроса, подождите пару секунд"


async def test_generate_rate_limit_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=RateLimitExceededError("rl"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много запросов, попробуйте через минуту"


async def test_generate_tier_not_allowed_maps_to_403(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=TierNotAllowedError("tier"))
    )
    response = await client.post("/api/generate", json={"model_code": "veo_video", "prompt": "hi"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Эта модель доступна после первой покупки пакета"


async def test_generate_free_tier_limit_maps_to_402(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=FreeTierLimitExceededError("cap"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 402
    assert response.json()["detail"] == "Бесплатный лимит исчерпан, купите пакет кредитов"


async def test_generate_daily_spend_limit_maps_to_429(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=DailySpendLimitExceededError("daily"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Дневной лимит трат исчерпан, попробуйте завтра"


# --- GET /api/generate/{id} ---

async def test_generate_status_404_for_unknown_request(client, monkeypatch):
    monkeypatch.setattr(generate, "get_generation", AsyncMock(return_value=None))
    response = await client.get("/api/generate/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "request not found"


# --- POST /api/fal/webhook: секрет ---

async def test_fal_webhook_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "fal_webhook_secret", "whsec")
    response = await client.post("/api/fal/webhook?secret=wrong", json={})
    assert response.status_code == 403
    assert response.json()["detail"] == "invalid secret"


async def test_fal_webhook_rejects_when_secret_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "fal_webhook_secret", "")
    response = await client.post("/api/fal/webhook?secret=", json={})
    assert response.status_code == 403


# --- интеграционные сценарии (реальный сервис поверх sqlite) ---

async def test_credit_cost_override_field_has_no_effect_on_charge(
    client, db_sessionmaker, real_service
):
    response = await client.post("/api/generate", json={
        "model_code": "img", "prompt": "a bear",
        "credit_cost_override": 1,  # поле старого API: должно полностью игнорироваться
    })

    assert response.status_code == 200
    assert response.json()["estimated_credits"] == 100  # серверный расчёт, не 1
    async with db_sessionmaker() as s:
        [request] = (await s.execute(select(AIRequest))).scalars().all()
        assert request.estimated_credits == 100
        assert request.reserved_credits == 100
        user = await s.get(User, 1)
        assert user.credits_balance == 900  # зарезервировано 100, а не 1


async def test_full_flow_get_returns_result_url_from_db_column(
    client, db_sessionmaker, real_service
):
    create = await client.post("/api/generate", json={"model_code": "img", "prompt": "a bear"})
    assert create.status_code == 200
    request_id = create.json()["request_id"]

    hook = await client.post(
        "/api/fal/webhook?secret=whsec",
        json={
            "request_id": "fal-req-1", "status": "OK",
            "payload": {"images": [{"url": "https://cdn.fal.media/out.png"}]},
        },
    )
    assert hook.status_code == 200
    assert hook.json() == {"ok": True}

    status = await client.get(f"/api/generate/{request_id}")
    assert status.status_code == 200
    assert status.json() == {
        "status": "completed",
        "result_url": "https://cdn.fal.media/out.png",
        "error_message": None,
        "charged_credits": 100,  # реальное поле, не хардкод 0 из старого API
    }
    # Результат живёт в durable-колонке ai_requests.result_url.
    async with db_sessionmaker() as s:
        request = await s.get(AIRequest, request_id)
        assert request.result_url == "https://cdn.fal.media/out.png"


async def test_full_flow_error_webhook_visible_in_status(
    client, db_sessionmaker, real_service
):
    create = await client.post("/api/generate", json={"model_code": "img", "prompt": "a bear"})
    request_id = create.json()["request_id"]

    hook = await client.post(
        "/api/fal/webhook?secret=whsec",
        json={"request_id": "fal-req-1", "status": "ERROR", "error": "nsfw content"},
    )
    assert hook.status_code == 200

    status = await client.get(f"/api/generate/{request_id}")
    assert status.json() == {
        "status": "refunded",
        "result_url": None,
        "error_message": "nsfw content",
        "charged_credits": 0,
    }
