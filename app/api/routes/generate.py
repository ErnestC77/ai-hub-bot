from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.models import User
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
    get_generation,
    start_media_generation,
)

router = APIRouter(dependencies=[Depends(current_user)])


class GenerateRequest(BaseModel):
    # Security-фикс фазы 3: поля credit_cost_override больше НЕТ -- стоимость
    # считается только на бэкенде (media_generation_service). Неизвестные поля
    # в JSON pydantic молча игнорирует.
    model_code: str
    prompt: str
    image_url: str | None = None         # для image-edit
    duration_seconds: int | None = None  # для video (per-second модели)
    confirm: bool = False


class GenerateResponse(BaseModel):
    request_id: int
    estimated_credits: int


class GenerationStatusOut(BaseModel):
    status: str
    result_url: str | None
    error_message: str | None
    charged_credits: int


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> GenerateResponse | JSONResponse:
    try:
        request = await start_media_generation(
            session, user, body.model_code, body.prompt,
            image_url=body.image_url,
            duration_seconds=body.duration_seconds,
            confirm=body.confirm,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    except ConfirmationRequiredError as exc:
        # Тело ровно {"estimated_credits": N} (без "detail") -- конвенция фазы 2
        # (/api/chat): клиент отличает этот 409 от "запрос уже выполняется".
        return JSONResponse(status_code=409, content={"estimated_credits": exc.estimated_credits})
    except RequestInProgressError as exc:
        raise HTTPException(status_code=409, detail=exc.user_message) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов") from exc
    except AIError as exc:
        raise HTTPException(
            status_code=502, detail="Модель временно недоступна, попробуйте позже"
        ) from exc

    return GenerateResponse(request_id=request.id, estimated_credits=request.estimated_credits)


@router.get("/generate/{request_id}", response_model=GenerationStatusOut)
async def generation_status(
    request_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> GenerationStatusOut:
    request = await get_generation(session, user, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="request not found")

    return GenerationStatusOut(
        status=request.status.value,
        result_url=request.result_url,  # durable-колонка ai_requests.result_url
        error_message=request.error_message,
        charged_credits=request.charged_credits,  # реальное списание, не хардкод 0
    )
