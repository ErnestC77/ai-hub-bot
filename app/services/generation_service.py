from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks

from app.db.enums import ModelProvider, RequestStatus
from app.db.models import AIRequest, ModelConfig, User
from app.services.access_service import check_access
from app.services.ai.base import AIError
from app.services.ai.image_service import ImageProvider
from app.services.ai.piapi_client import PiAPIClient
from app.services.credit_service import spend_credits
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider
from app.config import settings


class ModelNotFoundError(Exception):
    pass


def _webhook_url() -> str:
    # `backend_public_url` is added to Settings in Task 6 alongside route registration.
    # getattr(..., "") lets this module import and run cleanly before that field exists --
    # PiAPI just gets an incomplete webhook URL until Task 6 lands (never hit in this
    # task's tests, since none assert on the URL passed to the mocked PiAPIClient).
    base_url = getattr(settings, "backend_public_url", "")
    return f"{base_url}/api/piapi/webhook?secret={settings.piapi_webhook_secret}"


async def _get_model(session: AsyncSession, model_code: str) -> ModelConfig:
    model = (
        await session.execute(select(ModelConfig).where(ModelConfig.model_code == model_code))
    ).scalar_one_or_none()
    if model is None:
        raise ModelNotFoundError(model_code)
    return model


async def _run_sync_provider_in_background(
    session_factory, request_id: int, model: ModelConfig, prompt: str, extra: dict | None,
    credit_cost: int, user_id: int,
) -> None:
    """Runs the existing synchronous ImageProvider (dall-e-3) after the endpoint has
    already returned, then updates the same AIRequest row the async PiAPI path uses."""
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
        await spend_credits(session, user, credit_cost, reason=f"AI request: {model.model_code}")


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
    # credit_cost_override is only honored on the synchronous (non-PiAPI) path: the
    # PiAPI async path charges model.credit_cost later in handle_piapi_webhook, which
    # has no way to see this override, so applying it here would let a caller be
    # access-checked against one amount and charged a different one at webhook time.
    is_piapi = model.provider == ModelProvider.piapi
    effective_override = None if is_piapi else credit_cost_override
    await check_access(session, user, model, prompt, credit_cost=effective_override)
    credit_cost = effective_override if effective_override is not None else model.credit_cost

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

        model = await _get_model(session, request.model_code)
        user = await session.get(User, request.user_id)
        await spend_credits(session, user, model.credit_cost, reason=f"AI request: {model.model_code}")
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
