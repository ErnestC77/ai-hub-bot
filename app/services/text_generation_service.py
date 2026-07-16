"""Текстовый flow поверх движка кредитов (фаза 2, замена ai_router.py).

Порядок (спека фазы 2): резолв модели (+fallback) -> Redis-лок -> оценка ->
подтверждение дорогого запроса -> AIRequest + reserve (commit ДО внешнего
HTTP-вызова) -> OpenRouter -> settle / refund -> снятие лока (finally).
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelCategory, ModelTier, RequestStatus
from app.db.models import AIRequest, AiModel, User
from app.redis_client import redis_client
from app.services.ai.base import AIError, AIProvider
from app.services.ai.openrouter_service import OpenRouterProvider
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
from app.services.pricing import calculate_api_cost_usd, calculate_text_credits
from app.services.referral_service import maybe_grant_referral_bonus
from app.services.settings_service import load_pricing_settings

logger = logging.getLogger(__name__)

AI_LOCK_TTL_SECONDS = 120  # как в старом ai_router.py
ESTIMATE_INPUT_TOKENS = 2000   # дефолты оценки из ТЗ
ESTIMATE_OUTPUT_TOKENS = 1000
CONFIRM_THRESHOLD_CREDITS = 100

# Потолок max_output_tokens по tier (ТЗ: "Ограничить max_output_tokens по tier").
TIER_MAX: dict[ModelTier, int] = {
    ModelTier.economy: 1000,
    ModelTier.standard: 2000,
    ModelTier.premium: 4000,
    ModelTier.pro: 8000,
    ModelTier.ultra: 12000,
}

# Единственный текстовый провайдер фазы 2. Тесты подменяют monkeypatch'ем.
_provider: AIProvider = OpenRouterProvider()


class ModelNotFoundError(Exception):
    """model_code отсутствует в каталоге текстовых моделей."""


class ModelUnavailableError(Exception):
    """Модель выключена (is_active=False), fallback не задан."""


class RequestInProgressError(Exception):
    user_message = "Дождитесь ответа на предыдущий запрос."


class ConfirmationRequiredError(Exception):
    """Оценка дороже порога (или fallback дороже основной модели) без confirm=True."""

    def __init__(self, estimated_credits: int):
        self.estimated_credits = estimated_credits
        super().__init__(f"confirmation required: estimated {estimated_credits} credits")


@dataclass
class TextGenerationResult:
    answer: str
    charged_credits: int
    balance_after: int


async def _get_text_model(session: AsyncSession, code: str) -> AiModel | None:
    return (
        await session.execute(
            select(AiModel).where(AiModel.code == code, AiModel.category == ModelCategory.text)
        )
    ).scalar_one_or_none()


async def _resolve_model(session: AsyncSession, model_code: str) -> tuple[AiModel, AiModel]:
    """Возвращает (эффективная модель, запрошенная модель).

    Активная модель -> она сама. Неактивная с fallback_model_code -> активная
    fallback-модель. Иначе ModelNotFoundError / ModelUnavailableError / AIError
    (fallback тоже недоступен -- по спеке).
    """
    requested = await _get_text_model(session, model_code)
    if requested is None:
        raise ModelNotFoundError(model_code)
    if requested.is_active:
        return requested, requested
    if not requested.fallback_model_code:
        raise ModelUnavailableError(model_code)
    fallback = await _get_text_model(session, requested.fallback_model_code)
    if fallback is None or not fallback.is_active:
        raise AIError(f"model {model_code} and its fallback {requested.fallback_model_code} are unavailable")
    logger.info("model %s is inactive, falling back to %s", model_code, fallback.code)
    return fallback, requested


async def generate_text(
    session: AsyncSession, user: User, model_code: str, prompt: str, *, confirm: bool = False
) -> TextGenerationResult:
    model, requested = await _resolve_model(session, model_code)

    # Antifraud pre-checks (фаза 5) -- быстрый и дешёвый отказ ДО взятия лока.
    af_settings = await load_antifraud_settings(session)
    if not confirm:
        # confirm=True -- осознанный повтор после 409 ConfirmationRequired:
        # он приходит внутри cooldown-окна и не должен блокироваться дедупом.
        await check_duplicate_request(user.id, model_code, prompt, settings=af_settings)
    await check_rate_limits(user.id, model.code, settings=af_settings)
    await check_tier_allowed(user, model)

    lock_key = f"ai_lock:{user.id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=AI_LOCK_TTL_SECONDS)
    if not acquired:
        raise RequestInProgressError()

    try:
        pricing = await load_pricing_settings(session)
        estimated = calculate_text_credits(
            model, ESTIMATE_INPUT_TOKENS, ESTIMATE_OUTPUT_TOKENS, settings=pricing
        )

        # Antifraud (фаза 5): free-tier cap и дневной лимит -- после оценки,
        # ДО confirmation-gate (запись в daily-счётчик будет после reserve).
        await check_free_tier_cap(user, estimated, settings=af_settings)
        await check_daily_spend_limit(user.id, estimated, settings=af_settings)

        fallback_used = model is not requested
        needs_confirmation = estimated > CONFIRM_THRESHOLD_CREDITS or (
            fallback_used and model.recommended_credits > requested.recommended_credits
        )
        if needs_confirmation and not confirm:
            # Ничего не создано и не зарезервировано; лок снимется в finally.
            raise ConfirmationRequiredError(estimated)

        request = AIRequest(
            user_id=user.id,
            provider="openrouter",
            model_code=model.code,
            category=ModelCategory.text,
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
                provider="openrouter",
                model_code=model.code,
            )
        except InsufficientBalanceError:
            await session.rollback()  # убрать pending-AIRequest вместе с несостоявшимся резервом
            raise
        # reserve_credits не трогает статус AIRequest -- это ответственность вызывающего.
        request.status = RequestStatus.reserved
        await session.commit()  # резерв фиксируется ДО долгого внешнего вызова
        await record_daily_spend(user.id, estimated)

        try:
            result = await _provider.generate(model, prompt, TIER_MAX[model.tier])
            request.input_tokens = result.input_tokens
            request.output_tokens = result.output_tokens
            actual = calculate_text_credits(
                model, result.input_tokens, result.output_tokens, settings=pricing
            )
            request.provider_cost_usd = calculate_api_cost_usd(
                model, result.input_tokens, result.output_tokens
            )
            await settle_request(session, request, actual)
        except Exception as exc:
            request.error_message = str(exc)
            await refund_request(
                session, request, reason=f"provider error: {exc}", final_status=RequestStatus.failed
            )
            await session.commit()
            await record_daily_spend(user.id, -estimated)
            raise

        if request.charged_credits != estimated:
            # settle скорректировал списание (release или доплата) --
            # выравниваем дневной счётчик на разницу.
            await record_daily_spend(user.id, request.charged_credits - estimated)

        # Реферальный бонус -- после состоявшегося settle, ВНЕ try: его падение
        # не должно откатывать уже списанный запрос. Та же транзакция, до commit.
        await maybe_grant_referral_bonus(session, request.user_id)

        charged = request.charged_credits
        balance_after = user.credits_balance
        await session.commit()

        return TextGenerationResult(
            answer=result.answer, charged_credits=charged, balance_after=balance_after
        )
    finally:
        await redis_client.delete(lock_key)
