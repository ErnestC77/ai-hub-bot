from enum import StrEnum

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    dev = "dev"
    staging = "staging"
    prod = "prod"


class _ProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class OpenAISettings(_ProviderSettings):
    text_key: SecretStr | None = Field(default=None, alias="OPENAI_TEXT_KEY")
    image_key: SecretStr | None = Field(default=None, alias="OPENAI_IMAGE_KEY")
    audio_key: SecretStr | None = Field(default=None, alias="OPENAI_AUDIO_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="OPENAI_DEV_KEY")


class AnthropicSettings(_ProviderSettings):
    prod_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_PROD_KEY")
    premium_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_PREMIUM_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_DEV_KEY")


class GeminiSettings(_ProviderSettings):
    text_key: SecretStr | None = Field(default=None, alias="GEMINI_TEXT_KEY")
    image_key: SecretStr | None = Field(default=None, alias="GEMINI_IMAGE_KEY")
    video_key: SecretStr | None = Field(default=None, alias="GEMINI_VIDEO_KEY")
    audio_key: SecretStr | None = Field(default=None, alias="GEMINI_AUDIO_KEY")
    music_key: SecretStr | None = Field(default=None, alias="GEMINI_MUSIC_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="GEMINI_DEV_KEY")


class DeepSeekSettings(_ProviderSettings):
    prod_key: SecretStr | None = Field(default=None, alias="DEEPSEEK_PROD_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="DEEPSEEK_DEV_KEY")


class PerplexitySettings(_ProviderSettings):
    search_key: SecretStr | None = Field(default=None, alias="PERPLEXITY_SEARCH_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="PERPLEXITY_DEV_KEY")


class ElevenLabsSettings(_ProviderSettings):
    tts_key: SecretStr | None = Field(default=None, alias="ELEVENLABS_TTS_KEY")
    voice_agent_key: SecretStr | None = Field(default=None, alias="ELEVENLABS_VOICE_AGENT_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="ELEVENLABS_DEV_KEY")


class RunwaySettings(_ProviderSettings):
    fast_video_key: SecretStr | None = Field(default=None, alias="RUNWAY_FAST_VIDEO_KEY")
    premium_video_key: SecretStr | None = Field(default=None, alias="RUNWAY_PREMIUM_VIDEO_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="RUNWAY_DEV_KEY")


class StabilitySettings(_ProviderSettings):
    image_key: SecretStr | None = Field(default=None, alias="STABILITY_IMAGE_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="STABILITY_DEV_KEY")


class FalSettings(_ProviderSettings):
    image_key: SecretStr | None = Field(default=None, alias="FAL_IMAGE_KEY")
    video_key: SecretStr | None = Field(default=None, alias="FAL_VIDEO_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="FAL_DEV_KEY")


class ReplicateSettings(_ProviderSettings):
    prod_key: SecretStr | None = Field(default=None, alias="REPLICATE_PROD_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="REPLICATE_DEV_KEY")


class LumaSettings(_ProviderSettings):
    video_key: SecretStr | None = Field(default=None, alias="LUMA_VIDEO_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="LUMA_DEV_KEY")


class OpenRouterSettings(_ProviderSettings):
    api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")
    fallback_key: SecretStr | None = Field(default=None, alias="OPENROUTER_FALLBACK_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="OPENROUTER_DEV_KEY")


class PiApiSettings(_ProviderSettings):
    api_key: SecretStr | None = Field(default=None, alias="PIAPI_API_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="PIAPI_DEV_KEY")


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

    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    deepseek: DeepSeekSettings = Field(default_factory=DeepSeekSettings)
    perplexity: PerplexitySettings = Field(default_factory=PerplexitySettings)
    elevenlabs: ElevenLabsSettings = Field(default_factory=ElevenLabsSettings)
    runway: RunwaySettings = Field(default_factory=RunwaySettings)
    stability: StabilitySettings = Field(default_factory=StabilitySettings)
    fal: FalSettings = Field(default_factory=FalSettings)
    replicate: ReplicateSettings = Field(default_factory=ReplicateSettings)
    luma: LumaSettings = Field(default_factory=LumaSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    piapi: PiApiSettings = Field(default_factory=PiApiSettings)

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    payment_return_url: str = ""
    yookassa_webhook_url: str = ""
    frontend_url: str = ""
    piapi_webhook_secret: str = ""
    fal_webhook_secret: str = ""

    # This backend's own public URL -- used to build the PiAPI webhook callback address.
    # Render sets this via the service's own external hostname (see render.yaml).
    backend_public_url: str = ""

    admin_ids: str = ""

    debug: bool = False

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
        if not secret_set(self.openrouter.api_key):
            missing.append("OPENROUTER_API_KEY")
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
        if not self.yookassa_shop_id or not self.yookassa_secret_key:
            missing.append("YOOKASSA_SHOP_ID/SECRET_KEY")
        if missing:
            raise RuntimeError(
                "APP_ENV=prod требует заданными: " + ", ".join(missing)
            )


settings = Settings()
