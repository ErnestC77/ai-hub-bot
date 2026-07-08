import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import (
    CostUnit,
    CreditTxType,
    ModelCategory,
    ModelProvider,
    ModelTier,
    RequestStatus,
)
from app.db.models import AiModel, AIRequest, CreditPackage, CreditTransaction, Setting, User


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_user_new_credit_columns_default_to_zero(session):
    user = User(telegram_id=1, username="u", default_model_code=None)
    session.add(user)
    await session.commit()

    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 0
    assert fetched.total_credits_purchased == 0
    assert fetched.total_credits_spent == 0
    assert fetched.default_model_code is None
    assert not hasattr(fetched, "active_model")


async def test_ai_model_round_trip(session):
    model = AiModel(
        provider=ModelProvider.openrouter,
        category=ModelCategory.text,
        code="deepseek_v3",
        display_name="DeepSeek V3",
        provider_model_id="deepseek/deepseek-chat",
        tier=ModelTier.economy,
        input_price_usd_per_1m_tokens=0.27,
        output_price_usd_per_1m_tokens=1.10,
        fixed_cost_usd=0,
        cost_unit=CostUnit.tokens,
        min_credits=3,
        recommended_credits=3,
        max_context_tokens=128000,
        is_active=True,
        is_visible=True,
        sort_order=10,
    )
    session.add(model)
    await session.commit()

    fetched = await session.get(AiModel, model.id)
    assert fetched.code == "deepseek_v3"
    assert fetched.tier == ModelTier.economy
    assert fetched.cost_unit == CostUnit.tokens
    assert float(fetched.input_price_usd_per_1m_tokens) == 0.27


async def test_credit_package_round_trip(session):
    pkg = CreditPackage(code="start", title="START", credits=1000, price_rub=149, description="Для знакомства с ботом")
    session.add(pkg)
    await session.commit()

    fetched = await session.get(CreditPackage, pkg.id)
    assert fetched.credits == 1000
    assert fetched.is_active is True


async def test_setting_round_trip(session):
    session.add(Setting(key="usd_to_rub_rate", value="80", type="float", description="Курс USD→RUB"))
    await session.commit()

    fetched = await session.get(Setting, "usd_to_rub_rate")
    assert fetched.value == "80"
    assert fetched.type == "float"


async def test_ai_request_and_transaction_round_trip(session):
    user = User(telegram_id=2)
    session.add(user)
    await session.flush()

    request = AIRequest(
        user_id=user.id,
        provider="openrouter",
        model_code="deepseek_v3",
        category=ModelCategory.text,
        status=RequestStatus.reserved,
        prompt_preview="напиши хокку про кредиты"[:200],
        estimated_credits=10,
        reserved_credits=10,
    )
    session.add(request)
    await session.flush()

    tx = CreditTransaction(
        user_id=user.id,
        type=CreditTxType.reserve,
        amount=-10,
        balance_before=100,
        balance_after=90,
        provider="openrouter",
        model_code="deepseek_v3",
        request_id=request.id,
        description="reserve for request",
        metadata_json={"input_tokens": 2000, "output_tokens": 1000},
    )
    session.add(tx)
    await session.commit()

    fetched_req = await session.get(AIRequest, request.id)
    assert fetched_req.status == RequestStatus.reserved
    assert fetched_req.insufficient_balance_after_usage is False
    assert fetched_req.charged_credits == 0
    assert fetched_req.completed_at is None

    fetched_tx = await session.get(CreditTransaction, tx.id)
    assert fetched_tx.amount == -10
    assert fetched_tx.balance_before == 100
    assert fetched_tx.balance_after == 90
    assert fetched_tx.request_id == request.id
    assert fetched_tx.metadata_json == {"input_tokens": 2000, "output_tokens": 1000}


async def test_legacy_models_are_gone():
    import app.db.models as models

    for legacy in ("ModelConfig", "Tariff", "Subscription", "UsageLimit"):
        assert not hasattr(models, legacy)


async def test_ai_request_result_url_round_trip(session):
    user = User(telegram_id=3)
    session.add(user)
    await session.flush()

    request = AIRequest(
        user_id=user.id,
        provider="fal",
        model_code="flux_dev",
        category=ModelCategory.image,
        status=RequestStatus.reserved,
        prompt_preview="a bear",
        estimated_credits=100,
        reserved_credits=100,
    )
    session.add(request)
    await session.commit()

    fetched = await session.get(AIRequest, request.id)
    assert fetched.result_url is None  # nullable, пусто до вебхука

    fetched.result_url = "https://cdn.fal.media/out.png"
    await session.commit()

    again = await session.get(AIRequest, request.id)
    assert again.result_url == "https://cdn.fal.media/out.png"
