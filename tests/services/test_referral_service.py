import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CreditTxType
from app.db.models import Referral, User, CreditTransaction, Setting
from app.services.referral_service import maybe_grant_referral_bonus


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _setup(session, *, referrer_bonus="20", referred_bonus="20", with_referral=True):
    referrer = User(telegram_id=1, username="ref", credits_balance=0)
    referred = User(telegram_id=2, username="new", credits_balance=0)
    session.add_all([referrer, referred])
    session.add_all([
        Setting(key="referral_bonus_referrer_credits", value=referrer_bonus, type="int"),
        Setting(key="referral_bonus_referred_credits", value=referred_bonus, type="int"),
    ])
    await session.flush()
    if with_referral:
        session.add(Referral(referrer_user_id=referrer.id, referred_user_id=referred.id))
    await session.commit()
    return referrer, referred


async def test_grants_both_sides(session):
    referrer, referred = await _setup(session)
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()

    assert (await session.get(User, referrer.id)).credits_balance == 20
    assert (await session.get(User, referred.id)).credits_balance == 20
    r = (await session.execute(select(Referral))).scalar_one()
    assert r.bonus_granted is True
    assert r.bonus_credits == 20
    txs = (await session.execute(
        select(CreditTransaction).where(CreditTransaction.type == CreditTxType.referral_bonus)
    )).scalars().all()
    assert len(txs) == 2


async def test_idempotent(session):
    referrer, referred = await _setup(session)
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()
    await maybe_grant_referral_bonus(session, referred.id)  # повтор
    await session.commit()

    assert (await session.get(User, referrer.id)).credits_balance == 20  # не удвоилось
    count = (await session.execute(
        select(func.count()).select_from(CreditTransaction)
        .where(CreditTransaction.type == CreditTxType.referral_bonus)
    )).scalar_one()
    assert count == 2


async def test_no_referral_is_noop(session):
    _, referred = await _setup(session, with_referral=False)
    await maybe_grant_referral_bonus(session, referred.id)  # реферала нет
    await session.commit()
    assert (await session.get(User, referred.id)).credits_balance == 0


async def test_disabled_keeps_flag_false(session):
    referrer, referred = await _setup(session, referrer_bonus="0", referred_bonus="0")
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()
    r = (await session.execute(select(Referral))).scalar_one()
    assert r.bonus_granted is False  # реферал доступен для будущего начисления
    assert (await session.get(User, referrer.id)).credits_balance == 0


async def test_bonus_does_not_unlock_premium(session):
    referrer, referred = await _setup(session)
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()
    # total_credits_purchased остаётся 0 -- иначе рефссылка = ключ к video/ultra
    assert (await session.get(User, referrer.id)).total_credits_purchased == 0
    assert (await session.get(User, referred.id)).total_credits_purchased == 0


async def test_one_side_disabled_grants_only_other(session):
    referrer, referred = await _setup(session, referred_bonus="0")  # приглашённому 0
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()
    assert (await session.get(User, referrer.id)).credits_balance == 20
    assert (await session.get(User, referred.id)).credits_balance == 0
