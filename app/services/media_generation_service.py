"""Медиа-flow (image/video) поверх движка кредитов -- фаза 3, замена
generation_service.py (PiAPI/DALL-E) на fal.ai.

Отличие от текстового flow (фаза 2): вызов провайдера асинхронный. fal.ai
принимает задачу сразу, а результат доставляет вебхуком (handle_fal_webhook),
поэтому per-user Redis-лок НЕ снимается в конце start_media_generation --
он живёт до обработки вебхука (тот же паттерн, что у старого PiAPI-flow).
Синхронная ошибка ДО успешного submit снимает лок немедленно.

Стоимость считается ТОЛЬКО здесь, на бэкенде: клиентского
credit_cost_override из старого API больше не существует (security-фикс).
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.enums import ModelCategory, RequestStatus
from app.db.models import AIRequest, AiModel, User
from app.redis_client import redis_client
from app.services.ai.base import AIError
from app.services.ai.fal_client import FalClient
from app.services.credit_service import (
    InsufficientBalanceError,
    refund_request,
    reserve_credits,
)
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider
from app.services.pricing import calculate_image_credits, calculate_video_credits

logger = logging.getLogger(__name__)

# Страховочный TTL на медленную видео-генерацию (несколько минут) -- штатно лок
# снимается явно в handle_fal_webhook, не по TTL (как в старом PiAPI-flow).
AI_LOCK_TTL_SECONDS = 900
VIDEO_DEFAULT_DURATION_SECONDS = 5  # дефолт длительности из ТЗ
IMAGE_CONFIRM_THRESHOLD_CREDITS = 300
VIDEO_CONFIRM_THRESHOLD_CREDITS = 1000


class ModelNotFoundError(Exception):
    """model_code отсутствует в каталоге image/video-моделей."""


class RequestInProgressError(Exception):
    user_message = "Дождитесь ответа на предыдущий запрос."


class ConfirmationRequiredError(Exception):
    """Оценка дороже порога (300 image / 1000 video) без confirm=True."""

    def __init__(self, estimated_credits: int):
        self.estimated_credits = estimated_credits
        super().__init__(f"confirmation required: estimated {estimated_credits} credits")


def _webhook_url() -> str:
    return f"{settings.backend_public_url}/api/fal/webhook?secret={settings.fal_webhook_secret}"


async def _get_media_model(session: AsyncSession, model_code: str) -> AiModel:
    model = (
        await session.execute(
            select(AiModel).where(
                AiModel.code == model_code,
                AiModel.category.in_((ModelCategory.image, ModelCategory.video)),
            )
        )
    ).scalar_one_or_none()
    if model is None:
        raise ModelNotFoundError(model_code)
    return model


async def start_media_generation(
    session: AsyncSession,
    user: User,
    model_code: str,
    prompt: str,
    *,
    image_url: str | None = None,
    duration_seconds: int | None = None,
    confirm: bool = False,
) -> AIRequest:
    model = await _get_media_model(session, model_code)

    # category зафиксирована в строке каталога -- клиент её не выбирает.
    # Для image множитель редактирования включается всегда, когда передан
    # image_url, без проверки "поддерживает ли модель edit" (см. спеку фазы 3).
    if model.category == ModelCategory.image:
        estimated = calculate_image_credits(
            model, quantity=1, megapixels=1.0, is_edit=image_url is not None
        )
        threshold = IMAGE_CONFIRM_THRESHOLD_CREDITS
    else:
        estimated = calculate_video_credits(
            model, duration_seconds or VIDEO_DEFAULT_DURATION_SECONDS
        )
        threshold = VIDEO_CONFIRM_THRESHOLD_CREDITS

    if estimated > threshold and not confirm:
        # Ничего не создано, лок ещё не брался.
        raise ConfirmationRequiredError(estimated)

    lock_key = f"ai_lock:{user.id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=AI_LOCK_TTL_SECONDS)
    if not acquired:
        raise RequestInProgressError()

    try:
        request = AIRequest(
            user_id=user.id,
            provider="fal",
            model_code=model.code,
            category=model.category,
            status=RequestStatus.pending,
            prompt_preview=prompt[:200],
            estimated_credits=estimated,
            reserved_credits=estimated,
        )
        session.add(request)
        await session.flush()

        try:
            await reserve_credits(
                session,
                user.id,
                estimated,
                request_id=request.id,
                provider="fal",
                model_code=model.code,
            )
        except InsufficientBalanceError:
            # Убрать pending-AIRequest вместе с несостоявшимся резервом.
            await session.rollback()
            raise
        request.status = RequestStatus.reserved
        await session.commit()  # резерв фиксируется ДО внешнего HTTP-вызова
    except Exception:
        # Любая синхронная ошибка до submit -- лок снимается сразу.
        await redis_client.delete(lock_key)
        raise

    purpose = KeyPurpose.IMAGE if model.category == ModelCategory.image else KeyPurpose.VIDEO
    try:
        api_key = get_key_manager().get_key(Provider.FAL, purpose)
        client = FalClient(api_key=api_key)
        if model.category == ModelCategory.image:
            fal_request_id = await client.submit_image(
                model, prompt, image_url=image_url, webhook_url=_webhook_url()
            )
        else:
            fal_request_id = await client.submit_video(
                model,
                prompt,
                duration_seconds=duration_seconds or VIDEO_DEFAULT_DURATION_SECONDS,
                webhook_url=_webhook_url(),
            )
    except Exception as exc:
        # Резерв уже закоммичен -- возвращаем его и снимаем лок.
        request.error_message = str(exc)
        await refund_request(session, request, reason=f"fal submit failed: {exc}")
        await session.commit()
        await redis_client.delete(lock_key)
        raise AIError(f"fal submit failed: {exc}") from exc

    request.provider_response_id = fal_request_id
    await session.commit()
    # Лок НЕ снимается: генерация продолжается асинхронно до handle_fal_webhook.
    return request


async def get_generation(session: AsyncSession, user: User, request_id: int) -> AIRequest | None:
    request = await session.get(AIRequest, request_id)
    if request is None or request.user_id != user.id:
        return None
    return request
