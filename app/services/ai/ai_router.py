from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelCategory, RequestStatus
from app.db.models import AIRequest, ModelConfig, User
from app.redis_client import redis_client
from app.services.access_service import RequestInProgressError, check_access
from app.services.ai.base import AIError, AIResult
from app.services.ai.registry import IMAGE_PROVIDERS, TEXT_PROVIDERS
from app.services.cost_service import fill_request_cost
from app.services.limit_service import spend

AI_LOCK_TTL_SECONDS = 120


class ModelNotFoundError(Exception):
    pass


async def _get_model(session: AsyncSession, model_code: str) -> ModelConfig:
    model = (
        await session.execute(select(ModelConfig).where(ModelConfig.model_code == model_code))
    ).scalar_one_or_none()
    if model is None:
        raise ModelNotFoundError(model_code)
    return model


class AIRouter:
    async def generate(self, session: AsyncSession, user: User, model_code: str, prompt: str) -> AIResult:
        model = await _get_model(session, model_code)
        ctx = await check_access(session, user, model, prompt)

        lock_key = f"ai_lock:{user.id}"
        acquired = await redis_client.set(lock_key, "1", nx=True, ex=AI_LOCK_TTL_SECONDS)
        if not acquired:
            raise RequestInProgressError()

        try:
            request = AIRequest(
                user_id=user.id,
                model_code=model.model_code,
                model_category=model.category,
                prompt=prompt,
                status=RequestStatus.processing,
            )
            session.add(request)
            await session.commit()

            try:
                registry = IMAGE_PROVIDERS if model.category == ModelCategory.image else TEXT_PROVIDERS
                factory = registry.get(model.provider)
                if factory is None:
                    raise AIError("provider not implemented")
                result = await factory().generate(model, prompt, ctx.max_output_tokens)
            except AIError as exc:
                request.status = RequestStatus.error
                request.error_message = str(exc)
                await session.commit()
                raise

            await fill_request_cost(session, request, model, result)
            await spend(session, ctx.usage_limit, model.category)

            request.status = RequestStatus.success
            request.answer = result.answer
            await session.commit()

            return result
        finally:
            await redis_client.delete(lock_key)
