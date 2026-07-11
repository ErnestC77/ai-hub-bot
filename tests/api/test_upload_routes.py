import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
# postgresql+asyncpg:// (не голый postgresql://): app.api.deps -> app.db.session
# строит create_async_engine при импорте модуля -- см. комментарий в
# tests/api/test_chat_routes.py.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import current_user
from app.api.routes import upload
from app.config import settings
from app.db.models import User

# Минимальное приложение из тестируемого роутера (конвенция test_chat_routes.py).
app = FastAPI()
app.include_router(upload.router, prefix="/api")

_test_user = User(
    id=1, telegram_id=1, username="u", first_name="U", is_admin=False,
    default_model_code=None, credits_balance=100,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_user():
    return _test_user


@pytest.fixture
async def client(tmp_path, monkeypatch):
    # Файлы пишем во временную директорию pytest, а не в рабочий uploads/.
    # get_db переопределять не нужно: current_user переопределён целиком,
    # его под-зависимости FastAPI не резолвит.
    monkeypatch.setattr(upload, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "backend_public_url", "https://backend.example.com")
    app.dependency_overrides[current_user] = _fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_upload_image_saves_file_and_returns_public_url(client, tmp_path):
    data = b"\xff\xd8\xff fake-jpeg-bytes"

    response = await client.post(
        "/api/upload/image", files={"file": ("cat.jpg", data, "image/jpeg")},
    )

    assert response.status_code == 200
    url = response.json()["url"]
    assert url.startswith("https://backend.example.com/uploads/")
    filename = url.rsplit("/", 1)[1]
    assert filename.endswith(".jpg")
    # Файл реально лежит на диске с тем же содержимым (его отдаст StaticFiles).
    assert (tmp_path / filename).read_bytes() == data


async def test_upload_image_maps_content_type_to_extension(client):
    for content_type, ext in (("image/png", "png"), ("image/webp", "webp")):
        response = await client.post(
            "/api/upload/image", files={"file": ("x", b"data", content_type)},
        )
        assert response.status_code == 200
        assert response.json()["url"].endswith("." + ext)


async def test_upload_image_generates_unique_filenames(client):
    r1 = await client.post("/api/upload/image", files={"file": ("a.png", b"one", "image/png")})
    r2 = await client.post("/api/upload/image", files={"file": ("a.png", b"two", "image/png")})
    assert r1.json()["url"] != r2.json()["url"]  # uuid, не имя из запроса


async def test_upload_image_rejects_oversized_file_with_413(client):
    big = b"x" * (30 * 1024 * 1024 + 1)  # ровно на байт больше лимита PhotoUploadBox
    response = await client.post(
        "/api/upload/image", files={"file": ("big.png", big, "image/png")},
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "Файл больше 30 МБ"


async def test_upload_image_rejects_oversized_file_before_reading_body(client, monkeypatch):
    # Пин финального ревью: раньше лимит проверялся ПОСЛЕ await file.read(),
    # т.е. весь body уже материализовался в память как bytes -- при
    # клиент-контролируемом Content-Type это давало DoS на многогигабайтных
    # телах. Теперь file.size (заполняется Starlette из multipart-заголовков
    # ДО вызова route-хендлера) проверяется первым, и 413 должен вернуться,
    # даже не вызвав file.read(). Патчим read() так, чтобы он падал --
    # если бы старый путь (read-then-check) всё ещё существовал, тест упал
    # бы с AssertionError вместо 413.
    #
    # Патчим именно starlette.datastructures.UploadFile, а не fastapi.UploadFile:
    # fastapi.UploadFile -- это ре-экспорт для type hints, но объект, который
    # ASGI/Starlette реально передаёт в хендлер как file, -- это экземпляр
    # starlette-класса напрямую. Патч fastapi.UploadFile.read никогда не
    # затрагивает вызываемый метод (доказано ре-ревьюером: тест проходил
    # даже с откаченной production-правкой).
    async def _read_should_not_be_called(self, size=-1):
        raise AssertionError("file.read() не должен вызываться: file.size уже больше лимита")

    monkeypatch.setattr(StarletteUploadFile, "read", _read_should_not_be_called)

    big = b"x" * (30 * 1024 * 1024 + 1)
    response = await client.post(
        "/api/upload/image", files={"file": ("big.png", big, "image/png")},
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "Файл больше 30 МБ"


async def test_upload_image_rejects_wrong_content_type_with_422(client):
    response = await client.post(
        "/api/upload/image", files={"file": ("x.gif", b"GIF89a", "image/gif")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Поддерживаются только JPEG/PNG/WEBP"
