import logging

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.keys.enums import KeyPurpose, Provider
from app.services.keys.key_healthcheck import run_key_healthcheck


class FakeKeyManager:
    def __init__(self, configured: set[tuple[Provider, KeyPurpose]] = frozenset()):
        self.configured = set(configured)
        self.calls: list[tuple[Provider, KeyPurpose]] = []

    def has_key(self, provider, purpose):
        self.calls.append((provider, purpose))
        return (provider, purpose) in self.configured


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _model(code, category, provider, *, is_active=True) -> AiModel:
    cost_unit = CostUnit.tokens if category == ModelCategory.text else CostUnit.image
    return AiModel(
        provider=provider, category=category, code=code, display_name=code,
        provider_model_id=f"x/{code}", tier=ModelTier.standard, cost_unit=cost_unit,
        min_credits=0, recommended_credits=1, is_active=is_active,
    )


async def test_logs_ok_for_configured_key_and_missing_for_absent(session, caplog):
    session.add(_model("txt", ModelCategory.text, ModelProvider.openrouter))
    session.add(_model("vid", ModelCategory.video, ModelProvider.fal))
    await session.commit()
    manager = FakeKeyManager(configured={(Provider.OPENROUTER, KeyPurpose.TEXT)})

    with caplog.at_level(logging.INFO, logger="app.services.keys.key_healthcheck"):
        await run_key_healthcheck(session, manager)  # не кидает даже при MISSING

    ok = [r for r in caplog.records if "[OK]" in r.message]
    missing = [r for r in caplog.records if "[MISSING]" in r.message]
    assert len(ok) == 1 and "txt" in ok[0].message
    assert len(missing) == 1 and "vid" in missing[0].message


async def test_purpose_is_derived_from_category(session):
    session.add(_model("txt", ModelCategory.text, ModelProvider.openrouter))
    session.add(_model("img", ModelCategory.image, ModelProvider.fal))
    session.add(_model("vid", ModelCategory.video, ModelProvider.fal))
    await session.commit()
    manager = FakeKeyManager()

    await run_key_healthcheck(session, manager)

    assert set(manager.calls) == {
        (Provider.OPENROUTER, KeyPurpose.TEXT),
        (Provider.FAL, KeyPurpose.IMAGE),
        (Provider.FAL, KeyPurpose.VIDEO),
    }


async def test_inactive_models_are_skipped(session):
    session.add(_model("dead", ModelCategory.text, ModelProvider.openrouter, is_active=False))
    await session.commit()
    manager = FakeKeyManager()

    await run_key_healthcheck(session, manager)

    assert manager.calls == []
