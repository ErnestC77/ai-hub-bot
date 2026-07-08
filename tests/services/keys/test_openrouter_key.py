from app.config import Settings
from app.services.keys.api_key_manager import ApiKeyManager
from app.services.keys.enums import KeyPurpose, Provider


def test_openrouter_text_purpose_uses_api_key(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-123")
    settings = Settings()
    manager = ApiKeyManager(settings)

    assert manager.get_key(Provider.OPENROUTER, KeyPurpose.TEXT) == "sk-or-test-123"
