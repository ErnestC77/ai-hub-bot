from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import SubscriptionStatus
from app.db.models import Subscription, Tariff


async def get_active_subscription(session: AsyncSession, user_id: int) -> Subscription | None:
    return (
        await session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.active,
                Subscription.expires_at > datetime.now(timezone.utc),
            )
            .order_by(Subscription.expires_at.desc())
        )
    ).scalars().first()


async def get_tariff(session: AsyncSession, tariff_id: int) -> Tariff | None:
    return await session.get(Tariff, tariff_id)


async def get_free_tariff(session: AsyncSession) -> Tariff | None:
    return (
        await session.execute(select(Tariff).where(Tariff.code == "free"))
    ).scalar_one_or_none()


async def get_tariff_by_code(session: AsyncSession, code: str) -> Tariff | None:
    return (
        await session.execute(select(Tariff).where(Tariff.code == code, Tariff.is_active.is_(True)))
    ).scalar_one_or_none()


async def list_active_tariffs(session: AsyncSession) -> list[Tariff]:
    return list(
        (await session.execute(select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.price_rub)))
        .scalars()
        .all()
    )
