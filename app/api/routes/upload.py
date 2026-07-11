import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import current_user
from app.config import settings

router = APIRouter(dependencies=[Depends(current_user)])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # тот же лимит, что уже проверяет PhotoUploadBox.tsx
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class UploadResponse(BaseModel):
    url: str


@router.post("/upload/image", response_model=UploadResponse)
async def upload_image(file: UploadFile) -> UploadResponse:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Поддерживаются только JPEG/PNG/WEBP")

    # Чтение целиком в память приемлемо при лимите 30 МБ (спека) --
    # стриминговая проверка для этого объёма не нужна.
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 30 МБ")

    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[file.content_type]
    filename = f"{uuid.uuid4().hex}.{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)

    # Файл живёт на локальном диске (эфемерно на Render) -- нужен только на
    # время одного запроса к fal.ai, персистентность не требуется (спека).
    return UploadResponse(url=f"{settings.backend_public_url}/uploads/{filename}")
