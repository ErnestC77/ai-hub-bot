from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.models import User
from app.services.subscription_service import get_active_subscription, list_active_tariffs

router = APIRouter(dependencies=[Depends(current_user)])


class TariffOut(BaseModel):
    code: str
    name: str
    description: str | None
    price_rub: float
    price_stars: int
    period_days: int
    fast_limit: int
    medium_limit: int
    premium_limit: int
    image_limit: int
    is_current: bool


@router.get("/tariffs", response_model=list[TariffOut])
async def get_tariffs(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[TariffOut]:
    tariffs = await list_active_tariffs(session)
    subscription = await get_active_subscription(session, user.id)
    current_tariff_id = subscription.tariff_id if subscription else None

    return [
        TariffOut(
            code=t.code,
            name=t.name,
            description=t.description,
            price_rub=float(t.price_rub),
            price_stars=t.price_stars,
            period_days=t.period_days,
            fast_limit=t.fast_limit,
            medium_limit=t.medium_limit,
            premium_limit=t.premium_limit,
            image_limit=t.image_limit,
            is_current=t.id == current_tariff_id,
        )
        for t in tariffs
        if t.code != "free"
    ]
