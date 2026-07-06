from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentStatus, RequestStatus, SubscriptionStatus
from app.db.models import AIRequest, Payment, Subscription, User


@dataclass
class DailyStats:
    new_users: int
    payments_count: int
    payments_amount_rub: float
    ai_requests: int
    api_cost_usd: float
    errors: int


@dataclass
class MonthlyStats:
    revenue_rub: float
    active_subscriptions: int


async def get_daily_stats(session: AsyncSession) -> DailyStats:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    new_users = (
        await session.execute(select(func.count(User.id)).where(User.created_at >= day_start))
    ).scalar_one()

    payments_count, payments_amount = (
        await session.execute(
            select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.succeeded,
                Payment.paid_at >= day_start,
                Payment.currency == "RUB",
            )
        )
    ).one()

    ai_requests = (
        await session.execute(select(func.count(AIRequest.id)).where(AIRequest.created_at >= day_start))
    ).scalar_one()

    api_cost = (
        await session.execute(
            select(func.coalesce(func.sum(AIRequest.estimated_cost_usd), 0)).where(
                AIRequest.created_at >= day_start
            )
        )
    ).scalar_one()

    errors = (
        await session.execute(
            select(func.count(AIRequest.id)).where(
                AIRequest.created_at >= day_start, AIRequest.status == RequestStatus.error
            )
        )
    ).scalar_one()

    return DailyStats(
        new_users=new_users,
        payments_count=payments_count,
        payments_amount_rub=float(payments_amount),
        ai_requests=ai_requests,
        api_cost_usd=float(api_cost),
        errors=errors,
    )


async def get_monthly_stats(session: AsyncSession) -> MonthlyStats:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    revenue = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.succeeded,
                Payment.paid_at >= month_start,
                Payment.currency == "RUB",
            )
        )
    ).scalar_one()

    active_subscriptions = (
        await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status == SubscriptionStatus.active, Subscription.expires_at > now
            )
        )
    ).scalar_one()

    return MonthlyStats(revenue_rub=float(revenue), active_subscriptions=active_subscriptions)
