from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.config import settings
from app.db.models import User
from app.services.referral_service import get_referral_stats
from app.services.settings_service import get_setting

router = APIRouter(dependencies=[Depends(current_user)])


class ReferralOut(BaseModel):
    link: str
    referred_count: int
    bonus_count: int
    earned_credits: int
    bonus_amount: int


@router.get("/referral/me", response_model=ReferralOut)
async def get_my_referral(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> ReferralOut:
    stats = await get_referral_stats(session, user)
    # bonus_amount -- текущая настройка (не историческая сумма), для промо-строки типа
    # "приглашай друзей -- получай N кредитов".
    bonus_amount = await get_setting(session, "referral_bonus_referrer_credits", cast=int, default=0)
    link = f"https://t.me/{settings.bot_username}?start=ref_{user.telegram_id}"
    return ReferralOut(
        link=link,
        referred_count=stats.referred_count,
        bonus_count=stats.bonus_count,
        earned_credits=stats.earned_credits,
        bonus_amount=bonus_amount,
    )
