from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ModelConfig, Tariff, UsageLimit, User
from app.services.credit_service import get_balance as get_credit_balance
from app.services.limit_fields import CATEGORY_LIMIT_FIELD
from app.services.subscription_service import get_active_subscription, get_free_tariff, get_tariff

# Лимиты Free-тарифа — разовые, не периодические, поэтому у них фиксированное
# "вечное" окно usage_limits вместо периода активной подписки.
FREE_TIER_PERIOD_START = datetime(2020, 1, 1, tzinfo=timezone.utc)
FREE_TIER_PERIOD_END = FREE_TIER_PERIOD_START + timedelta(days=36500)

PROMPT_CHARS_PER_TOKEN = 3


class AccessError(Exception):
    user_message = "Доступ ограничен."


class UserBlockedError(AccessError):
    user_message = "Ваш аккаунт заблокирован."


class ModelUnavailableError(AccessError):
    user_message = "Эта модель временно отключена."


class ModelNotAllowedError(AccessError):
    user_message = "Эта модель недоступна на вашем тарифе, а кредитов для оплаты не хватает. Оформите подписку или купите кредиты в разделе «Тарифы»."


class DailyLimitExceededError(AccessError):
    user_message = "Дневной лимит по тарифу исчерпан, а кредитов не хватает. Попробуйте завтра или купите кредиты."


class MonthlyLimitExceededError(AccessError):
    user_message = "Лимит по тарифу исчерпан, а кредитов не хватает. Оформите подписку или купите кредиты, чтобы продолжить."


class PromptTooLongError(AccessError):
    user_message = "Сообщение слишком длинное, сократите его."


class RequestInProgressError(AccessError):
    user_message = "Дождитесь ответа на предыдущий запрос."


@dataclass
class AccessContext:
    tariff: Tariff
    usage_limit: UsageLimit
    max_output_tokens: int
    # Тарифная квота на эту категорию исчерпана (или модель вообще не входит в
    # тариф) -- запрос оплачивается кредитами, а не счётчиком usage_limits.
    use_credits: bool = False


async def get_or_create_usage_limit(
    session: AsyncSession, user: User, subscription_id: int | None, period_start: datetime, period_end: datetime
) -> UsageLimit:
    usage = (
        await session.execute(
            select(UsageLimit).where(
                UsageLimit.user_id == user.id,
                UsageLimit.subscription_id == subscription_id,
                UsageLimit.period_start == period_start,
            )
        )
    ).scalar_one_or_none()

    if usage is None:
        usage = UsageLimit(
            user_id=user.id,
            subscription_id=subscription_id,
            period_start=period_start,
            period_end=period_end,
        )
        session.add(usage)
        await session.commit()

    return usage


async def resolve_tariff_and_period(
    session: AsyncSession, user: User
) -> tuple[Tariff, int | None, datetime, datetime]:
    """Активный тариф пользователя + границы периода для usage_limits."""
    subscription = await get_active_subscription(session, user.id)
    if subscription:
        tariff = await get_tariff(session, subscription.tariff_id)
        return tariff, subscription.id, subscription.started_at, subscription.expires_at

    tariff = await get_free_tariff(session)
    return tariff, None, FREE_TIER_PERIOD_START, FREE_TIER_PERIOD_END


async def check_access(
    session: AsyncSession, user: User, model: ModelConfig, prompt: str, credit_cost: int | None = None
) -> AccessContext:
    """7 проверок доступа перед AI-запросом (раздел 19 bot_ai.md) + кредиты
    поверх тарифа: если квота тарифа по категории исчерпана (или модель вообще
    не входит в тариф), но на балансе хватает кредитов -- запрос всё равно
    выполняется, а оплачивается уже из кредитов, а не из usage_limits.
    """
    if user.is_blocked:
        raise UserBlockedError()

    if not model.is_active:
        raise ModelUnavailableError()

    effective_credit_cost = model.credit_cost if credit_cost is None else credit_cost

    tariff, subscription_id, period_start, period_end = await resolve_tariff_and_period(session, user)

    estimated_tokens = max(1, len(prompt) // PROMPT_CHARS_PER_TOKEN)
    if estimated_tokens > tariff.max_input_tokens or estimated_tokens > model.max_context_tokens:
        raise PromptTooLongError()

    usage = await get_or_create_usage_limit(session, user, subscription_id, period_start, period_end)

    today = datetime.now(timezone.utc).date()
    if usage.updated_at.date() != today:
        usage.daily_used = 0
        await session.commit()

    limit_field, used_field = CATEGORY_LIMIT_FIELD[model.category]
    category_limit = getattr(tariff, limit_field)

    tariff_has_quota = (
        category_limit > 0
        and usage.daily_used < tariff.daily_limit
        and getattr(usage, used_field) < category_limit
    )

    if tariff_has_quota:
        return AccessContext(tariff=tariff, usage_limit=usage, max_output_tokens=tariff.max_output_tokens)

    balance = await get_credit_balance(session, user)
    if balance >= effective_credit_cost:
        return AccessContext(
            tariff=tariff, usage_limit=usage, max_output_tokens=tariff.max_output_tokens, use_credits=True
        )

    if category_limit <= 0:
        raise ModelNotAllowedError()
    if usage.daily_used >= tariff.daily_limit:
        raise DailyLimitExceededError()
    raise MonthlyLimitExceededError()
