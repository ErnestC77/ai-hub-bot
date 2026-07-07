from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.models import User
from app.services.access_service import AccessError
from app.services.generation_service import ModelNotFoundError, get_generation, start_generation

router = APIRouter(dependencies=[Depends(current_user)])


class GenerateRequest(BaseModel):
    model_code: str
    prompt: str
    extra: dict | None = None
    credit_cost_override: int | None = None


class GenerateResponse(BaseModel):
    request_id: int


class GenerationStatusOut(BaseModel):
    status: str
    result_url: str | None
    error_message: str | None
    credit_cost: int


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    try:
        request = await start_generation(
            session, user, body.model_code, body.prompt, body.extra, body.credit_cost_override, background_tasks,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    except AccessError as exc:
        raise HTTPException(status_code=403, detail=exc.user_message) from exc

    return GenerateResponse(request_id=request.id)


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
        result_url=request.answer,
        error_message=request.error_message,
        credit_cost=0,
    )
