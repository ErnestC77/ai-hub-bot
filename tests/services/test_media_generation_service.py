import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import (
    CostUnit,
    CreditTxType,
    ModelCategory,
    ModelProvider,
    ModelTier,
    RequestStatus,
)
from app.db.models import AIRequest, AiModel, CreditTransaction, User
from app.services import media_generation_service as mgs
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
    get_generation,
    start_media_generation,
)


class FakeRedis:
    """Как в test_text_generation_service.py: set(nx) + delete с записью вызовов."""

    def __init__(self, locked: bool = False):
        self.locked = locked
        self.deleted: list[str] = []

    async def set(self, key, value, nx=False, ex=None):
        return None if self.locked else True

    async def delete(self, key):
        self.deleted.append(key)


class FakeKeyManager:
    def get_key(self, provider, purpose):
        return f"key-{provider.value}-{purpose.value}"


class FakeFalClient:
    """Подменяет mgs.FalClient. Сервис делает FalClient(api_key=...), поэтому
    сам fake используется как фабрика: __call__ записывает ключ и возвращает self."""

    def __init__(self, request_id: str = "fal-req-1", error: Exception | None = None):
        self.request_id = request_id
        self.error = error
        self.api_keys: list[str] = []
        self.image_calls: list[dict] = []
        self.video_calls: list[dict] = []

    def __call__(self, api_key: str):
        self.api_keys.append(api_key)
        return self

    async def submit_image(self, model, prompt, *, image_url=None, webhook_url):
        if self.error is not None:
            raise self.error
        self.image_calls.append({
            "model": model.code, "prompt": prompt,
            "image_url": image_url, "webhook_url": webhook_url,
        })
        return self.request_id

    async def submit_video(self, model, prompt, *, duration_seconds, webhook_url):
        if self.error is not None:
            raise self.error
        self.video_calls.append({
            "model": model.code, "prompt": prompt,
            "duration_seconds": duration_seconds, "webhook_url": webhook_url,
        })
        return self.request_id


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(mgs, "redis_client", fake)
    return fake


@pytest.fixture(autouse=True)
def fal(monkeypatch):
    fake = FakeFalClient()
    monkeypatch.setattr(mgs, "FalClient", fake)
    monkeypatch.setattr(mgs, "get_key_manager", lambda: FakeKeyManager())
    monkeypatch.setattr(mgs.settings, "backend_public_url", "https://backend.example.com")
    monkeypatch.setattr(mgs.settings, "fal_webhook_secret", "whsec")
    return fake


EXPECTED_WEBHOOK_URL = "https://backend.example.com/api/fal/webhook?secret=whsec"


def _image_model(code="img", *, cost_unit=CostUnit.image, recommended=100,
                 min_credits=0) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.image, code=code,
        display_name=code, provider_model_id=f"fal-ai/{code}", tier=ModelTier.standard,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
    )


def _video_model(code="vid", *, cost_unit=CostUnit.second, recommended=600,
                 min_credits=0) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.video, code=code,
        display_name=code, provider_model_id=f"fal-ai/{code}", tier=ModelTier.premium,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
    )


async def _seed(session, *models, balance=1000) -> User:
    user = User(telegram_id=1, username="u", credits_balance=balance)
    session.add(user)
    for m in models:
        session.add(m)
    await session.commit()
    return user


async def _request_rows(session) -> list[AIRequest]:
    return list((await session.execute(select(AIRequest))).scalars().all())


async def _tx_types(session) -> list[CreditTxType]:
    return [
        row[0]
        for row in (
            await session.execute(
                select(CreditTransaction.type).order_by(CreditTransaction.id)
            )
        ).all()
    ]


# --- успешный старт генерации ---

async def test_image_success_reserves_and_submits(session, fake_redis, fal):
    user = await _seed(session, _image_model())

    request = await start_media_generation(session, user, "img", "a bear")

    assert request.status == RequestStatus.reserved
    assert request.provider == "fal"
    assert request.category == ModelCategory.image
    assert request.model_code == "img"
    assert request.prompt_preview == "a bear"
    assert request.estimated_credits == 100   # 1 image * recommended 100
    assert request.reserved_credits == 100
    assert request.provider_response_id == "fal-req-1"
    assert request.result_url is None  # результат появится только из вебхука

    assert fal.image_calls == [{
        "model": "img", "prompt": "a bear",
        "image_url": None, "webhook_url": EXPECTED_WEBHOOK_URL,
    }]
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 900
    assert await _tx_types(session) == [CreditTxType.reserve]
    assert fake_redis.deleted == []  # лок держится до вебхука, НЕ снимается здесь


async def test_image_edit_multiplier_applied_when_image_url_given(session, fal):
    user = await _seed(session, _image_model())

    request = await start_media_generation(
        session, user, "img", "make it night",
        image_url="https://cdn.example.com/in.png",
    )

    # calculate_image_credits(..., is_edit=True): max(ceil(100 * 1.5), 100) = 150
    assert request.estimated_credits == 150
    assert fal.image_calls[0]["image_url"] == "https://cdn.example.com/in.png"


async def test_video_uses_default_duration_of_five_seconds(session, fal):
    user = await _seed(session, _video_model())

    request = await start_media_generation(session, user, "vid", "a bear runs")

    assert request.estimated_credits == 600  # ceil(5/5 * 600)
    assert fal.video_calls == [{
        "model": "vid", "prompt": "a bear runs",
        "duration_seconds": 5, "webhook_url": EXPECTED_WEBHOOK_URL,
    }]


async def test_video_duration_scales_credits_and_is_passed_to_fal(session, fal):
    user = await _seed(session, _video_model(), balance=2000)

    request = await start_media_generation(
        session, user, "vid", "a bear runs", duration_seconds=10, confirm=True
    )

    assert request.estimated_credits == 1200  # ceil(10/5 * 600); >1000 -> нужен confirm
    assert fal.video_calls[0]["duration_seconds"] == 10


# --- подтверждение дорогого запроса ---

async def test_expensive_image_without_confirm_raises(session, fake_redis, fal):
    user = await _seed(session, _image_model(recommended=400))

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await start_media_generation(session, user, "img", "a bear")

    assert exc_info.value.estimated_credits == 400  # > 300
    assert fal.image_calls == []
    assert await _request_rows(session) == []
    assert await _tx_types(session) == []
    # порог проверяется ДО лока -- лок не брался и не снимался
    assert fake_redis.deleted == []


async def test_image_at_threshold_does_not_require_confirm(session, fal):
    user = await _seed(session, _image_model(recommended=300))
    request = await start_media_generation(session, user, "img", "a bear")
    assert request.estimated_credits == 300  # порог строго "больше": ровно 300 проходит


async def test_expensive_video_without_confirm_raises(session, fal):
    user = await _seed(
        session, _video_model(cost_unit=CostUnit.video, recommended=1500), balance=2000
    )

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await start_media_generation(session, user, "vid", "a bear runs")

    assert exc_info.value.estimated_credits == 1500  # > 1000
    assert await _request_rows(session) == []


# --- недостаточный баланс ---

async def test_insufficient_balance_rolls_back_and_releases_lock(session, fake_redis, fal):
    user = await _seed(session, _image_model(), balance=50)
    user_id = user.id  # захват ДО rollback (см. комментарий в test_text_generation_service.py)

    with pytest.raises(InsufficientBalanceError):
        await start_media_generation(session, user, "img", "a bear")

    assert await _request_rows(session) == []   # pending-запись откатилась
    assert await _tx_types(session) == []
    fetched = await session.get(User, user_id)
    assert fetched.credits_balance == 50
    assert fake_redis.deleted == [f"ai_lock:{user_id}"]  # синхронная ошибка -> лок снят


# --- per-user лок ---

async def test_busy_lock_raises_request_in_progress(session, monkeypatch, fal):
    user = await _seed(session, _image_model())
    monkeypatch.setattr(mgs, "redis_client", FakeRedis(locked=True))

    with pytest.raises(RequestInProgressError):
        await start_media_generation(session, user, "img", "a bear")

    assert await _request_rows(session) == []
    assert await _tx_types(session) == []


# --- ошибка submit -> refund ---

async def test_submit_failure_refunds_and_releases_lock(session, fake_redis, monkeypatch):
    user = await _seed(session, _image_model())
    broken = FakeFalClient(error=RuntimeError("fal down"))
    monkeypatch.setattr(mgs, "FalClient", broken)

    with pytest.raises(AIError):
        await start_media_generation(session, user, "img", "a bear")

    [request] = await _request_rows(session)
    assert request.status == RequestStatus.refunded
    assert request.charged_credits == 0
    assert "fal down" in request.error_message
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1000  # резерв возвращён полностью
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]


# --- резолв модели ---

async def test_unknown_model_code_raises_model_not_found(session, fal):
    user = await _seed(session, _image_model())
    with pytest.raises(ModelNotFoundError):
        await start_media_generation(session, user, "no_such_model", "a bear")


async def test_text_model_is_not_a_media_model(session, fal):
    text_model = AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text, code="txt",
        display_name="txt", provider_model_id="vendor/txt", tier=ModelTier.economy,
        cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=3,
    )
    user = await _seed(session, text_model)
    with pytest.raises(ModelNotFoundError):
        await start_media_generation(session, user, "txt", "a bear")


# --- get_generation (owner-scoped) ---

async def test_get_generation_returns_own_request(session, fal):
    user = await _seed(session, _image_model())
    request = await start_media_generation(session, user, "img", "a bear")

    found = await get_generation(session, user, request.id)

    assert found is not None
    assert found.id == request.id


async def test_get_generation_hides_foreign_and_missing_requests(session, fal):
    user = await _seed(session, _image_model())
    request = await start_media_generation(session, user, "img", "a bear")
    other = User(telegram_id=2, username="other", credits_balance=0)
    session.add(other)
    await session.commit()

    assert await get_generation(session, other, request.id) is None
    assert await get_generation(session, user, request.id + 100) is None
