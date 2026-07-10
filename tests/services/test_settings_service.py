import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.models import Setting
from app.services.pricing import PricingSettings
from app.services.settings_service import get_setting, load_pricing_settings, set_setting


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_get_setting_returns_cast_value(session):
    session.add(Setting(key="usd_to_rub_rate", value="80", type="float"))
    await session.commit()

    value = await get_setting(session, "usd_to_rub_rate", cast=float)
    assert value == 80.0
    assert isinstance(value, float)


async def test_get_setting_missing_key_returns_default(session):
    assert await get_setting(session, "no_such_key", cast=int, default=42) == 42
    assert await get_setting(session, "no_such_key") is None


async def test_load_pricing_settings_empty_db_uses_defaults(session):
    assert await load_pricing_settings(session) == PricingSettings()


async def test_load_pricing_settings_reads_overrides(session):
    session.add(Setting(key="margin_multiplier", value="3.0", type="float"))
    session.add(Setting(key="minimum_text_credits", value="5", type="int"))
    await session.commit()

    loaded = await load_pricing_settings(session)
    assert loaded.margin_multiplier == 3.0
    assert loaded.minimum_text_credits == 5
    assert loaded.usd_to_rub_rate == 80.0  # остальные -- дефолты


# --- set_setting ---

async def test_set_setting_creates_new_row(session):
    row = await set_setting(
        session, "daily_spend_limit_credits", "10000",
        type_="int", description="Дневной лимит трат на пользователя",
    )
    await session.commit()

    assert row.key == "daily_spend_limit_credits"
    assert row.value == "10000"
    assert row.type == "int"
    assert row.description == "Дневной лимит трат на пользователя"
    assert await get_setting(session, "daily_spend_limit_credits", cast=int) == 10000


async def test_set_setting_updates_value_only(session):
    session.add(Setting(key="free_tier_credit_cap", value="100", type="int",
                        description="исходное описание"))
    await session.commit()

    row = await set_setting(
        session, "free_tier_credit_cap", "250", type_="str", description="другое"
    )
    await session.commit()

    assert row.value == "250"
    assert row.type == "int"                       # тип НЕ меняется при обновлении
    assert row.description == "исходное описание"  # описание НЕ меняется
