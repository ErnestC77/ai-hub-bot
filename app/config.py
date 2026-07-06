from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str

    bot_mode: str = "polling"  # "polling" | "webhook"
    webapp_url: str = "http://localhost:8000"
    webhook_secret: str = ""
    bot_username: str = ""

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    deepseek_api_key: str = ""

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    payment_return_url: str = ""
    yookassa_webhook_url: str = ""

    admin_ids: str = ""

    debug: bool = False

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.split(",") if x.strip()]


settings = Settings()
