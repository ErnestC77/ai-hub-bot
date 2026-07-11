import os
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
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
from app.services import antifraud_service as afs
from app.services import text_generation_service as tgs
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
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
    """In-memory Redis: set(nx)/get/delete/incr/incrby/decrby/expire.

    locked=True отклоняет ТОЛЬКО попытку взять ai_lock:* (эмуляция занятого
    per-user лока) -- antifraud-ключи (dup:*, rate_limit:*, daily_spend:*)
    живут как обычно. Тот же класс копируется в generation-тесты (Tasks 4-5).
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
    monkeypatch.setattr(afs, "redis_client", fake)
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


async def _seed(session, *models, balance=100, purchased=0, spent=0) -> User:
    user = User(
        telegram_id=1, username="u", credits_balance=balance,
        total_credits_purchased=purchased, total_credits_spent=spent,
    )
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


async def test_success_fills_provider_cost_usd(session, monkeypatch):
    user = await _seed(session, _model())  # price=1 -> input/output = 1 USD за 1M токенов
    provider = FakeProvider(result=AIResult(answer="ответ", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    await generate_text(session, user, "cheap", "привет")

    [request] = await _request_rows(session)
    # По ФАКТУ usage (500/200), не по оценке (2000/1000): 500/1e6*1 + 200/1e6*1 = 0.0007
    assert float(request.provider_cost_usd) == pytest.approx(0.0007)


async def test_tier_max_caps_output_tokens(session, monkeypatch):
    user = await _seed(session, _model(code="big", tier=ModelTier.ultra), purchased=1)
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
    assert request.status == RequestStatus.failed  # подтверждённая ошибка провайдера (Finding 2)
    assert request.charged_credits == 0
    assert request.provider_cost_usd == 0  # ничего не доставлено (Finding 1)
    assert request.error_message == "boom"

    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 100  # резерв возвращён полностью
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок снят и при ошибке


async def test_settle_failure_after_successful_call_refunds_and_reraises(session, fake_redis, monkeypatch):
    # Провайдер отвечает успешно, но settle_request после него падает произвольным
    # исключением (не AIError) -- это тоже должно приводить к refund, а не
    # к "зависшему" reserved-запросу с потерянным балансом.
    user = await _seed(session, _model())
    provider = FakeProvider(result=AIResult(answer="ответ", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)
    monkeypatch.setattr(tgs, "settle_request", AsyncMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        await generate_text(session, user, "cheap", "привет")

    [request] = await _request_rows(session)
    # Тот же except-блок, что и у provider-ошибки -> final_status=failed (Finding 2).
    assert request.status == RequestStatus.failed
    assert request.charged_credits == 0
    assert request.provider_cost_usd == 0  # Finding 1: ничего не доставлено
    assert request.error_message == "boom"

    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 100  # резерв возвращён полностью
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок снят и при ошибке после провайдера


# --- подтверждение дорогого запроса ---

async def test_expensive_estimate_without_confirm_raises_confirmation(session, fake_redis, monkeypatch):
    user = await _seed(
        session, _model(code="exp", price=20, min_credits=20, recommended=30),
        balance=500, purchased=1,
    )
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
    user = await _seed(
        session, _model(code="exp", price=20, min_credits=20, recommended=30),
        balance=500, purchased=1,
    )
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


# --- antifraud (фаза 5) ---

async def test_duplicate_prompt_within_cooldown_is_rejected(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(tgs, "_provider", provider)

    await generate_text(session, user, "cheap", "привет")
    with pytest.raises(DuplicateRequestError):
        await generate_text(session, user, "cheap", "привет")

    assert len(provider.calls) == 1               # до провайдера дошёл только первый
    assert len(await _request_rows(session)) == 1  # второй ничего не создал


async def test_confirm_retry_is_not_blocked_by_dedup(session, monkeypatch):
    # Повтор с confirm=True после 409 ConfirmationRequired приходит внутри
    # cooldown-окна и НЕ должен блокироваться дедупом.
    user = await _seed(
        session, _model(code="exp", price=20, min_credits=20, recommended=30),
        balance=500, purchased=1,
    )
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    with pytest.raises(ConfirmationRequiredError):
        await generate_text(session, user, "exp", "hi")

    result = await generate_text(session, user, "exp", "hi", confirm=True)
    assert result.charged_credits == 33


async def test_user_rate_limit_rejects_over_limit(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    bucket = afs._minute_bucket()
    fake_redis.store[f"rate_limit:user:{user.id}:{bucket}"] = "10"  # лимит уже выбран

    with pytest.raises(RateLimitExceededError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []
    assert await _tx_types(session) == []


async def test_model_rate_limit_rejects_over_limit(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    bucket = afs._minute_bucket()
    fake_redis.store[f"rate_limit:model:cheap:{bucket}"] = "60"

    with pytest.raises(RateLimitExceededError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []


async def test_ultra_model_blocked_until_first_purchase(session, fake_redis, monkeypatch):
    user = await _seed(session, _model(code="big", tier=ModelTier.ultra))  # purchased=0
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(tgs, "_provider", provider)

    with pytest.raises(TierNotAllowedError):
        await generate_text(session, user, "big", "hi")

    assert provider.calls == []
    assert await _request_rows(session) == []
    assert fake_redis.deleted == []  # отказ ДО взятия лока


async def test_free_tier_cap_blocks_when_estimate_exceeds_remaining(session, fake_redis, monkeypatch):
    # cap=100, spent=95, оценка cheap-модели = 7 -> 95 + 7 > 100.
    user = await _seed(session, _model(), purchased=0, spent=95)
    monkeypatch.setattr(tgs, "_provider", FakeProvider())

    with pytest.raises(FreeTierLimitExceededError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []
    assert await _tx_types(session) == []
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок был взят и снят в finally


async def test_daily_spend_limit_blocks_request(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    fake_redis.store[afs._daily_spend_key(user.id)] = "9998"  # 9998 + 7 > 10000

    with pytest.raises(DailySpendLimitExceededError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "9998"  # счётчик не тронут


async def test_success_records_daily_spend_adjusted_to_charged(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())  # оценка 7, факт 3
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "cheap", "привет")

    assert result.charged_credits == 3
    # +7 после reserve, затем -4 после settle (release) -> итог = фактическое списание
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "3"


async def test_provider_error_decrements_daily_spend_fully(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider(error=AIError("boom")))

    with pytest.raises(AIError):
        await generate_text(session, user, "cheap", "привет")

    # +7 после reserve, -7 после refund
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "0"
