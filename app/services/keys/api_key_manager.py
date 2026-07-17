import logging

from app.config import AppEnv, Settings
from app.services.keys.enums import KeyPurpose, Provider
from app.services.keys.exceptions import (
    ApiKeyNotConfiguredError,
    ApiKeyPurposeNotSupportedError,
    DevKeyUsedInProductionError,
)

logger = logging.getLogger(__name__)

# provider -> {purpose: имя поля на app.config.<Provider>Settings}.
# Реально используются только fal (медиа) + OpenRouter (текст). Прежние ~11
# провайдеров удалены как мёртвый код; новый провайдер добавляется сюда + свой
# Settings-класс в app.config по мере реального использования.
_PURPOSE_ATTR: dict[Provider, dict[KeyPurpose, str]] = {
    Provider.FAL: {
        KeyPurpose.IMAGE: "image_key",
        KeyPurpose.VIDEO: "video_key",
    },
    Provider.OPENROUTER: {
        KeyPurpose.TEXT: "api_key",
        KeyPurpose.FALLBACK: "fallback_key",
    },
}

_DEV_KEY_ATTR = "dev_key"


class ApiKeyManager:
    """Единая точка получения API-ключей. AI-сервисы не читают .env напрямую."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def get_key(self, provider: Provider, purpose: KeyPurpose) -> str:
        provider_settings = getattr(self._settings, provider.value, None)
        purpose_map = _PURPOSE_ATTR.get(provider)
        if provider_settings is None or purpose_map is None:
            raise ApiKeyPurposeNotSupportedError(f"unknown provider {provider!r}")

        attr = _DEV_KEY_ATTR if purpose == KeyPurpose.DEV else purpose_map.get(purpose)
        if attr is None:
            raise ApiKeyPurposeNotSupportedError(
                f"{provider} has no key configured for purpose={purpose}"
            )

        secret = getattr(provider_settings, attr, None)
        if secret is not None:
            return secret.get_secret_value()

        dev_secret = getattr(provider_settings, _DEV_KEY_ATTR, None)
        if dev_secret is None:
            raise ApiKeyNotConfiguredError(f"no API key configured for {provider}/{purpose}")

        if self._settings.app_env == AppEnv.prod:
            raise DevKeyUsedInProductionError(
                f"{provider}/{purpose}: only a DEV key is configured; refusing to use it with APP_ENV=prod"
            )

        logger.warning(
            "%s/%s: no key for this purpose, falling back to DEV key (APP_ENV=%s)",
            provider, purpose, self._settings.app_env,
        )
        return dev_secret.get_secret_value()

    def has_key(self, provider: Provider, purpose: KeyPurpose) -> bool:
        try:
            self.get_key(provider, purpose)
            return True
        except (ApiKeyNotConfiguredError, ApiKeyPurposeNotSupportedError, DevKeyUsedInProductionError):
            return False


_manager: ApiKeyManager | None = None


def get_key_manager() -> ApiKeyManager:
    global _manager
    if _manager is None:
        from app.config import settings

        _manager = ApiKeyManager(settings)
    return _manager
