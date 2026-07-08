from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.api.schemas import MeOut
from app.db.models import User

router = APIRouter(dependencies=[Depends(current_user)])

# ТЗ: если у пользователя не выбрана модель -- DeepSeek V3 (sort_order=10,
# самая дешёвая и первая в каталоге).
DEFAULT_MODEL_CODE = "deepseek_v3"


@router.get("/me", response_model=MeOut)
async def get_me(user: User = Depends(current_user)) -> MeOut:
    return MeOut(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        is_admin=user.is_admin,
        default_model_code=user.default_model_code or DEFAULT_MODEL_CODE,
        credits_balance=user.credits_balance,
        total_credits_purchased=user.total_credits_purchased,
        total_credits_spent=user.total_credits_spent,
    )
