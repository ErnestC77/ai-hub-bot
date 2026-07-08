from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.db.session import get_session
from app.services.media_generation_service import handle_fal_webhook

router = APIRouter()


@router.post("/api/fal/webhook")
async def fal_webhook(request: Request, secret: str = "") -> dict:
    if secret != settings.fal_webhook_secret or not settings.fal_webhook_secret:
        raise HTTPException(status_code=403, detail="invalid secret")

    payload = await request.json()
    async with get_session() as session:
        await handle_fal_webhook(session, payload)

    return {"ok": True}
