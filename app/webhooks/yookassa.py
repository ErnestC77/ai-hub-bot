import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import Payment, User
from app.db.session import get_session
from app.services.notification_service import notify_credits_purchase
from app.services.payments import GATEWAYS
from app.services.payments.activation import activate_paid_payment

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhooks/yookassa")
async def yookassa_webhook(request: Request) -> dict:
    payload = await request.json()
    object_id = (payload.get("object") or {}).get("id")
    if not object_id:
        logger.warning("yookassa webhook without object.id: %s", payload)
        return {"ok": True}

    async with get_session() as session:
        payment = (
            await session.execute(
                select(Payment).where(
                    Payment.provider == PaymentProvider.yookassa,
                    Payment.provider_payment_id == object_id,
                )
            )
        ).scalar_one_or_none()

        if payment is None:
            logger.warning("yookassa webhook for unknown payment %s", object_id)
            return {"ok": True}

        if payment.status == PaymentStatus.succeeded:
            return {"ok": True}

        try:
            # Не доверяем телу webhook — перечитываем статус напрямую из API ЮKassa.
            real_status = await GATEWAYS[PaymentProvider.yookassa].check_payment_status(session, payment)
        except Exception as exc:
            logger.exception("failed to verify yookassa payment %s", object_id)
            raise HTTPException(status_code=500) from exc

        if real_status == PaymentStatus.succeeded:
            result = await activate_paid_payment(
                session, provider=PaymentProvider.yookassa, provider_payment_id=object_id
            )
            logger.info("yookassa payment %s activated -> result=%s", object_id, result)

            if result and result.credits_granted:
                user = await session.get(User, payment.user_id)
                if user:
                    await notify_credits_purchase(user.telegram_id, result.credits_granted)
        elif real_status == PaymentStatus.canceled:
            payment.status = PaymentStatus.canceled
            await session.commit()

    return {"ok": True}
