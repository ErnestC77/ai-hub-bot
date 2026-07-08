import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks

from app.db.enums import ModelProvider, RequestStatus
from app.db.models import AIRequest, ModelConfig, User
from app.redis_client import redis_client
from app.services.access_service import RequestInProgressError, check_access
from app.services.ai.base import AIError
from app.services.ai.image_service import ImageProvider
from app.services.ai.piapi_client import PiAPIClient
from app.services.credit_service import spend_credits
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider
from app.services.limit_service import spend
from app.config import settings

logger = logging.getLogger(__name__)

# Long enough to survive slow PiAPI video generation (Sora2/Veo can take several
# minutes) -- this is a safety-net TTL, not the expected lock lifetime; the lock is
# normally released explicitly once the generation truly finishes (see
# handle_piapi_webhook / _run_sync_provider_in_background), not by TTL expiry.
AI_LOCK_TTL_SECONDS = 900


class ModelNotFoundError(Exception):
    pass


_IMAGE_ASPECT_TO_BUCKET: dict[str, str] = {
    "auto": "square", "1:1": "square", "4:3": "square", "4:5": "square", "5:4": "square",
    "3:2": "landscape", "16:9": "landscape", "21:9": "landscape",
    "2:3": "portrait", "3:4": "portrait", "9:16": "portrait",
}
_IMAGE_BUCKET_TO_SIZE = {"square": "1024x1024", "portrait": "1024x1792", "landscape": "1792x1024"}
_RESOLUTION_TO_QUALITY = {"1k": "standard", "2k": "hd", "4k": "hd"}
_COST_MULTIPLIER: dict[tuple[str, str], int] = {
    ("square", "1k"): 1, ("square", "2k"): 2, ("square", "4k"): 3,
    ("landscape", "1k"): 2, ("landscape", "2k"): 3, ("landscape", "4k"): 4,
    ("portrait", "1k"): 2, ("portrait", "2k"): 3, ("portrait", "4k"): 4,
}


def compute_dalle3_credit_cost(base_cost: int, aspect: str, resolution: str) -> int:
    bucket = _IMAGE_ASPECT_TO_BUCKET.get(aspect, "square")
    multiplier = _COST_MULTIPLIER[(bucket, resolution)]
    return max(1, round(base_cost * multiplier))


def _webhook_url() -> str:
    return f"{settings.backend_public_url}/api/piapi/webhook?secret={settings.piapi_webhook_secret}"


async def _get_model(session: AsyncSession, model_code: str) -> ModelConfig:
    model = (
        await session.execute(select(ModelConfig).where(ModelConfig.model_code == model_code))
    ).scalar_one_or_none()
    if model is None:
        raise ModelNotFoundError(model_code)
    return model


async def _charge_for_completed_request(
    session: AsyncSession, user: User, model: ModelConfig, request: AIRequest, credit_cost: int
) -> None:
    """Charges for a completed generation, matching the old ai_router.py behavior:
    prefer tariff quota (limit_service.spend) if the user still has quota for this
    category, otherwise spend credits. The actual charge happens at completion time --
    possibly minutes later than the original access check for PiAPI/video -- so we
    re-derive a fresh AccessContext here instead of persisting the original one (which
    would need a new DB column). If the re-check itself raises (extremely unlikely --
    the user's tariff/limits state could only have shifted in the intervening minutes),
    fall back to an unconditional credit spend: the generation was already produced and
    paid for at the provider, so a completion-time re-check failure must never block
    delivering the already-generated result.
    """
    ctx = None
    try:
        ctx = await check_access(session, user, model, request.prompt)
    except Exception:
        logger.warning(
            "check_access re-check failed at completion time for user_id=%s model=%s; "
            "falling back to unconditional credit spend",
            user.id, model.model_code,
        )

    if ctx is not None and not ctx.use_credits:
        await spend(session, ctx.usage_limit, model.category)
    else:
        ok = await spend_credits(session, user, credit_cost, reason=f"AI request: {model.model_code}")
        if not ok:
            logger.warning(
                "spend_credits returned False for user_id=%s model=%s amount=%s",
                user.id, model.model_code, credit_cost,
            )


async def _run_sync_provider_in_background(
    session_factory, request_id: int, model: ModelConfig, prompt: str, extra: dict | None,
    credit_cost: int, user_id: int,
) -> None:
    """Runs the existing synchronous ImageProvider (dall-e-3) after the endpoint has
    already returned, then updates the same AIRequest row the async PiAPI path uses.
    Releases the per-user in-flight lock acquired in start_generation once the
    generation is truly finished, whether it succeeded or failed."""
    lock_key = f"ai_lock:{user_id}"
    try:
        async with session_factory() as session:
            request = await session.get(AIRequest, request_id)
            try:
                result = await ImageProvider().generate(model, prompt, max_output_tokens=0, extra=extra)
            except AIError as exc:
                request.status = RequestStatus.error
                request.error_message = str(exc)
                await session.commit()
                return

            request.status = RequestStatus.success
            request.answer = result.answer
            await session.commit()

            user = await session.get(User, user_id)
            await _charge_for_completed_request(session, user, model, request, credit_cost)
    finally:
        await redis_client.delete(lock_key)


async def start_generation(
    session: AsyncSession,
    user: User,
    model_code: str,
    prompt: str,
    extra: dict | None,
    credit_cost_override: int | None,
    background_tasks: BackgroundTasks,
) -> AIRequest:
    model = await _get_model(session, model_code)

    if model.model_code == "dall-e-3" and extra and "aspect" in extra and "resolution" in extra:
        aspect, resolution = extra["aspect"], extra["resolution"]
        credit_cost_override = compute_dalle3_credit_cost(model.credit_cost, aspect, resolution)
        bucket = _IMAGE_ASPECT_TO_BUCKET.get(aspect, "square")
        extra = {
            "size": _IMAGE_BUCKET_TO_SIZE[bucket],
            "quality": _RESOLUTION_TO_QUALITY[resolution],
            "resolution": resolution,
        }

    # credit_cost_override is only honored on the synchronous (non-PiAPI) path: the
    # PiAPI async path charges model.credit_cost later in handle_piapi_webhook, which
    # has no way to see this override, so applying it here would let a caller be
    # access-checked against one amount and charged a different one at webhook time.
    is_piapi = model.provider == ModelProvider.piapi
    effective_override = None if is_piapi else credit_cost_override
    await check_access(session, user, model, prompt, credit_cost=effective_override)
    credit_cost = effective_override if effective_override is not None else model.credit_cost

    # Per-user in-flight lock: without it a user could fire N concurrent generations of
    # the same expensive model, all pass check_access (which only reads balance, it
    # doesn't reserve), all get billed to us by the provider -- but since credits are
    # spent later at completion time, only the first completion would actually deduct
    # anything. PiAPI generation is async (result arrives via webhook, possibly minutes
    # later for video) so this lock is NOT released at the end of this function -- it is
    # only released once the generation is truly finished, in handle_piapi_webhook or
    # _run_sync_provider_in_background.
    lock_key = f"ai_lock:{user.id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=AI_LOCK_TTL_SECONDS)
    if not acquired:
        raise RequestInProgressError()

    request = AIRequest(
        user_id=user.id,
        model_code=model.model_code,
        model_category=model.category,
        prompt=prompt,
        status=RequestStatus.processing,
    )
    session.add(request)
    await session.commit()

    if is_piapi:
        try:
            purpose = KeyPurpose(model.key_purpose)
            api_key = get_key_manager().get_key(Provider.PIAPI, purpose)
            client = PiAPIClient(api_key=api_key)
            input_ = {"prompt": prompt, **(model.piapi_extra_input or {})}
            task_id = await client.create_task(
                model=model.piapi_model,
                task_type=model.piapi_task_type,
                input_=input_,
                webhook_url=_webhook_url(),
            )
        except Exception as exc:
            request.status = RequestStatus.error
            request.error_message = str(exc)
            await session.commit()
            await redis_client.delete(lock_key)
            raise

        request.provider_task_id = task_id
        await session.commit()
    else:
        from app.db.session import get_session
        background_tasks.add_task(
            _run_sync_provider_in_background, get_session, request.id, model, prompt, extra, credit_cost, user.id,
        )

    return request


async def get_generation(session: AsyncSession, user: User, request_id: int) -> AIRequest | None:
    request = await session.get(AIRequest, request_id)
    if request is None or request.user_id != user.id:
        return None
    return request


async def handle_piapi_webhook(session: AsyncSession, payload: dict) -> None:
    from app.services.ai.piapi_client import extract_result_url

    data = payload.get("data") or {}
    task_id = data.get("task_id")
    if not task_id:
        return

    request = (
        await session.execute(select(AIRequest).where(AIRequest.provider_task_id == task_id))
    ).scalar_one_or_none()
    if request is None:
        return  # unknown task

    status = data.get("status")
    if status == "completed":
        # Atomic claim: the WHERE clause ensures only one concurrent webhook delivery
        # (PiAPI retry, or multi-worker deployment) can transition processing -> success.
        # If rowcount is 0, another delivery already claimed this request -- bail out
        # before spending credits again.
        result = await session.execute(
            update(AIRequest)
            .where(AIRequest.id == request.id, AIRequest.status == RequestStatus.processing)
            .values(status=RequestStatus.success, answer=extract_result_url(data))
        )
        if result.rowcount == 0:
            return  # already handled (webhook retry) -- idempotent no-op
        await session.commit()

        # Lock is released only here (or in the failed branch below), never in
        # start_generation -- the rowcount==0 early-return above ensures a duplicate/
        # retried webhook delivery never tries to release a lock it doesn't own.
        lock_key = f"ai_lock:{request.user_id}"
        try:
            model = await _get_model(session, request.model_code)
            user = await session.get(User, request.user_id)
            await _charge_for_completed_request(session, user, model, request, model.credit_cost)
        finally:
            await redis_client.delete(lock_key)
    elif status == "failed":
        error = data.get("error") or {}
        result = await session.execute(
            update(AIRequest)
            .where(AIRequest.id == request.id, AIRequest.status == RequestStatus.processing)
            .values(status=RequestStatus.error, error_message=error.get("message") or "generation failed")
        )
        if result.rowcount == 0:
            return  # already handled (webhook retry) -- idempotent no-op
        await session.commit()
        await redis_client.delete(f"ai_lock:{request.user_id}")
