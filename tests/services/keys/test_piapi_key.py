from app.config import Settings
from app.services.keys.api_key_manager import ApiKeyManager
from app.services.keys.enums import KeyPurpose, Provider


def test_piapi_key_shared_across_purposes(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("PIAPI_API_KEY", "sk-test-123")
    settings = Settings()
    manager = ApiKeyManager(settings)

    assert manager.get_key(Provider.PIAPI, KeyPurpose.IMAGE) == "sk-test-123"
    assert manager.get_key(Provider.PIAPI, KeyPurpose.VIDEO) == "sk-test-123"
