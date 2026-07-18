from enum import StrEnum

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    dev = "dev"
    staging = "staging"
    prod = "prod"


class _ProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Приложение использует ТОЛЬКО fal: медиа (image/video) + текст через fal LLM
# router (fal.run/openrouter/router — те же модели OpenRouter, но проксируются
# с не-РФ серверов fal, поэтому доступны из РФ, в отличие от прямого OpenRouter,
# который Cloudflare режет по гео). Прежние провайдер-классы удалены как мёртвый
# код: новый провайдер = новый Settings-класс + запись в ApiKeyManager.
class FalSettings(_ProviderSettings):
    image_key: SecretStr | None = Field(default=None, alias="FAL_IMAGE_KEY")
    video_key: SecretStr | None = Field(default=None, alias="FAL_VIDEO_KEY")
    # Текст через fal LLM router. Отдельный ключ -- чтобы траты на текст считались
    # отдельно; если не задан, провайдер откатывается на image_key (тот же fal-аккаунт).
    text_key: SecretStr | None = Field(default=None, alias="FAL_TEXT_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="FAL_DEV_KEY")


class OpenRouterSettings(_ProviderSettings):
    api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")
    fallback_key: SecretStr | None = Field(default=None, alias="OPENROUTER_FALLBACK_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="OPENROUTER_DEV_KEY")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: AppEnv = AppEnv.dev

    bot_token: str

    bot_mode: str = "polling"  # "polling" | "webhook"
    webapp_url: str = "http://localhost:8000"
    webhook_secret: str = ""
    bot_username: str = ""

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    fal: FalSettings = Field(default_factory=FalSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    payment_return_url: str = ""
    frontend_url: str = ""
    fal_webhook_secret: str = ""

    # Публичный https-URL этого бэкенда -- из него собирается fal webhook-callback.
    backend_public_url: str = ""

    admin_ids: str = ""

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.split(",") if x.strip()]

    @field_validator("database_url")
    @classmethod
    def _normalize_asyncpg(cls, url: str) -> str:
        """Render отдаёт connectionString как postgresql:// -- driver по
        умолчанию psycopg2 (не установлен). Приложение целиком на asyncpg,
        поэтому нормализуем схему, чтобы прод-URL из Render работал как есть."""
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://"):]
        if url.startswith("postgres://"):  # старый алиас Heroku/некоторых панелей
            return "postgresql+asyncpg://" + url[len("postgres://"):]
        return url

    def require_prod_web_secrets(self) -> None:
        """Fail-fast для WEB-процесса на проде: без этих значений фичи молча
        ломаются (генерация падает, fal-webhook отвечает 403, CORS режет фронт).
        Вызывается из app.main.lifespan -- НЕ в валидаторе Settings, потому что
        тот же модуль импортит worker, которому FAL/OpenRouter не нужны и который
        иначе не стартовал бы. В dev/staging проверка пропускается."""
        if self.app_env is not AppEnv.prod:
            return

        def secret_set(s: SecretStr | None) -> bool:
            return bool(s and s.get_secret_value())

        missing: list[str] = []
        # Текст теперь через fal router: отдельный ключ не обязателен -- при его
        # отсутствии используется FAL_IMAGE_KEY (тот же fal-аккаунт), который
        # требуется ниже. OPENROUTER_API_KEY больше не нужен.
        if not secret_set(self.fal.image_key):
            missing.append("FAL_IMAGE_KEY")
        if not secret_set(self.fal.video_key):
            missing.append("FAL_VIDEO_KEY")
        if not self.fal_webhook_secret:
            missing.append("FAL_WEBHOOK_SECRET")
        if not self.backend_public_url:
            missing.append("BACKEND_PUBLIC_URL")
        elif not self.backend_public_url.startswith("https://"):
            missing.append("BACKEND_PUBLIC_URL (must be https://...)")
        if not self.frontend_url:
            missing.append("FRONTEND_URL")
        if self.bot_mode == "webhook" and not self.webhook_secret:
            missing.append("WEBHOOK_SECRET (bot_mode=webhook)")
        # YOOKASSA НЕ требуем: платежи возможны и через Telegram Stars, yookassa
        # опционален. Отсутствие ключей ломает только yookassa-платежи, не старт.
        if missing:
            raise RuntimeError(
                "APP_ENV=prod требует заданными: " + ", ".join(missing)
            )


settings = Settings()
