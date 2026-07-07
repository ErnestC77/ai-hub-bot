from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.enums import ModelCategory
from app.db.models import ModelConfig, User
from app.services.access_service import AccessError
from app.services.ai.ai_router import AIRouter, ModelNotFoundError
from app.services.ai.base import AIError

router = APIRouter(dependencies=[Depends(current_user)])
ai_router = AIRouter()

# DALL-E 3 реально поддерживает только 3 холста. UI предлагает привычный
# набор соотношений сторон (как у конкурентов) -- каждое соотношение
# схлопывается в ближайший по форме реальный холст DALL-E.
IMAGE_ASPECT_TO_BUCKET: dict[str, str] = {
    "auto": "square",
    "1:1": "square",
    "4:3": "square",
    "4:5": "square",
    "5:4": "square",
    "3:2": "landscape",
    "16:9": "landscape",
    "21:9": "landscape",
    "2:3": "portrait",
    "3:4": "portrait",
    "9:16": "portrait",
}
IMAGE_BUCKET_TO_SIZE = {
    "square": "1024x1024",
    "portrait": "1024x1792",
    "landscape": "1792x1024",
}

# "1K"/"2K" -- реальные квалити-тиры OpenAI (standard/hd). "4K" -- честный
# 2x Lanczos-апскейл результата (app/services/ai/image_service.py), а не
# просто маркетинговый лейбл -- поэтому дороже, чем 2K.
_RESOLUTION_TO_QUALITY = {"1k": "standard", "2k": "hd", "4k": "hd"}
_COST_MULTIPLIER: dict[tuple[str, str], int] = {
    ("square", "1k"): 1,
    ("square", "2k"): 2,
    ("square", "4k"): 3,
    ("landscape", "1k"): 2,
    ("landscape", "2k"): 3,
    ("landscape", "4k"): 4,
    ("portrait", "1k"): 2,
    ("portrait", "2k"): 3,
    ("portrait", "4k"): 4,
}


def _compute_image_credit_cost(base_cost: int, aspect: str, resolution: str) -> int:
    bucket = IMAGE_ASPECT_TO_BUCKET.get(aspect, "square")
    multiplier = _COST_MULTIPLIER[(bucket, resolution)]
    return max(1, round(base_cost * multiplier))


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


ASPECT_OPTIONS = Literal["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "5:4", "9:16", "16:9", "21:9"]
RESOLUTION_OPTIONS = Literal["1k", "2k", "4k"]


class ImageGenerateRequest(BaseModel):
    model_code: str
    prompt: str = Field(min_length=1, max_length=6000)
    aspect: ASPECT_OPTIONS = "auto"
    resolution: RESOLUTION_OPTIONS = "1k"


class ImageGenerateResponse(BaseModel):
    image_url: str
    credit_cost: int


@router.post("/chat/image", response_model=ImageGenerateResponse)
async def generate_image(
    body: ImageGenerateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ImageGenerateResponse:
    model = (
        await session.execute(select(ModelConfig).where(ModelConfig.model_code == body.model_code))
    ).scalar_one_or_none()
    if model is None or model.category != ModelCategory.image:
        raise HTTPException(status_code=404, detail="model not found")

    bucket = IMAGE_ASPECT_TO_BUCKET.get(body.aspect, "square")
    credit_cost = _compute_image_credit_cost(model.credit_cost, body.aspect, body.resolution)

    try:
        result = await ai_router.generate(
            session,
            user,
            body.model_code,
            body.prompt,
            extra={
                "size": IMAGE_BUCKET_TO_SIZE[bucket],
                "quality": _RESOLUTION_TO_QUALITY[body.resolution],
                "resolution": body.resolution,
            },
            credit_cost_override=credit_cost,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    except AccessError as exc:
        raise HTTPException(status_code=403, detail=exc.user_message) from exc
    except AIError as exc:
        raise HTTPException(
            status_code=502, detail="Модель временно недоступна, попробуйте позже"
        ) from exc

    return ImageGenerateResponse(image_url=result.answer, credit_cost=credit_cost)
