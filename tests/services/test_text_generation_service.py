import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

import pytest
from sqlalchemy import func, select
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
from app.services import text_generation_service as tgs
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.credit_service import InsufficientBalanceError
from app.services.text_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    ModelUnavailableError,
    RequestInProgressError,
    TextGenerationResult,
    generate_text,
)


class FakeRedis:
    def __init__(self, locked: bool = False):
        self.locked = locked
        self.deleted: list[str] = []

    async def set(self, key, value, nx=False, ex=None):
        return None if self.locked else True

    async def delete(self, key):
        self.deleted.append(key)


class FakeProvider(AIProvider):
    def __init__(self, result: AIResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, int]] = []

    async def generate(self, model, prompt, max_output_tokens, extra=None):
        self.calls.append((model.code, prompt, max_output_tokens))
        if self.error is not None:
            raise self.error
        return self.result


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
    monkeypatch.setattr(tgs, "redis_client", fake)
    return fake


def _model(code="cheap", *, tier=ModelTier.economy, price=1, min_credits=3,
           recommended=3, is_active=True, fallback=None) -> AiModel:
    return AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text, code=code,
        display_name=code, provider_model_id=f"vendor/{code}", tier=tier,
        input_price_usd_per_1m_tokens=price, output_price_usd_per_1m_tokens=price,
        cost_unit=CostUnit.tokens, min_credits=min_credits,
        recommended_credits=recommended, is_active=is_active,
        fallback_model_code=fallback,
    )


async def _seed(session, *models, balance=100) -> User:
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
            await session.execute(select(CreditTransaction.type).order_by(CreditTransaction.id))
        ).all()
    ]


# --- успешная генерация ---

async def test_success_reserves_settles_and_returns_result(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())  # цена 1 -> оценка 7 кредитов
    provider = FakeProvider(result=AIResult(answer="ответ", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "cheap", "привет")

    assert isinstance(result, TextGenerationResult)
    assert result.answer == "ответ"
    assert result.charged_credits == 3      # actual по факту (500/200) = 3
    assert result.balance_after == 97       # 100 - 3

    assert provider.calls == [("cheap", "привет", 1000)]  # TIER_MAX[economy]

    [request] = await _request_rows(session)
    assert request.status == RequestStatus.completed
    assert request.model_code == "cheap"
    assert request.provider == "openrouter"
    assert request.estimated_credits == 7
    assert request.reserved_credits == 7
    assert request.charged_credits == 3
    assert request.input_tokens == 500
    assert request.output_tokens == 200
    assert request.prompt_preview == "привет"

    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.release]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]


async def test_tier_max_caps_output_tokens(session, monkeypatch):
    user = await _seed(session, _model(code="big", tier=ModelTier.ultra))
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(tgs, "_provider", provider)

    await generate_text(session, user, "big", "hi")

    assert provider.calls[0][2] == 12000  # TIER_MAX[ultra]


# --- ошибка провайдера -> refund ---

async def test_provider_error_refunds_and_reraises(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider(error=AIError("boom")))

    with pytest.raises(AIError):
        await generate_text(session, user, "cheap", "привет")

    [request] = await _request_rows(session)
    assert request.status == RequestStatus.refunded
    assert request.charged_credits == 0
    assert request.error_message == "boom"

    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 100  # резерв возвращён полностью
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок снят и при ошибке


# --- подтверждение дорогого запроса ---

async def test_expensive_estimate_without_confirm_raises_confirmation(session, fake_redis, monkeypatch):
    user = await _seed(session, _model(code="exp", price=20, min_credits=20, recommended=30), balance=500)
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(tgs, "_provider", provider)

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await generate_text(session, user, "exp", "hi")

    assert exc_info.value.estimated_credits == 138  # оценка 2000/1000 при цене 20
    assert provider.calls == []                      # до провайдера не дошли
    assert await _request_rows(session) == []        # ничего не создано
    assert await _tx_types(session) == []            # ничего не зарезервировано
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 500
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок снят


async def test_expensive_estimate_with_confirm_proceeds(session, monkeypatch):
    user = await _seed(session, _model(code="exp", price=20, min_credits=20, recommended=30), balance=500)
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "exp", "hi", confirm=True)

    assert result.charged_credits == 33   # actual при цене 20 и usage 500/200
    assert result.balance_after == 467    # 500 - 33


# --- недостаточный баланс ---

async def test_insufficient_balance_rolls_back_pending_request(session, monkeypatch):
    user = await _seed(session, _model(), balance=5)  # оценка 7 > 5
    user_id = user.id  # захват ДО rollback: после него доступ к user.id -- sync
    # lazy-load (MissingGreenlet), см. комментарий в test_credit_service.py:82.
    monkeypatch.setattr(tgs, "_provider", FakeProvider())

    with pytest.raises(InsufficientBalanceError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []  # pending-запись откатилась
    assert await _tx_types(session) == []
    fetched = await session.get(User, user_id)
    assert fetched.credits_balance == 5


# --- fallback ---

async def test_inactive_model_falls_back_to_fallback_code(session, monkeypatch):
    primary = _model(code="dead", is_active=False, fallback="alive")
    fallback = _model(code="alive")
    user = await _seed(session, primary, fallback)
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "dead", "hi")

    assert result.charged_credits == 3
    assert provider.calls == [("alive", "hi", 1000)]
    [request] = await _request_rows(session)
    assert request.model_code == "alive"  # биллинг на фактическую модель


async def test_more_expensive_fallback_without_confirm_raises_confirmation(session, monkeypatch):
    primary = _model(code="dead", recommended=3, is_active=False, fallback="pricey")
    fallback = _model(code="pricey", recommended=10)  # дороже по recommended_credits
    user = await _seed(session, primary, fallback)
    monkeypatch.setattr(tgs, "_provider", FakeProvider())

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await generate_text(session, user, "dead", "hi")

    assert exc_info.value.estimated_credits == 7  # оценка по fallback-модели (цена 1)
    assert await _request_rows(session) == []


async def test_more_expensive_fallback_with_confirm_proceeds(session, monkeypatch):
    primary = _model(code="dead", recommended=3, is_active=False, fallback="pricey")
    fallback = _model(code="pricey", recommended=10)
    user = await _seed(session, primary, fallback)
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "dead", "hi", confirm=True)

    assert result.charged_credits == 3
    assert provider.calls[0][0] == "pricey"


# --- ошибки резолва модели ---

async def test_unknown_code_raises_model_not_found(session, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    with pytest.raises(ModelNotFoundError):
        await generate_text(session, user, "no_such_model", "hi")


async def test_inactive_without_fallback_raises_model_unavailable(session, monkeypatch):
    user = await _seed(session, _model(code="dead", is_active=False))
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    with pytest.raises(ModelUnavailableError):
        await generate_text(session, user, "dead", "hi")


async def test_inactive_fallback_chain_raises_aierror(session, monkeypatch):
    primary = _model(code="dead", is_active=False, fallback="also_dead")
    fallback = _model(code="also_dead", is_active=False)
    user = await _seed(session, primary, fallback)
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    with pytest.raises(AIError):
        await generate_text(session, user, "dead", "hi")


# --- per-user лок ---

async def test_busy_lock_raises_request_in_progress(session, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "redis_client", FakeRedis(locked=True))
    monkeypatch.setattr(tgs, "_provider", FakeProvider())

    with pytest.raises(RequestInProgressError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []
    assert await _tx_types(session) == []
