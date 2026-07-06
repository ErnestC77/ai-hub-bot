from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Referral, User


@dataclass
class ReferralStats:
    referred_count: int
    bonus_count: int


async def get_referral_stats(session: AsyncSession, user: User) -> ReferralStats:
    row = (
        await session.execute(
            select(
                func.count(Referral.id),
                func.count(Referral.id).filter(Referral.bonus_granted.is_(True)),
            ).where(Referral.referrer_user_id == user.id)
        )
    ).one()
    return ReferralStats(referred_count=row[0], bonus_count=row[1])


async def record_referral(session: AsyncSession, referrer_telegram_id: int, referred_user: User) -> None:
    if referred_user.telegram_id == referrer_telegram_id:
        return

    referrer = (
        await session.execute(select(User).where(User.telegram_id == referrer_telegram_id))
    ).scalar_one_or_none()
    if referrer is None:
        return

    session.add(Referral(referrer_user_id=referrer.id, referred_user_id=referred_user.id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
