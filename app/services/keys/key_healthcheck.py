import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelProvider
from app.db.models import ModelConfig
from app.services.keys.api_key_manager import ApiKeyManager, get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

logger = logging.getLogger(__name__)

_DB_PROVIDER_TO_KEY_PROVIDER = {
    ModelProvider.openai: Provider.OPENAI,
    ModelProvider.anthropic: Provider.ANTHROPIC,
    ModelProvider.google: Provider.GEMINI,
    ModelProvider.deepseek: Provider.DEEPSEEK,
}


async def run_key_healthcheck(session: AsyncSession, key_manager: ApiKeyManager | None = None) -> None:
    """Логирует статус ключей активных моделей при старте.

    Никогда не роняет приложение: отсутствующий ключ означает, что конкретная
    модель ответит пользователю безопасной ошибкой ("модель временно
    недоступна"), а не крэш всего сервиса -- так остальные модели и функции
    (тарифы, баланс, оплата) продолжают работать, даже если часть AI-ключей
    ещё не настроена.
    """
    key_manager = key_manager or get_key_manager()

    models = (
        await session.execute(select(ModelConfig).where(ModelConfig.is_active.is_(True)))
    ).scalars().all()

    for model in models:
        provider = _DB_PROVIDER_TO_KEY_PROVIDER.get(model.provider)
        if provider is None:
            logger.warning("[WARNING] %s: no key-manager mapping for provider=%s", model.model_code, model.provider)
            continue

        try:
            purpose = KeyPurpose(model.key_purpose)
        except ValueError:
            logger.warning("[WARNING] %s: unknown key_purpose=%r", model.model_code, model.key_purpose)
            continue

        if key_manager.has_key(provider, purpose):
            logger.info("[OK] %s/%s configured (model=%s)", provider.value, purpose.value, model.model_code)
        else:
            logger.warning(
                "[MISSING] %s is active but %s/%s key is not configured -- "
                "requests to it will fail with a safe error until the key is set",
                model.model_code, provider.value, purpose.value,
            )
