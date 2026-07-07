from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
def mock_current_user():
    from app.db.models import User
    from app.api.deps import current_user

    async def _fake_user():
        return User(id=1, telegram_id=1, username="u")

    app.dependency_overrides[current_user] = _fake_user
    yield
    app.dependency_overrides.pop(current_user, None)


async def test_webhook_rejects_wrong_secret():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/piapi/webhook?secret=wrong", json={"data": {"task_id": "x"}})
    assert response.status_code == 403


async def test_webhook_accepts_correct_secret(monkeypatch):
    monkeypatch.setattr("app.config.settings.piapi_webhook_secret", "correct")
    with patch("app.webhooks.piapi.handle_piapi_webhook", new=AsyncMock()) as mock_handle:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/piapi/webhook?secret=correct", json={"data": {"task_id": "x", "status": "completed"}}
            )
        assert response.status_code == 200
        mock_handle.assert_awaited_once()
