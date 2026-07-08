from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.enums import ModelCategory
from app.db.models import AiModel, User
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.text_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    ModelUnavailableError,
    RequestInProgressError,
    generate_text,
)

router = APIRouter(dependencies=[Depends(current_user)])


class ChatRequest(BaseModel):
    model_code: str
    prompt: str = Field(min_length=1, max_length=4000)
    confirm: bool = False


class ChatResponse(BaseModel):
    answer: str
    charged_credits: int
    balance_after: int


class ModelOut(BaseModel):
    code: str
    display_name: str
    tier: str
    min_credits: int
    recommended_credits: int


@router.get("/models", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_db)) -> list[ModelOut]:
    models = (
        (
            await session.execute(
                select(AiModel)
                .where(
                    AiModel.category == ModelCategory.text,
                    AiModel.is_active.is_(True),
                    AiModel.is_visible.is_(True),
                )
                .order_by(AiModel.sort_order)
            )
        )
        .scalars()
        .all()
    )
    # provider_model_id намеренно не отдаётся клиенту (ТЗ).
    return [
        ModelOut(
            code=m.code,
            display_name=m.display_name,
            tier=m.tier.value,
            min_credits=m.min_credits,
            recommended_credits=m.recommended_credits,
        )
        for m in models
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatResponse | JSONResponse:
    try:
        result = await generate_text(
            session, user, body.model_code, body.prompt, confirm=body.confirm
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=404, detail="Эта модель временно отключена.") from exc
    except ConfirmationRequiredError as exc:
        # Тело ровно {"estimated_credits": N} (без "detail") -- клиент отличает
        # этот 409 от "запрос уже выполняется" по наличию estimated_credits.
        return JSONResponse(status_code=409, content={"estimated_credits": exc.estimated_credits})
    except RequestInProgressError as exc:
        raise HTTPException(status_code=409, detail=exc.user_message) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов") from exc
    except AIError as exc:
        raise HTTPException(
            status_code=502, detail="Модель временно недоступна, попробуйте позже"
        ) from exc

    return ChatResponse(
        answer=result.answer,
        charged_credits=result.charged_credits,
        balance_after=result.balance_after,
    )
