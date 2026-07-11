"""Статистика для GET /admin/stats.

Фаза 6: поверх базовых счётчиков фазы 5 добавлены revenue/margin/avg и
breakdown-списки model_usage / top_users_by_spend -- агрегация на лету по
ai_requests (GROUP BY), без отдельной таблицы (YAGNI, см. спеку фазы 6).
provider_cost_usd заполняется generation-сервисами с фазы 6.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType, PaymentStatus, RequestStatus
from app.db.models import AIRequest, CreditTransaction, Payment, User
from app.services.pricing import PricingSettings
from app.services.settings_service import get_setting

TOP_LIMIT = 10  # обе breakdown-выборки -- топ-10 (спека фазы 6)


@dataclass
class ModelUsageStat:
    model_code: str
    requests: int
    credits_spent: int
    cost_usd: float


@dataclass
class UserSpendStat:
    telegram_id: int
    credits_spent: int


@dataclass
class DailyStats:
    new_users: int
    payments_count: int
    payments_amount_rub: float
    ai_requests: int
    api_cost_usd: float
    errors: int
    revenue_credits: int
    revenue_rub_estimated: float
    margin_rub: float
    avg_cost_credits: float
    model_usage: list[ModelUsageStat]
    top_users_by_spend: list[UserSpendStat]


@dataclass
class MonthlyStats:
    revenue_rub: float
    credits_purchases_count: int


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
            select(func.coalesce(func.sum(AIRequest.provider_cost_usd), 0)).where(
                AIRequest.created_at >= day_start
            )
        )
    ).scalar_one()

    errors = (
        await session.execute(
            select(func.count(AIRequest.id)).where(
                AIRequest.created_at >= day_start, AIRequest.status == RequestStatus.failed
            )
        )
    ).scalar_one()

    revenue_credits = (
        await session.execute(
            select(func.coalesce(func.sum(AIRequest.charged_credits), 0)).where(
                AIRequest.status == RequestStatus.completed,
                AIRequest.created_at >= day_start,
            )
        )
    ).scalar_one()

    defaults = PricingSettings()
    rub_per_credit = await get_setting(
        session, "rub_per_credit", cast=float, default=defaults.rub_per_credit
    )
    usd_to_rub_rate = await get_setting(
        session, "usd_to_rub_rate", cast=float, default=defaults.usd_to_rub_rate
    )
    revenue_rub_estimated = revenue_credits * rub_per_credit
    margin_rub = revenue_rub_estimated - float(api_cost) * usd_to_rub_rate
    avg_cost_credits = revenue_credits / ai_requests if ai_requests else 0.0

    model_spend = func.coalesce(func.sum(AIRequest.charged_credits), 0).label("credits_spent")
    model_rows = (
        await session.execute(
            select(
                AIRequest.model_code,
                func.count(AIRequest.id).label("requests"),
                model_spend,
                func.coalesce(func.sum(AIRequest.provider_cost_usd), 0).label("cost_usd"),
            )
            .where(AIRequest.created_at >= day_start)
            .group_by(AIRequest.model_code)
            .order_by(model_spend.desc())
            .limit(TOP_LIMIT)
        )
    ).all()
    model_usage = [
        ModelUsageStat(
            model_code=row.model_code,
            requests=row.requests,
            credits_spent=row.credits_spent,
            cost_usd=float(row.cost_usd),
        )
        for row in model_rows
    ]

    user_spend = func.coalesce(func.sum(AIRequest.charged_credits), 0).label("credits_spent")
    user_rows = (
        await session.execute(
            select(User.telegram_id, user_spend)
            .select_from(AIRequest)
            .join(User, User.id == AIRequest.user_id)
            .where(AIRequest.created_at >= day_start)
            # users.telegram_id уникален (unique index), поэтому группировка по нему
            # эквивалентна GROUP BY user_id из спеки и валидна на Postgres и sqlite.
            .group_by(User.telegram_id)
            .order_by(user_spend.desc())
            .limit(TOP_LIMIT)
        )
    ).all()
    top_users_by_spend = [
        UserSpendStat(telegram_id=row.telegram_id, credits_spent=row.credits_spent)
        for row in user_rows
    ]

    return DailyStats(
        new_users=new_users,
        payments_count=payments_count,
        payments_amount_rub=float(payments_amount),
        ai_requests=ai_requests,
        api_cost_usd=float(api_cost),
        errors=errors,
        revenue_credits=revenue_credits,
        revenue_rub_estimated=revenue_rub_estimated,
        margin_rub=margin_rub,
        avg_cost_credits=avg_cost_credits,
        model_usage=model_usage,
        top_users_by_spend=top_users_by_spend,
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

    credits_purchases_count = (
        await session.execute(
            select(func.count(CreditTransaction.id)).where(
                CreditTransaction.type == CreditTxType.purchase,
                CreditTransaction.created_at >= month_start,
            )
        )
    ).scalar_one()

    return MonthlyStats(
        revenue_rub=float(revenue), credits_purchases_count=credits_purchases_count
    )
