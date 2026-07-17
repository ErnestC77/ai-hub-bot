import hmac

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.db.session import get_session
from app.services.media_generation_service import handle_fal_webhook

router = APIRouter()


@router.post("/api/fal/webhook")
async def fal_webhook(request: Request, secret: str = "") -> dict:
    # Пустой секрет -> fail-closed; сравнение constant-time (compare_digest).
    if not settings.fal_webhook_secret or not hmac.compare_digest(secret, settings.fal_webhook_secret):
        raise HTTPException(status_code=403, detail="invalid secret")

    payload = await request.json()
    async with get_session() as session:
        found = await handle_fal_webhook(session, payload)

    if not found:
        # request_id ещё не закоммичен (гонка) -> 404 -> fal доставит повторно.
        raise HTTPException(status_code=404, detail="request not found")
    return {"ok": True}
