"""Приветственные кредиты новому пользователю (welcome_bonus_credits)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CreditTxType
from app.db.models import CreditTransaction, Setting, User
from app.db.seed import SETTINGS_ROWS
from app.services.user_service import get_or_create_user


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _set_bonus(session, value: str) -> None:
    session.add(Setting(key="welcome_bonus_credits", value=value, type="int",
                        description="test"))
    await session.commit()


async def test_new_user_gets_welcome_bonus(session):
    await _set_bonus(session, "220")

    user = await get_or_create_user(session, telegram_id=1, username="new")

    assert user.credits_balance == 220
    tx = (await session.execute(select(CreditTransaction))).scalars().one()
    assert tx.type == CreditTxType.welcome_bonus
    assert tx.amount == 220
    assert tx.balance_before == 0 and tx.balance_after == 220


async def test_welcome_bonus_does_not_count_as_purchase(session):
    """Бонус не должен открывать видео/ultra и снимать free-cap.

    Оба гейта в antifraud смотрят на total_credits_purchased > 0, поэтому
    начисление типом purchase молча сделало бы новичка «покупателем».
    """
    await _set_bonus(session, "220")

    user = await get_or_create_user(session, telegram_id=1, username="new")

    assert user.total_credits_purchased == 0


async def test_returning_user_is_not_paid_twice(session):
    await _set_bonus(session, "220")

    await get_or_create_user(session, telegram_id=1, username="new")
    user = await get_or_create_user(session, telegram_id=1, username="new")

    assert user.credits_balance == 220
    txs = (await session.execute(select(CreditTransaction))).scalars().all()
    assert len(txs) == 1


async def test_zero_setting_disables_bonus(session):
    await _set_bonus(session, "0")

    user = await get_or_create_user(session, telegram_id=1, username="new")

    assert user.credits_balance == 0
    assert (await session.execute(select(CreditTransaction))).scalars().all() == []


async def test_missing_setting_disables_bonus(session):
    """Пустая таблица settings -- не повод раздавать кредиты по дефолту."""
    user = await get_or_create_user(session, telegram_id=1, username="new")

    assert user.credits_balance == 0


async def test_free_tier_cap_fits_welcome_bonus():
    """Потолок free-трат обязан вмещать подарок.

    Иначе бонус недодаёт молча: баланс 220 виден, а тратится только cap
    (при cap=100 -- 3 фото вместо обещанных 5), и понять это по коду нельзя --
    два независимых ключа настроек связаны только этим инвариантом.
    """
    by_key = {s["key"]: int(s["value"]) for s in SETTINGS_ROWS if s["type"] == "int"}

    assert by_key["free_tier_credit_cap"] >= by_key["welcome_bonus_credits"]
