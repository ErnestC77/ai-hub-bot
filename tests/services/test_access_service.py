import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import ModelCategory, ModelProvider
from app.db.models import CreditTransaction, ModelConfig, Tariff, User
from app.db.enums import CreditTxType
from app.services.access_service import ModelNotAllowedError, check_access


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _make_free_tariff(session):
    tariff = Tariff(
        code="free", name="Free", price_rub=0, price_stars=0, period_days=36500,
        fast_limit=5, medium_limit=0, premium_limit=0, image_limit=0, daily_limit=5,
        max_input_tokens=2000, max_output_tokens=1000,
    )
    session.add(tariff)
    await session.commit()
    return tariff


async def test_video_model_with_no_credits_raises_not_allowed(session):
    await _make_free_tariff(session)
    user = User(telegram_id=1, username="u")
    session.add(user)
    await session.flush()

    model = ModelConfig(
        model_code="piapi-veo3-fast", provider=ModelProvider.piapi, display_name="AI Video Fast",
        category=ModelCategory.video, credit_cost=51, key_purpose="video",
    )
    session.add(model)
    await session.commit()

    with pytest.raises(ModelNotAllowedError):
        await check_access(session, user, model, "a sunset")


async def test_video_model_with_enough_credits_uses_credits(session):
    await _make_free_tariff(session)
    user = User(telegram_id=2, username="u2")
    session.add(user)
    await session.flush()

    session.add(CreditTransaction(user_id=user.id, type=CreditTxType.deposit, amount=100, reason="test"))
    await session.commit()

    model = ModelConfig(
        model_code="piapi-veo3-fast", provider=ModelProvider.piapi, display_name="AI Video Fast",
        category=ModelCategory.video, credit_cost=51, key_purpose="video",
    )
    session.add(model)
    await session.commit()

    ctx = await check_access(session, user, model, "a sunset")
    assert ctx.use_credits is True
