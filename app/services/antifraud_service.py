"""Antifraud-гарды фазы 5: free-tier гейтинг, дневной лимит трат, rate-limit,
защита от дублей. Чистые guard-функции поверх Redis + таблицы settings: каждая
кидает своё исключение при нарушении и НИЧЕГО не пишет в Postgres. Пороги
редактируются админкой (settings), дефолты = сид фазы 5.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelCategory, ModelTier
from app.db.models import AiModel, User
from app.redis_client import redis_client
from app.services.settings_service import get_setting

DAILY_SPEND_TTL_SECONDS = 25 * 60 * 60  # 25ч -- страховка поверх UTC-дня (спека)


class DuplicateRequestError(Exception):
    """Повтор идентичного (model_code, prompt, option_codes) в окне duplicate_cooldown_seconds."""


class RateLimitExceededError(Exception):
    """Превышен per-minute лимит запросов (user или model)."""


class TierNotAllowedError(Exception):
    """video/ultra модели закрыты до первой покупки пакета."""


class FreeTierLimitExceededError(Exception):
    """Кумулятивный лимит бесплатных кредитов исчерпан."""


class DailySpendLimitExceededError(Exception):
    """Дневной лимит трат исчерпан."""


@dataclass(frozen=True)
class AntifraudSettings:
    """Снимок антифрод-порогов из таблицы settings. Дефолты = сид фазы 5
    (защита от пустой БД до первого сида, как у PricingSettings)."""

    daily_spend_limit_credits: int = 10_000
    rate_limit_per_user_per_minute: int = 10
    rate_limit_per_model_per_minute: int = 60
    duplicate_cooldown_seconds: int = 5
    free_tier_credit_cap: int = 100


async def load_antifraud_settings(session: AsyncSession) -> AntifraudSettings:
    defaults = AntifraudSettings()
    return AntifraudSettings(
        daily_spend_limit_credits=await get_setting(
            session, "daily_spend_limit_credits", cast=int,
            default=defaults.daily_spend_limit_credits,
        ),
        rate_limit_per_user_per_minute=await get_setting(
            session, "rate_limit_per_user_per_minute", cast=int,
            default=defaults.rate_limit_per_user_per_minute,
        ),
        rate_limit_per_model_per_minute=await get_setting(
            session, "rate_limit_per_model_per_minute", cast=int,
            default=defaults.rate_limit_per_model_per_minute,
        ),
        duplicate_cooldown_seconds=await get_setting(
            session, "duplicate_cooldown_seconds", cast=int,
            default=defaults.duplicate_cooldown_seconds,
        ),
        free_tier_credit_cap=await get_setting(
            session, "free_tier_credit_cap", cast=int,
            default=defaults.free_tier_credit_cap,
        ),
    )


def _minute_bucket() -> int:
    # Фиксированные 60-секундные окна (не скользящее окно): проще и достаточно
    # для защиты от убытков, не для точного throttling API (спека фазы 5).
    return int(time.time() // 60)


def _daily_spend_key(user_id: int) -> str:
    return f"daily_spend:{user_id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"


async def check_duplicate_request(
    user_id: int,
    model_code: str,
    prompt: str,
    *,
    option_codes: dict[str, str] | None = None,
    settings: AntifraudSettings,
) -> None:
    # option_codes входят в отпечаток: один промпт в 480p и 720p -- это два
    # разных запроса. Без них смена качества внутри cooldown ловила бы ложный
    # DuplicateRequestError. sort_keys канонизирует порядок ключей, чтобы
    # {quality,audio} и {audio,quality} совпадали. Текст опций не шлёт ->
    # option_codes=None -> отпечаток как раньше (обратная совместимость).
    fingerprint = model_code + prompt
    if option_codes:
        fingerprint += json.dumps(option_codes, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    key = f"dup:{user_id}:{digest}"
    # SET NX EX: проверка и захват cooldown-окна -- одна атомарная операция.
    acquired = await redis_client.set(key, "1", nx=True, ex=settings.duplicate_cooldown_seconds)
    if not acquired:
        raise DuplicateRequestError(
            f"duplicate request {key} within {settings.duplicate_cooldown_seconds}s"
        )


async def _check_one_rate_limit(key: str, limit: int, what: str) -> None:
    # Check и increment -- одна операция (INCR), отдельного "record" нет (спека).
    count = await redis_client.incr(key)
    if count == 1:
        # Первый запрос создал ключ -- ставим TTL, чтобы окно очистилось само.
        await redis_client.expire(key, 60)
    if count > limit:
        raise RateLimitExceededError(f"{what}: {count} > {limit}/min")


async def check_rate_limits(
    user_id: int, model_code: str, *, settings: AntifraudSettings
) -> None:
    bucket = _minute_bucket()
    await _check_one_rate_limit(
        f"rate_limit:user:{user_id}:{bucket}",
        settings.rate_limit_per_user_per_minute,
        f"user {user_id}",
    )
    await _check_one_rate_limit(
        f"rate_limit:model:{model_code}:{bucket}",
        settings.rate_limit_per_model_per_minute,
        f"model {model_code}",
    )


async def check_tier_allowed(user: User, model: AiModel) -> None:
    if user.total_credits_purchased > 0:
        return
    if model.category == ModelCategory.video or model.tier == ModelTier.ultra:
        raise TierNotAllowedError(
            f"model {model.code} requires a purchase "
            f"(category={model.category.value}, tier={model.tier.value})"
        )


async def check_free_tier_cap(
    user: User, estimated_credits: int, *, settings: AntifraudSettings
) -> None:
    # Раз пользователь ничего не покупал, весь его total_credits_spent -- это
    # трата free-кредитов (спека фазы 5): новых колонок не требуется.
    if user.total_credits_purchased > 0:
        return
    if user.total_credits_spent + estimated_credits > settings.free_tier_credit_cap:
        raise FreeTierLimitExceededError(
            f"free tier cap: {user.total_credits_spent} + {estimated_credits} "
            f"> {settings.free_tier_credit_cap}"
        )


async def check_daily_spend_limit(
    user_id: int, estimated_credits: int, *, settings: AntifraudSettings
) -> None:
    # Только чтение (GET): запись делает record_daily_spend ПОСЛЕ успешного
    # reserve_credits -- между проверкой и резервом стоит confirmation-gate,
    # который может прервать поток без записи (спека фазы 5).
    raw = await redis_client.get(_daily_spend_key(user_id))
    current = int(raw) if raw is not None else 0
    if current + estimated_credits > settings.daily_spend_limit_credits:
        raise DailySpendLimitExceededError(
            f"daily spend: {current} + {estimated_credits} "
            f"> {settings.daily_spend_limit_credits}"
        )


async def record_daily_spend(user_id: int, delta: int) -> None:
    """Инкремент/декремент дневного счётчика трат. Вызывается ПОСЛЕ успешного
    reserve_credits (delta=+estimated) и на ветках release/refund (delta<0)."""
    if delta == 0:
        return
    key = _daily_spend_key(user_id)
    if delta > 0:
        new_value = await redis_client.incrby(key, delta)
        if new_value == delta:  # ключ только что создан -- страховочный TTL
            await redis_client.expire(key, DAILY_SPEND_TTL_SECONDS)
    else:
        await redis_client.decrby(key, -delta)
