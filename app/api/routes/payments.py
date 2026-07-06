import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.enums import PaymentProvider
from app.db.models import Payment, User
from app.services.payments import GATEWAYS
from app.services.subscription_service import get_tariff_by_code

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(current_user)])


class CreatePaymentRequest(BaseModel):
    tariff_code: str


class CreatePaymentResponse(BaseModel):
    payment_id: int
    invoice_link: str | None = None
    confirmation_url: str | None = None


class PaymentStatusOut(BaseModel):
    payment_id: int
    status: str


class PaymentHistoryItem(BaseModel):
    id: int
    provider: str
    amount: float
    currency: str
    status: str
    created_at: str


async def _get_tariff_or_404(session: AsyncSession, tariff_code: str):
    tariff = await get_tariff_by_code(session, tariff_code)
    if tariff is None or tariff.code == "free":
        raise HTTPException(status_code=404, detail="Тариф не найден")
    return tariff


@router.post("/payments/stars/create", response_model=CreatePaymentResponse)
async def create_stars_payment(
    body: CreatePaymentRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    tariff = await _get_tariff_or_404(session, body.tariff_code)
    try:
        result = await GATEWAYS[PaymentProvider.telegram_stars].create_payment(session, user, tariff)
    except Exception:
        logger.exception("stars create_payment failed")
        raise HTTPException(status_code=502, detail="Не удалось создать платёж, попробуйте позже")

    return CreatePaymentResponse(payment_id=result.payment.id, invoice_link=result.invoice_link)


@router.post("/payments/yookassa/create", response_model=CreatePaymentResponse)
async def create_yookassa_payment(
    body: CreatePaymentRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    tariff = await _get_tariff_or_404(session, body.tariff_code)
    try:
        result = await GATEWAYS[PaymentProvider.yookassa].create_payment(session, user, tariff)
    except Exception:
        logger.exception("yookassa create_payment failed")
        raise HTTPException(status_code=502, detail="Не удалось создать платёж, попробуйте позже")

    return CreatePaymentResponse(payment_id=result.payment.id, confirmation_url=result.confirmation_url)


@router.get("/payments/{payment_id}/status", response_model=PaymentStatusOut)
async def get_payment_status(
    payment_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> PaymentStatusOut:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Платёж не найден")

    gateway = GATEWAYS.get(payment.provider)
    status = await gateway.check_payment_status(session, payment) if gateway else payment.status
    return PaymentStatusOut(payment_id=payment.id, status=status.value)


@router.get("/payments/history", response_model=list[PaymentHistoryItem])
async def get_payment_history(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[PaymentHistoryItem]:
    payments = (
        await session.execute(
            select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(50)
        )
    ).scalars().all()

    return [
        PaymentHistoryItem(
            id=p.id,
            provider=p.provider.value,
            amount=float(p.amount),
            currency=p.currency,
            status=p.status.value,
            created_at=p.created_at.isoformat(),
        )
        for p in payments
    ]
