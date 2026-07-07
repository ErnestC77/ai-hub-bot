from enum import StrEnum

from pydantic import Field, SecretStr
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

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    payment_return_url: str = ""
    yookassa_webhook_url: str = ""
    frontend_url: str = ""

    admin_ids: str = ""

    debug: bool = False

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.split(",") if x.strip()]


settings = Settings()
