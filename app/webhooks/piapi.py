from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.db.session import get_session
from app.services.generation_service import handle_piapi_webhook

router = APIRouter()


@router.post("/api/piapi/webhook")
async def piapi_webhook(request: Request, secret: str = "") -> dict:
    if secret != settings.piapi_webhook_secret or not settings.piapi_webhook_secret:
        raise HTTPException(status_code=403, detail="invalid secret")

    payload = await request.json()
    async with get_session() as session:
        await handle_piapi_webhook(session, payload)

    return {"ok": True}
