from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.api.schemas import CategoryLimitOut, LimitsOut, MeOut, SubscriptionStatusOut
from app.db.models import User
from app.services.credit_service import get_balance as get_credit_balance
from app.services.limit_service import get_usage_snapshot
from app.services.subscription_service import get_active_subscription, get_tariff

router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/me", response_model=MeOut)
async def get_me(user: User = Depends(current_user), session: AsyncSession = Depends(get_db)) -> MeOut:
    subscription = await get_active_subscription(session, user.id)
    expires_at = subscription.expires_at if subscription else None

    snapshot = await get_usage_snapshot(session, user)
    credits_balance = await get_credit_balance(session, user)

    return MeOut(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        is_admin=user.is_admin,
        active_model=user.active_model,
        tariff_code=snapshot.tariff_code,
        tariff_name=snapshot.tariff_name,
        subscription_expires_at=expires_at,
        credits_balance=credits_balance,
        limits=LimitsOut(
            daily_used=snapshot.daily_used,
            daily_limit=snapshot.daily_limit,
            categories={
                category: CategoryLimitOut(used=cl.used, limit=cl.limit)
                for category, cl in snapshot.categories.items()
            },
        ),
    )


@router.get("/subscription/me", response_model=SubscriptionStatusOut)
async def get_subscription_status(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> SubscriptionStatusOut:
    subscription = await get_active_subscription(session, user.id)
    if subscription:
        tariff = await get_tariff(session, subscription.tariff_id)
        return SubscriptionStatusOut(
            tariff_code=tariff.code if tariff else "unknown",
            status=subscription.status.value,
            expires_at=subscription.expires_at,
        )

    return SubscriptionStatusOut(tariff_code="free", status="active", expires_at=None)
