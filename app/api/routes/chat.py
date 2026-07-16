from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.enums import ModelCategory
from app.db.models import AiModel, ModelOption, User
from app.services.pricing import IMAGE_EDIT_MULTIPLIER, VIDEO_MIN_CREDITS
from app.services.ai.base import AIError
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
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


class ModelOptionOut(BaseModel):
    kind: str
    code: str
    label: str
    credits_multiplier: float
    is_default: bool
    sort_order: int


class ModelOut(BaseModel):
    code: str
    display_name: str
    tier: str
    min_credits: int
    recommended_credits: int
    # Эффективный минимум списания: то, что бэкенд реально спишет как пол
    # (для видео max(min_credits, VIDEO_MIN_CREDITS), иначе min_credits). Фронт
    # использует ЕГО, а не min_credits -- иначе CTA показывал бы меньше, чем
    # спишется (баг C1: показывали 466, списывали 500 из-за VIDEO_MIN_CREDITS).
    min_charge_credits: int
    # Наборы значений диктует модель: у nano_banana опций качества не будет
    # вовсе (у fal нет ручки размера), у Wan их три. provider_params наружу
    # НЕ отдаём -- клиент шлёт код, а не сырые параметры.
    options: list[ModelOptionOut] = []
    # Множитель за генерацию по фото (i2i), либо null если модель редактирование
    # не поддерживает. Фронт по нему решает, показывать ли фото-бокс, и на сколько
    # дороже станет CTA с фото. Само число -- на бэке (IMAGE_EDIT_MULTIPLIER),
    # чтобы фронт его не хардкодил и они не разъехались.
    edit_multiplier: float | None = None


@router.get("/models", response_model=list[ModelOut])
async def list_models(
    category: ModelCategory = ModelCategory.text,
    session: AsyncSession = Depends(get_db),
) -> list[ModelOut]:
    models = (
        (
            await session.execute(
                select(AiModel)
                .where(
                    AiModel.category == category,
                    AiModel.is_active.is_(True),
                    AiModel.is_visible.is_(True),
                )
                .order_by(AiModel.sort_order)
            )
        )
        .scalars()
        .all()
    )

    # Опции всех моделей выдачи -- ОДНИМ запросом (не по модели на строку,
    # иначе N+1 на списке моделей).
    options_by_model_id: dict[int, list[ModelOption]] = {}
    model_ids = [m.id for m in models]
    if model_ids:
        option_rows = (
            (
                await session.execute(
                    select(ModelOption)
                    .where(
                        ModelOption.model_id.in_(model_ids),
                        ModelOption.is_active.is_(True),
                    )
                    .order_by(ModelOption.sort_order)
                )
            )
            .scalars()
            .all()
        )
        for opt in option_rows:
            options_by_model_id.setdefault(opt.model_id, []).append(opt)

    # provider_model_id намеренно не отдаётся клиенту (ТЗ).
    return [
        ModelOut(
            code=m.code,
            display_name=m.display_name,
            tier=m.tier.value,
            min_credits=m.min_credits,
            recommended_credits=m.recommended_credits,
            min_charge_credits=(
                max(m.min_credits, VIDEO_MIN_CREDITS)
                if category == ModelCategory.video
                else m.min_credits
            ),
            options=[
                ModelOptionOut(
                    kind=o.kind.value,
                    code=o.code,
                    label=o.label,
                    credits_multiplier=float(o.credits_multiplier),
                    is_default=o.is_default,
                    sort_order=o.sort_order,
                )
                for o in options_by_model_id.get(m.id, [])
            ],
            # edit-множитель только для моделей с i2i-маршрутом; у остальных null.
            edit_multiplier=IMAGE_EDIT_MULTIPLIER if m.provider_model_id_edit else None,
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
    except DuplicateRequestError as exc:
        raise HTTPException(
            status_code=429, detail="Слишком быстрый повтор запроса, подождите пару секунд"
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429, detail="Слишком много запросов, попробуйте через минуту"
        ) from exc
    except TierNotAllowedError as exc:
        raise HTTPException(
            status_code=403, detail="Эта модель доступна после первой покупки пакета"
        ) from exc
    except FreeTierLimitExceededError as exc:
        raise HTTPException(
            status_code=402, detail="Бесплатный лимит исчерпан, купите пакет кредитов"
        ) from exc
    except DailySpendLimitExceededError as exc:
        raise HTTPException(
            status_code=429, detail="Дневной лимит трат исчерпан, попробуйте завтра"
        ) from exc
    except AIError as exc:
        raise HTTPException(
            status_code=502, detail="Модель временно недоступна, попробуйте позже"
        ) from exc

    return ChatResponse(
        answer=result.answer,
        charged_credits=result.charged_credits,
        balance_after=result.balance_after,
    )
