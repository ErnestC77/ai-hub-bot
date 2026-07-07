from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.models import ModelConfig, User
from app.services.access_service import AccessError
from app.services.ai.ai_router import AIRouter, ModelNotFoundError
from app.services.ai.base import AIError

router = APIRouter(dependencies=[Depends(current_user)])
ai_router = AIRouter()


class ChatRequest(BaseModel):
    model_code: str
    prompt: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    input_tokens: int
    output_tokens: int


class ModelOut(BaseModel):
    model_code: str
    display_name: str
    category: str
    is_premium: bool
    credit_cost: int


@router.get("/models", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_db)) -> list[ModelOut]:
    models = (
        await session.execute(select(ModelConfig).where(ModelConfig.is_active.is_(True)))
    ).scalars().all()
    return [
        ModelOut(
            model_code=m.model_code,
            display_name=m.display_name,
            category=m.category.value,
            is_premium=m.is_premium,
            credit_cost=m.credit_cost,
        )
        for m in models
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatResponse:
    try:
        result = await ai_router.generate(session, user, body.model_code, body.prompt)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    except AccessError as exc:
        raise HTTPException(status_code=403, detail=exc.user_message) from exc
    except AIError as exc:
        raise HTTPException(
            status_code=502, detail="Модель временно недоступна, попробуйте позже"
        ) from exc

    return ChatResponse(
        answer=result.answer, input_tokens=result.input_tokens, output_tokens=result.output_tokens
    )
