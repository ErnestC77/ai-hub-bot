import pytest
from fastapi import HTTPException

from app.api.deps import current_admin
from app.config import settings
from app.db.models import User


async def test_current_admin_allows_id_in_env(monkeypatch):
    monkeypatch.setattr(settings, "admin_ids", "42,99")
    admin = User(telegram_id=42, username="a")
    assert await current_admin(admin) is admin


async def test_current_admin_revokes_when_removed_from_env(monkeypatch):
    # is_admin=True в БД (наследие с момента создания), но ID уже НЕ в ADMIN_IDS.
    # Раньше проверялся кэш-флаг -> доступ оставался; теперь сверяем env -> 403.
    monkeypatch.setattr(settings, "admin_ids", "42")
    stale_admin = User(telegram_id=7, username="x", is_admin=True)
    with pytest.raises(HTTPException) as exc:
        await current_admin(stale_admin)
    assert exc.value.status_code == 403
