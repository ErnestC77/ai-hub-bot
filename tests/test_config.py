from app.config import Settings


def test_fal_webhook_secret_read_from_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("FAL_WEBHOOK_SECRET", "whsec-123")

    settings = Settings()

    assert settings.fal_webhook_secret == "whsec-123"
