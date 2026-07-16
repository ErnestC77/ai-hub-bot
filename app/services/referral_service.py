from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType
from app.db.models import Referral, User
from app.services.credit_service import grant_credits
from app.services.settings_service import get_setting


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


async def maybe_grant_referral_bonus(session: AsyncSession, referred_user_id: int) -> None:
    """Начисляет реферальный бонус обеим сторонам после первого успешного запроса
    приглашённого. Идемпотентно: атомарный claim по bonus_granted. Тихий no-op,
    если реферала нет, бонус уже выдан, или обе стороны выключены (=0).

    Вызывается ВНЕ try/except settle_request и в его же транзакции, до commit.
    """
    referrer_amount = await get_setting(
        session, "referral_bonus_referrer_credits", cast=int, default=0
    )
    referred_amount = await get_setting(
        session, "referral_bonus_referred_credits", cast=int, default=0
    )
    # Обе выключены -- НЕ клеймим: реферал отработает, когда админ вернёт ненулевое.
    if referrer_amount <= 0 and referred_amount <= 0:
        return

    referral = (
        await session.execute(
            select(Referral).where(Referral.referred_user_id == referred_user_id)
        )
    ).scalar_one_or_none()
    if referral is None or referral.bonus_granted:
        return

    # Атомарный claim: UPDATE берёт блокировку строки, параллельная транзакция
    # дождётся коммита и увидит bonus_granted=true -> rowcount 0. Размер выплаты
    # пишем тем же UPDATE (bonus_credits = выплата пригласившему).
    claimed = await session.execute(
        update(Referral)
        .where(Referral.referred_user_id == referred_user_id, Referral.bonus_granted.is_(False))
        .values(bonus_granted=True, bonus_credits=referrer_amount)
    )
    if claimed.rowcount == 0:
        return  # гонку проиграли -- тихий no-op

    if referrer_amount > 0:
        await grant_credits(
            session, referral.referrer_user_id, referrer_amount,
            reason="referral bonus (referrer)", tx_type=CreditTxType.referral_bonus,
            metadata={"referral_id": referral.id, "role": "referrer"},
        )
    if referred_amount > 0:
        await grant_credits(
            session, referred_user_id, referred_amount,
            reason="referral bonus (referred)", tx_type=CreditTxType.referral_bonus,
            metadata={"referral_id": referral.id, "role": "referred"},
        )
