import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelCategory, ModelProvider
from app.db.models import AiModel
from app.services.keys.api_key_manager import ApiKeyManager, get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

logger = logging.getLogger(__name__)

# Провайдеров в каталоге ровно два (фаза 1). Поля key_purpose на AiModel нет
# (в отличие от старого ModelConfig) -- purpose выводится из категории модели.
_DB_PROVIDER_TO_KEY_PROVIDER = {
    ModelProvider.openrouter: Provider.OPENROUTER,
    ModelProvider.fal: Provider.FAL,
}

_CATEGORY_TO_PURPOSE = {
    ModelCategory.text: KeyPurpose.TEXT,
    ModelCategory.image: KeyPurpose.IMAGE,
    ModelCategory.video: KeyPurpose.VIDEO,
}


async def run_key_healthcheck(
    session: AsyncSession, key_manager: ApiKeyManager | None = None
) -> None:
    """Логирует статус ключей активных моделей при старте.

    Никогда не роняет приложение: отсутствующий ключ означает, что конкретная
    модель ответит пользователю безопасной ошибкой ("модель временно
    недоступна"), а не крэш всего сервиса -- так остальные модели и функции
    (пакеты, баланс, оплата) продолжают работать, даже если часть AI-ключей
    ещё не настроена.
    """
    key_manager = key_manager or get_key_manager()

    models = (
        await session.execute(select(AiModel).where(AiModel.is_active.is_(True)))
    ).scalars().all()

    for model in models:
        provider = _DB_PROVIDER_TO_KEY_PROVIDER.get(model.provider)
        if provider is None:
            logger.warning(
                "[WARNING] %s: no key-manager mapping for provider=%s", model.code, model.provider
            )
            continue

        purpose = _CATEGORY_TO_PURPOSE.get(model.category)
        if purpose is None:
            logger.warning(
                "[WARNING] %s: no key purpose for category=%s", model.code, model.category
            )
            continue

        if key_manager.has_key(provider, purpose):
            logger.info("[OK] %s/%s configured (model=%s)", provider.value, purpose.value, model.code)
        else:
            logger.warning(
                "[MISSING] %s is active but %s/%s key is not configured -- "
                "requests to it will fail with a safe error until the key is set",
                model.code, provider.value, purpose.value,
            )
