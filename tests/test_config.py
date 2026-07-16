import pytest

from app.config import AppEnv, Settings


def test_fal_webhook_secret_read_from_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("FAL_WEBHOOK_SECRET", "whsec-123")

    settings = Settings()

    assert settings.fal_webhook_secret == "whsec-123"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),  # уже ок
    ],
)
def test_database_url_normalized_to_asyncpg(raw, expected):
    s = Settings(bot_token="x", database_url=raw)
    assert s.database_url == expected


def test_dev_env_does_not_require_prod_secrets():
    # dev: проверка -- no-op (не мешает разработке)
    s = Settings(bot_token="x", database_url="postgresql+asyncpg://u@h/db", _env_file=None)
    assert s.app_env is AppEnv.dev
    s.require_prod_web_secrets()  # не бросает


def test_prod_web_fails_fast_on_missing_secrets():
    # _env_file=None: изолируемся от локального .env, где эти значения заданы.
    # Конструирование НЕ бросает (проверка -- отдельный метод для web-startup).
    s = Settings(bot_token="x", database_url="postgresql+asyncpg://u@h/db",
                 app_env=AppEnv.prod, _env_file=None)
    with pytest.raises(RuntimeError) as exc:
        s.require_prod_web_secrets()
    msg = str(exc.value)
    for key in ("OPENROUTER_API_KEY", "FAL_IMAGE_KEY", "FAL_VIDEO_KEY",
                "FAL_WEBHOOK_SECRET", "BACKEND_PUBLIC_URL", "FRONTEND_URL"):
        assert key in msg


def test_prod_web_requires_https_backend_url(monkeypatch):
    for k, v in {
        "OPENROUTER_API_KEY": "k", "FAL_IMAGE_KEY": "k", "FAL_VIDEO_KEY": "k",
        "FAL_WEBHOOK_SECRET": "s", "FRONTEND_URL": "https://front",
        "YOOKASSA_SHOP_ID": "1", "YOOKASSA_SECRET_KEY": "k",
        "BACKEND_PUBLIC_URL": "ai-hub-bot.onrender.com",  # без https://
    }.items():
        monkeypatch.setenv(k, v)
    s = Settings(bot_token="x", database_url="postgresql+asyncpg://u@h/db",
                 app_env=AppEnv.prod, _env_file=None)
    with pytest.raises(RuntimeError) as exc:
        s.require_prod_web_secrets()
    assert "BACKEND_PUBLIC_URL" in str(exc.value)


def test_prod_web_passes_when_all_secrets_present(monkeypatch):
    for k, v in {
        "OPENROUTER_API_KEY": "k", "FAL_IMAGE_KEY": "k", "FAL_VIDEO_KEY": "k",
        "FAL_WEBHOOK_SECRET": "s", "BACKEND_PUBLIC_URL": "https://back",
        "FRONTEND_URL": "https://front", "YOOKASSA_SHOP_ID": "1", "YOOKASSA_SECRET_KEY": "k",
    }.items():
        monkeypatch.setenv(k, v)
    s = Settings(bot_token="x", database_url="postgresql+asyncpg://u@h/db",
                 app_env=AppEnv.prod, _env_file=None)
    s.require_prod_web_secrets()  # не бросает
