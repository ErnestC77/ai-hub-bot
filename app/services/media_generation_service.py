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
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.enums import ModelCategory, RequestStatus
from app.db.models import AIRequest, AiModel, User
from app.redis_client import redis_client
from app.services.ai.base import AIError
from app.services.ai.fal_client import FalClient, extract_result_url
from app.services.antifraud_service import (
    check_daily_spend_limit,
    check_duplicate_request,
    check_free_tier_cap,
    check_rate_limits,
    check_tier_allowed,
    load_antifraud_settings,
    record_daily_spend,
)
from app.services.credit_service import (
    InsufficientBalanceError,
    refund_request,
    reserve_credits,
    settle_request,
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

RECONCILE_STALE_AFTER_MINUTES = 20  # безопасно больше AI_LOCK_TTL_SECONDS (900с = 15 мин):
# к этому времени Redis-лок уже точно истёк сам по себе, так что явно чистить его
# не обязательно, но мы всё равно пробуем на случай нестандартного TTL/окружения.


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

    # Antifraud pre-checks (фаза 5) -- быстрый отказ до оценки и лока.
    af_settings = await load_antifraud_settings(session)
    if not confirm:
        # confirm=True -- осознанный повтор после 409 ConfirmationRequired:
        # он приходит внутри cooldown-окна и не должен блокироваться дедупом.
        await check_duplicate_request(user.id, model_code, prompt, settings=af_settings)
    await check_rate_limits(user.id, model.code, settings=af_settings)
    await check_tier_allowed(user, model)

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

    # Antifraud (фаза 5): free-tier cap и дневной лимит -- после оценки, ДО
    # confirmation-gate (запись в daily-счётчик будет после reserve).
    await check_free_tier_cap(user, estimated, settings=af_settings)
    await check_daily_spend_limit(user.id, estimated, settings=af_settings)

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

    await record_daily_spend(user.id, estimated)

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
        await record_daily_spend(user.id, -estimated)
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


async def handle_fal_webhook(session: AsyncSession, payload: dict) -> None:
    """Обрабатывает доставку fal-вебхука: {"request_id", "status": "OK"|"ERROR",
    "payload": {...}}.

    Идемпотентность: атомарный UPDATE ... WHERE status=reserved "закрепляет"
    запрос за первой доставкой (тот же приём, что в старом handle_piapi_webhook);
    повторная доставка получает rowcount=0 и выходит, не трогая ни кредиты,
    ни лок. Claim и settle/refund выполняются в ОДНОЙ транзакции: на Postgres
    UPDATE берёт блокировку строки, конкурентная доставка дожидается commit
    и видит уже не-reserved статус.
    """
    fal_request_id = payload.get("request_id")
    if not fal_request_id:
        return

    request = (
        await session.execute(
            select(AIRequest).where(AIRequest.provider_response_id == fal_request_id)
        )
    ).scalar_one_or_none()
    if request is None:
        return  # неизвестный request_id -- не наш запрос

    status = payload.get("status")
    result_payload = payload.get("payload") or {}
    lock_key = f"ai_lock:{request.user_id}"

    if status == "OK":
        result_url = extract_result_url(result_payload)
        claimed = await session.execute(
            update(AIRequest)
            .where(AIRequest.id == request.id, AIRequest.status == RequestStatus.reserved)
            .values(result_url=result_url)
        )
        if claimed.rowcount == 0:
            return  # повторная доставка -- идемпотентный no-op
        try:
            if result_url is None:
                # Форму ответа извлечь не удалось: кредиты за недоставленный
                # результат не списываем. PLACEHOLDER: дополнить
                # fal_client.extract_result_url новой формой и уточнить перед
                # продакшн-запуском.
                request.error_message = "fal webhook: could not extract result url"
                await refund_request(
                    session, request, reason="fal webhook: could not extract result url"
                )
                await record_daily_spend(request.user_id, -request.reserved_credits)
            else:
                # quantity/duration известны на этапе запроса, поэтому
                # actual == estimated == reserved: settle_request штатно вернёт
                # None (без корректирующей транзакции) -- см. спеку фазы 3.
                await settle_request(session, request, request.estimated_credits)
            await session.commit()
        finally:
            await redis_client.delete(lock_key)
    elif status == "ERROR":
        # PLACEHOLDER: точная форма тела ошибки fal не подтверждена (уточнить
        # перед продакшн-запуском); перебираем известных кандидатов.
        error_message = str(
            payload.get("error") or result_payload.get("detail") or "generation failed"
        )
        claimed = await session.execute(
            update(AIRequest)
            .where(AIRequest.id == request.id, AIRequest.status == RequestStatus.reserved)
            .values(error_message=error_message)
        )
        if claimed.rowcount == 0:
            return  # повторная доставка -- идемпотентный no-op
        try:
            await refund_request(session, request, reason=f"fal error: {error_message}")
            await record_daily_spend(request.user_id, -request.reserved_credits)
            await session.commit()
        finally:
            await redis_client.delete(lock_key)
    else:
        logger.warning(
            "fal webhook: unknown status %r for request_id=%s", status, fal_request_id
        )


async def refund_stale_reserved_requests(
    session: AsyncSession, *, older_than_minutes: int = RECONCILE_STALE_AFTER_MINUTES
) -> int:
    """Возврат кредитов за запросы, застрявшие в status=reserved дольше
    older_than_minutes -- признак того, что вебхук fal.ai так и не пришёл
    (сетевой сбой, потерянный callback и т.п.). Без этой развёртки
    зарезервированные кредиты остались бы списанными навсегда без возврата.

    Запускается периодически из app/worker.py (job reconcile_stale_media_reserves,
    подключён в фазе 4).

    Коммит один раз в конце (batch-джоба, не hot path): проще и достаточно --
    при падении на середине списка просто ничего не коммитится и следующий
    прогон повторит попытку для всех тех же строк (idempotent: refund_request
    требует status=reserved, что гарантируется select ниже перед изменениями).

    Гонка с "опоздавшим" вебхуком: между этим SELECT и обработкой строки
    настоящий (не потерянный) вебхук может успеть прийти в отдельной
    транзакции и settle-ить запрос. Поэтому, как и в handle_fal_webhook,
    перед refund_request берём атомарный claim -- UPDATE ... WHERE
    status=reserved. Если rowcount=0, значит вебхук успел раньше и уже
    закоммитил settle/refund; строку пропускаем, не трогая её in-memory
    (устаревший) объект.
    """
    threshold = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    stale_requests = (
        await session.execute(
            select(AIRequest).where(
                AIRequest.status == RequestStatus.reserved,
                AIRequest.category.in_((ModelCategory.image, ModelCategory.video)),
                AIRequest.created_at < threshold,
            )
        )
    ).scalars().all()

    refunded_count = 0
    for request in stale_requests:
        claimed = await session.execute(
            update(AIRequest)
            .where(
                AIRequest.id == request.id,
                AIRequest.status == RequestStatus.reserved,
                AIRequest.created_at < threshold,
            )
            .values(error_message="reconciliation: fal webhook never arrived")
            # synchronize_session=False: не нужно синхронизировать identity map
            # по этому UPDATE (мы не читаем error_message из `request` дальше,
            # только status, который эта строка не меняет) -- "evaluate"
            # пытался бы сравнить created_at в памяти с threshold и падал на
            # naive/aware datetime в тестовом sqlite; "fetch" был бы лишним
            # round-trip'ом на каждую строку в batch-джобе.
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount == 0:
            continue  # уже обработан (вебхук успел раньше) -- не наш запрос больше

        await refund_request(
            session, request, reason="reconciliation: fal webhook never arrived"
        )
        # decrement здесь (как и на webhook-ветках submit/ERROR/no-result-url выше)
        # может случиться минуты-часы спустя после исходного +estimated в
        # reserve_credits, а _daily_spend_key считается от текущего UTC-дня отдельно
        # в каждый момент -- если резерв пришёлся на конец дня D, а decrement уже
        # на день D+1, счётчик D+1 уйдёт в небольшой минус (чуть смягчает завтрашний
        # лимит), а счётчик D останется завышенным (не страшно, его больше никто не
        # читает). Это ограничено 25ч TTL (DAILY_SPEND_TTL_SECONDS) и осознанный
        # компромисс в пользу защиты от убытков, а не баг.
        await record_daily_spend(request.user_id, -request.reserved_credits)
        await redis_client.delete(f"ai_lock:{request.user_id}")
        refunded_count += 1

    await session.commit()
    return refunded_count
