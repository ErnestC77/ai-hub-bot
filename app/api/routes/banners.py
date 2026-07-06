from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.models import Banner

router = APIRouter(dependencies=[Depends(current_user)])


class BannerOut(BaseModel):
    id: int
    title: str
    subtitle: str | None
    badge_text: str | None
    cta_text: str
    image_url: str
    action_type: str
    action_value: str


@router.get("/banners", response_model=list[BannerOut])
async def get_banners(session: AsyncSession = Depends(get_db)) -> list[BannerOut]:
    banners = (
        await session.execute(
            select(Banner).where(Banner.is_active.is_(True)).order_by(Banner.sort_order, Banner.id)
        )
    ).scalars().all()
    return [BannerOut(**{k: getattr(b, k) for k in BannerOut.model_fields}) for b in banners]
