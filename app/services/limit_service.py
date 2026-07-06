from dataclasses import dataclass

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelCategory
from app.db.models import User, UsageLimit
from app.services.access_service import get_or_create_usage_limit, resolve_tariff_and_period
from app.services.limit_fields import CATEGORY_LIMIT_FIELD


@dataclass
class CategoryLimit:
    used: int
    limit: int


@dataclass
class UsageSnapshot:
    tariff_code: str
    tariff_name: str
    daily_used: int
    daily_limit: int
    categories: dict[str, CategoryLimit]


async def get_usage_snapshot(session: AsyncSession, user: User) -> UsageSnapshot:
    tariff, subscription_id, period_start, period_end = await resolve_tariff_and_period(session, user)
    usage = await get_or_create_usage_limit(session, user, subscription_id, period_start, period_end)

    categories = {
        category.value: CategoryLimit(used=getattr(usage, used_field), limit=getattr(tariff, limit_field))
        for category, (limit_field, used_field) in CATEGORY_LIMIT_FIELD.items()
    }

    return UsageSnapshot(
        tariff_code=tariff.code,
        tariff_name=tariff.name,
        daily_used=usage.daily_used,
        daily_limit=tariff.daily_limit,
        categories=categories,
    )


async def spend(session: AsyncSession, usage_limit: UsageLimit, category: ModelCategory) -> None:
    """Атомарно списывает лимит. Вызывать только после успешного ответа модели."""
    _, used_field = CATEGORY_LIMIT_FIELD[category]
    used_column = getattr(UsageLimit, used_field)

    await session.execute(
        update(UsageLimit)
        .where(UsageLimit.id == usage_limit.id)
        .values(
            **{used_field: used_column + 1},
            daily_used=UsageLimit.daily_used + 1,
            updated_at=func.now(),
        )
    )
    await session.commit()
