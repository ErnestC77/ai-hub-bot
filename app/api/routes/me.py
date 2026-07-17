from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.api.schemas import MeOut
from app.db.enums import ModelCategory
from app.db.models import AiModel, User

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


class DefaultModelUpdate(BaseModel):
    model_code: str


@router.put("/me/default-model", response_model=MeOut)
async def set_default_model(
    payload: DefaultModelUpdate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> MeOut:
    """Пользователь сам выбирает модель по умолчанию для чата.

    Разрешаем ТОЛЬКО видимую текстовую модель: дефолт применяется на входе в чат
    (resolveModel), а туда попадают лишь text-модели -- сохранить сюда video/image
    или скрытый код значило бы записать значение, которое чат молча проигнорирует.
    """
    model = (
        await session.execute(
            select(AiModel).where(
                AiModel.code == payload.model_code,
                AiModel.category == ModelCategory.text,
                AiModel.is_active.is_(True),
                AiModel.is_visible.is_(True),
            )
        )
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Модель недоступна для выбора")

    user.default_model_code = model.code
    await session.commit()

    return MeOut(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        is_admin=user.is_admin,
        default_model_code=user.default_model_code,
        credits_balance=user.credits_balance,
        total_credits_purchased=user.total_credits_purchased,
        total_credits_spent=user.total_credits_spent,
    )
