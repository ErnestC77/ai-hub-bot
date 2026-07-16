import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelOptionKind, ModelProvider, ModelTier
from app.db.models import AiModel, ModelOption


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _model(session) -> AiModel:
    m = AiModel(
        provider=ModelProvider.fal, category=ModelCategory.video, code="vid",
        display_name="Vid", provider_model_id="fal-ai/vid", tier=ModelTier.standard,
        cost_unit=CostUnit.second, min_credits=100, recommended_credits=200,
    )
    session.add(m)
    await session.commit()
    return m


async def test_option_roundtrips_with_json_params(session):
    """provider_params -- JSON, а не строка: типы значений обязаны пережить
    round-trip. Kling ждёт duration строкой "10", Wan -- num_frames числом 161.
    Если типы поедут, fal отвергнет запрос (или, хуже, молча проигнорирует)."""
    m = await _model(session)
    session.add(ModelOption(
        model_id=m.id, kind=ModelOptionKind.duration, code="10s", label="10 сек",
        provider_params={"duration": "10", "num_frames": 161},
        credits_multiplier=2.0, is_default=False, sort_order=20,
    ))
    await session.commit()

    row = (await session.execute(select(ModelOption))).scalar_one()
    assert row.provider_params == {"duration": "10", "num_frames": 161}
    assert isinstance(row.provider_params["duration"], str)
    assert isinstance(row.provider_params["num_frames"], int)
    assert float(row.credits_multiplier) == 2.0


async def test_defaults_are_sane(session):
    m = await _model(session)
    session.add(ModelOption(
        model_id=m.id, kind=ModelOptionKind.quality, code="720p", label="720p",
        provider_params={"resolution": "720p"},
    ))
    await session.commit()
    row = (await session.execute(select(ModelOption))).scalar_one()
    assert float(row.credits_multiplier) == 1.0
    assert row.is_default is False
    assert row.is_active is True
    assert row.sort_order == 0


async def test_code_unique_per_model_and_kind(session):
    m = await _model(session)
    session.add(ModelOption(model_id=m.id, kind=ModelOptionKind.duration, code="5s",
                            label="5 сек", provider_params={}))
    await session.commit()
    session.add(ModelOption(model_id=m.id, kind=ModelOptionKind.duration, code="5s",
                            label="дубль", provider_params={}))
    with pytest.raises(IntegrityError):
        await session.commit()
