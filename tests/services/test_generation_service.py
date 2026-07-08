from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import ModelCategory, ModelProvider, RequestStatus
from app.db.models import AIRequest, ModelConfig, Tariff, UsageLimit, User
from app.services.access_service import RequestInProgressError
from app.services.generation_service import get_generation, handle_piapi_webhook, start_generation


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


class FakeRedis:
    """Minimal in-memory stand-in for redis.asyncio.Redis, supporting only the
    SET NX EX / DELETE calls generation_service.py makes for the per-user in-flight
    lock. No real Redis server is available in the test environment."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self._store:
            return None  # lock already held -- not acquired
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.services.generation_service.redis_client", fake)
    return fake


async def _setup(session, credit_cost=51):
    tariff = Tariff(
        code="free", name="Free", price_rub=0, price_stars=0, period_days=36500,
        fast_limit=5, medium_limit=0, premium_limit=0, image_limit=0, daily_limit=5,
        max_input_tokens=2000, max_output_tokens=1000,
    )
    session.add(tariff)
    user = User(telegram_id=1, username="u")
    session.add(user)
    await session.flush()
    from app.db.models import CreditTransaction
    from app.db.enums import CreditTxType
    session.add(CreditTransaction(user_id=user.id, type=CreditTxType.deposit, amount=1000, reason="test"))
    model = ModelConfig(
        model_code="piapi-veo3-fast", provider=ModelProvider.piapi, display_name="AI Video Fast",
        category=ModelCategory.video, credit_cost=credit_cost, key_purpose="video",
        piapi_model="veo3.1", piapi_task_type="veo3.1-video-fast", piapi_extra_input={"duration": "5s"},
    )
    session.add(model)
    await session.commit()
    return user, model


@patch("app.services.generation_service.PiAPIClient")
async def test_start_generation_piapi_creates_processing_request_with_task_id(mock_client_cls, session):
    mock_client = AsyncMock()
    mock_client.create_task.return_value = "task-123"
    mock_client_cls.return_value = mock_client

    user, model = await _setup(session)
    bg = BackgroundTasks()

    request = await start_generation(
        session, user, model.model_code, "a sunset", extra=None, credit_cost_override=None, background_tasks=bg
    )

    assert request.status == RequestStatus.processing
    assert request.provider_task_id == "task-123"
    mock_client.create_task.assert_awaited_once()
    call_kwargs = mock_client.create_task.await_args.kwargs
    assert call_kwargs["model"] == "veo3.1"
    assert call_kwargs["task_type"] == "veo3.1-video-fast"
    assert call_kwargs["input_"]["prompt"] == "a sunset"
    assert call_kwargs["input_"]["duration"] == "5s"


async def test_get_generation_returns_none_for_other_users_request(session):
    user, model = await _setup(session)
    other = User(telegram_id=2, username="other")
    session.add(other)
    await session.commit()

    from unittest.mock import AsyncMock, patch
    with patch("app.services.generation_service.PiAPIClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.create_task.return_value = "task-456"
        mock_client_cls.return_value = mock_client
        request = await start_generation(
            session, user, model.model_code, "x", extra=None, credit_cost_override=None,
            background_tasks=BackgroundTasks(),
        )

    result = await get_generation(session, other, request.id)
    assert result is None


async def test_webhook_completed_marks_success_and_spends_credits(session):
    user, model = await _setup(session)
    with patch("app.services.generation_service.PiAPIClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.create_task.return_value = "task-789"
        mock_client_cls.return_value = mock_client
        request = await start_generation(
            session, user, model.model_code, "x", extra=None, credit_cost_override=None,
            background_tasks=BackgroundTasks(),
        )

    from app.services.credit_service import get_balance
    balance_before = await get_balance(session, user)

    await handle_piapi_webhook(session, {
        "data": {
            "task_id": "task-789",
            "status": "completed",
            "output": {"video_url": "https://cdn.example.com/out.mp4"},
            "error": {"code": 0, "message": ""},
        }
    })

    await session.refresh(request)
    assert request.status == RequestStatus.success
    assert request.answer == "https://cdn.example.com/out.mp4"

    balance_after = await get_balance(session, user)
    assert balance_after == balance_before - model.credit_cost


async def test_webhook_is_idempotent(session):
    user, model = await _setup(session)
    with patch("app.services.generation_service.PiAPIClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.create_task.return_value = "task-idem"
        mock_client_cls.return_value = mock_client
        request = await start_generation(
            session, user, model.model_code, "x", extra=None, credit_cost_override=None,
            background_tasks=BackgroundTasks(),
        )

    payload = {
        "data": {
            "task_id": "task-idem", "status": "completed",
            "output": {"video_url": "https://cdn.example.com/out.mp4"},
            "error": {"code": 0, "message": ""},
        }
    }
    await handle_piapi_webhook(session, payload)
    from app.services.credit_service import get_balance
    balance_after_first = await get_balance(session, user)

    await handle_piapi_webhook(session, payload)  # PiAPI may retry webhooks
    balance_after_second = await get_balance(session, user)

    assert balance_after_first == balance_after_second


@patch("app.services.generation_service.PiAPIClient")
async def test_start_generation_create_task_failure_marks_request_error(mock_client_cls, session):
    """If PiAPI's create_task blows up (network error, outage, bad key), the AIRequest
    must not be left stuck at status=processing forever -- it should transition to
    status=error with a non-null error_message, and the exception must still propagate
    to the caller."""
    mock_client = AsyncMock()
    mock_client.create_task.side_effect = RuntimeError("piapi outage")
    mock_client_cls.return_value = mock_client

    user, model = await _setup(session)
    bg = BackgroundTasks()

    with pytest.raises(RuntimeError, match="piapi outage"):
        await start_generation(
            session, user, model.model_code, "a sunset", extra=None, credit_cost_override=None,
            background_tasks=bg,
        )

    saved = (
        await session.execute(select(AIRequest).where(AIRequest.model_code == model.model_code))
    ).scalar_one()

    assert saved.status == RequestStatus.error
    assert saved.error_message is not None
    assert saved.provider_task_id is None


async def test_start_generation_key_lookup_failure_marks_request_error(session):
    """Same guarantee as above, but for the key-lookup step (get_key_manager().get_key(...))
    raising ApiKeyNotConfiguredError before create_task is ever called."""
    from app.services.keys.exceptions import ApiKeyNotConfiguredError

    user, model = await _setup(session)
    bg = BackgroundTasks()

    with patch("app.services.generation_service.get_key_manager") as mock_get_key_manager:
        mock_manager = mock_get_key_manager.return_value
        mock_manager.get_key.side_effect = ApiKeyNotConfiguredError("no piapi key configured")

        with pytest.raises(ApiKeyNotConfiguredError):
            await start_generation(
                session, user, model.model_code, "a sunset", extra=None, credit_cost_override=None,
                background_tasks=bg,
            )

    saved = (
        await session.execute(select(AIRequest).where(AIRequest.model_code == model.model_code))
    ).scalar_one()

    assert saved.status == RequestStatus.error
    assert saved.error_message is not None
    assert saved.provider_task_id is None


@patch("app.services.generation_service.PiAPIClient")
async def test_credit_cost_override_ignored_for_piapi_models(mock_client_cls, session):
    """credit_cost_override must be ignored entirely on the PiAPI async path: the real
    charge always happens later in handle_piapi_webhook using model.credit_cost, so
    honoring an override here would let access-check and charge diverge. We prove this
    two ways: (1) an override far above the user's balance does NOT block the request
    (it would, if honored, since check_access would compare balance against the huge
    override instead of model.credit_cost); (2) the amount actually spent at webhook
    completion equals model.credit_cost, not the override."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = "task-override"
    mock_client_cls.return_value = mock_client

    user, model = await _setup(session, credit_cost=51)  # balance granted in _setup is 1000

    from app.services.credit_service import get_balance
    balance_before = await get_balance(session, user)

    # An override far larger than the balance would trip ModelNotAllowedError if honored.
    request = await start_generation(
        session, user, model.model_code, "x", extra=None, credit_cost_override=999_999,
        background_tasks=BackgroundTasks(),
    )
    assert request.status == RequestStatus.processing

    await handle_piapi_webhook(session, {
        "data": {
            "task_id": "task-override",
            "status": "completed",
            "output": {"video_url": "https://cdn.example.com/out.mp4"},
            "error": {"code": 0, "message": ""},
        }
    })

    balance_after = await get_balance(session, user)
    assert balance_after == balance_before - model.credit_cost  # NOT balance_before - 999_999


@patch("app.services.generation_service.ImageProvider")
async def test_dalle3_aspect_resolution_credit_multiplier(mock_image_provider_cls, session):
    tariff = Tariff(
        code="free", name="Free", price_rub=0, price_stars=0, period_days=36500,
        fast_limit=5, medium_limit=0, premium_limit=0, image_limit=0, daily_limit=5,
        max_input_tokens=2000, max_output_tokens=1000,
    )
    session.add(tariff)
    user = User(telegram_id=9, username="u9")
    session.add(user)
    await session.flush()
    from app.db.models import CreditTransaction
    from app.db.enums import CreditTxType
    session.add(CreditTransaction(user_id=user.id, type=CreditTxType.deposit, amount=1000, reason="test"))
    model = ModelConfig(
        model_code="dall-e-3", provider=ModelProvider.openai, display_name="Генерация картинок",
        category=ModelCategory.image, credit_cost=15, key_purpose="image",
    )
    session.add(model)
    await session.commit()

    mock_provider = AsyncMock()
    from app.services.ai.base import AIResult
    mock_provider.generate.return_value = AIResult(answer="https://x/out.png", input_tokens=0, output_tokens=0)
    mock_image_provider_cls.return_value = mock_provider

    from app.services.generation_service import compute_dalle3_credit_cost
    # landscape + 4k = multiplier 4 (see app/services/generation_service.py table)
    assert compute_dalle3_credit_cost(15, aspect="16:9", resolution="4k") == 60
    assert compute_dalle3_credit_cost(15, aspect="1:1", resolution="1k") == 15


async def _setup_image_model_with_quota(session, image_limit=5, credit_cost=20):
    # code="free" is required: the user has no active Subscription, so check_access
    # resolves their tariff via resolve_tariff_and_period -> get_free_tariff, which
    # looks up Tariff.code == "free" specifically.
    tariff = Tariff(
        code="free", name="Free", price_rub=0, price_stars=0, period_days=36500,
        fast_limit=5, medium_limit=5, premium_limit=5, image_limit=image_limit, daily_limit=50,
        max_input_tokens=2000, max_output_tokens=1000,
    )
    session.add(tariff)
    user = User(telegram_id=42, username="quota_user")
    session.add(user)
    await session.flush()
    from app.db.models import CreditTransaction
    from app.db.enums import CreditTxType
    session.add(CreditTransaction(user_id=user.id, type=CreditTxType.deposit, amount=1000, reason="test"))
    model = ModelConfig(
        model_code="piapi-image-model", provider=ModelProvider.piapi, display_name="PiAPI Image",
        category=ModelCategory.image, credit_cost=credit_cost, key_purpose="image",
        piapi_model="some-image-model", piapi_task_type="image-task", piapi_extra_input={},
    )
    session.add(model)
    await session.commit()
    return user, model


@patch("app.services.generation_service.PiAPIClient")
async def test_start_generation_blocks_concurrent_request_for_same_user(mock_client_cls, session):
    """A second start_generation call for the same user while the first request is
    still processing must be rejected -- otherwise a user can fire N concurrent
    generations that all pass check_access (which only reads balance, doesn't reserve)
    and all get billed by the provider while only one ever gets charged back to us."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = "task-lock-1"
    mock_client_cls.return_value = mock_client

    user, model = await _setup(session)

    first = await start_generation(
        session, user, model.model_code, "first", extra=None, credit_cost_override=None,
        background_tasks=BackgroundTasks(),
    )
    assert first.status == RequestStatus.processing

    mock_client.create_task.return_value = "task-lock-2"
    with pytest.raises(RequestInProgressError):
        await start_generation(
            session, user, model.model_code, "second", extra=None, credit_cost_override=None,
            background_tasks=BackgroundTasks(),
        )

    # The rejected second attempt must not have created a request or called PiAPI again.
    mock_client.create_task.assert_awaited_once()


@patch("app.services.generation_service.PiAPIClient")
async def test_lock_released_after_webhook_completes_allows_new_request(mock_client_cls, session, fake_redis):
    """The in-flight lock is only released once the generation is truly finished --
    for the PiAPI path that means inside handle_piapi_webhook, not at the end of
    start_generation (which returns immediately while PiAPI works asynchronously)."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = "task-release"
    mock_client_cls.return_value = mock_client

    user, model = await _setup(session)

    await start_generation(
        session, user, model.model_code, "x", extra=None, credit_cost_override=None,
        background_tasks=BackgroundTasks(),
    )
    assert f"ai_lock:{user.id}" in fake_redis._store

    # Still locked -- a concurrent second call is rejected.
    with pytest.raises(RequestInProgressError):
        await start_generation(
            session, user, model.model_code, "y", extra=None, credit_cost_override=None,
            background_tasks=BackgroundTasks(),
        )

    await handle_piapi_webhook(session, {
        "data": {
            "task_id": "task-release",
            "status": "completed",
            "output": {"video_url": "https://cdn.example.com/out.mp4"},
            "error": {"code": 0, "message": ""},
        }
    })

    assert f"ai_lock:{user.id}" not in fake_redis._store

    mock_client.create_task.return_value = "task-after-release"
    third = await start_generation(
        session, user, model.model_code, "z", extra=None, credit_cost_override=None,
        background_tasks=BackgroundTasks(),
    )
    assert third.status == RequestStatus.processing


@patch("app.services.generation_service.PiAPIClient")
async def test_lock_released_after_webhook_failure(mock_client_cls, session, fake_redis):
    """Symmetric to the completed case: a failed PiAPI generation must also release
    the lock so the user isn't permanently blocked by a failed request."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = "task-fail"
    mock_client_cls.return_value = mock_client

    user, model = await _setup(session)
    await start_generation(
        session, user, model.model_code, "x", extra=None, credit_cost_override=None,
        background_tasks=BackgroundTasks(),
    )
    assert f"ai_lock:{user.id}" in fake_redis._store

    await handle_piapi_webhook(session, {
        "data": {
            "task_id": "task-fail",
            "status": "failed",
            "error": {"code": 1, "message": "boom"},
        }
    })

    assert f"ai_lock:{user.id}" not in fake_redis._store


@patch("app.services.generation_service.PiAPIClient")
async def test_webhook_completion_spends_tariff_quota_when_available_for_image_model(mock_client_cls, session):
    """If check_access re-derived at completion time still finds tariff quota for the
    model's category (image, in this case), the charge must go through
    limit_service.spend (incrementing the tariff usage counter) instead of
    spend_credits -- otherwise subscribers get charged credits for generations their
    tariff already covers."""
    mock_client = AsyncMock()
    mock_client.create_task.return_value = "task-quota"
    mock_client_cls.return_value = mock_client

    user, model = await _setup_image_model_with_quota(session)
    await start_generation(
        session, user, model.model_code, "a cat", extra=None, credit_cost_override=None,
        background_tasks=BackgroundTasks(),
    )

    from app.services.credit_service import get_balance
    balance_before = await get_balance(session, user)

    await handle_piapi_webhook(session, {
        "data": {
            "task_id": "task-quota",
            "status": "completed",
            "output": {"image_url": "https://cdn.example.com/out.png"},
            "error": {"code": 0, "message": ""},
        }
    })

    balance_after = await get_balance(session, user)
    assert balance_after == balance_before  # credits untouched -- tariff quota used instead

    usage = (await session.execute(select(UsageLimit).where(UsageLimit.user_id == user.id))).scalar_one()
    assert usage.images_used == 1
