import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.enums import ModelCategory, PaymentProvider
from app.db.models import AiModel, CreditPackage, Payment, User
from app.services.payments import GATEWAYS
from app.services.pricing import VIDEO_MIN_CREDITS
from app.services.settings_service import get_setting

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(current_user)])


class CreditPackageOut(BaseModel):
    code: str
    title: str
    credits: int
    price_rub: float
    price_stars: int
    # «Примерно на сколько хватит»: по самой дешёвой активной фото/видео-модели
    # каталога (оптимистичный потолок -> на фронте формулируем «до N»). 0, если
    # моделей такой категории нет.
    approx_photos: int
    approx_videos: int
    # Бонус первой покупки для ЭТОГО юзера и пакета: 0, если уже покупал или
    # бонус выключен. Считается как min(credits * percent/100, cap) -- та же
    # формула, что начислит activation.py после оплаты.
    first_purchase_bonus: int


class CreateCreditPaymentRequest(BaseModel):
    package_code: str


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


async def _cheapest_media_costs(session: AsyncSession) -> tuple[int, int]:
    """Мин. стоимость одной генерации в кредитах для фото и видео по каталогу.
    Фото: пол = min_credits модели; видео: пол = max(min_credits, VIDEO_MIN_CREDITS).
    0, если моделей категории нет."""
    rows = (
        await session.execute(
            select(AiModel.category, AiModel.min_credits).where(
                AiModel.is_active.is_(True),
                AiModel.is_visible.is_(True),
                AiModel.category.in_((ModelCategory.image, ModelCategory.video)),
            )
        )
    ).all()
    photos = [m for c, m in rows if c == ModelCategory.image]
    videos = [max(m, VIDEO_MIN_CREDITS) for c, m in rows if c == ModelCategory.video]
    return (min(photos) if photos else 0), (min(videos) if videos else 0)


@router.get("/credits/packages", response_model=list[CreditPackageOut])
async def get_credit_packages(
    session: AsyncSession = Depends(get_db), user: User = Depends(current_user)
) -> list[CreditPackageOut]:
    packages = (
        await session.execute(
            select(CreditPackage)
            .where(CreditPackage.is_active.is_(True))
            .order_by(CreditPackage.price_rub)
        )
    ).scalars().all()
    photo_cost, video_cost = await _cheapest_media_costs(session)

    bonus_percent = 0
    bonus_cap = 0
    if user.total_credits_purchased == 0:
        bonus_percent = await get_setting(
            session, "first_purchase_bonus_percent", cast=int, default=0
        )
        bonus_cap = await get_setting(session, "first_purchase_bonus_cap", cast=int, default=1500)

    def bonus_for(credits: int) -> int:
        if bonus_percent <= 0:
            return 0
        return min(credits * bonus_percent // 100, bonus_cap)

    return [
        CreditPackageOut(
            code=p.code, title=p.title, credits=p.credits,
            price_rub=float(p.price_rub), price_stars=p.price_stars,
            approx_photos=(p.credits // photo_cost) if photo_cost else 0,
            approx_videos=(p.credits // video_cost) if video_cost else 0,
            first_purchase_bonus=bonus_for(p.credits),
        )
        for p in packages
    ]


async def _get_credit_package_or_404(session: AsyncSession, package_code: str) -> CreditPackage:
    package = (
        await session.execute(
            select(CreditPackage).where(
                CreditPackage.code == package_code, CreditPackage.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="Пакет кредитов не найден")
    return package


async def _create_credit_payment(
    provider: PaymentProvider, package_code: str, user: User, session: AsyncSession
) -> CreatePaymentResponse:
    package = await _get_credit_package_or_404(session, package_code)
    try:
        result = await GATEWAYS[provider].create_credit_payment(session, user, package)
    except Exception:
        logger.exception("%s create_credit_payment failed", provider.value)
        raise HTTPException(status_code=502, detail="Не удалось создать платёж, попробуйте позже")

    return CreatePaymentResponse(
        payment_id=result.payment.id,
        invoice_link=result.invoice_link,
        confirmation_url=result.confirmation_url,
    )


@router.post("/payments/credits/stars/create", response_model=CreatePaymentResponse)
async def create_stars_credit_payment(
    body: CreateCreditPaymentRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    return await _create_credit_payment(PaymentProvider.telegram_stars, body.package_code, user, session)


@router.post("/payments/credits/yookassa/create", response_model=CreatePaymentResponse)
async def create_yookassa_credit_payment(
    body: CreateCreditPaymentRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    return await _create_credit_payment(PaymentProvider.yookassa, body.package_code, user, session)


@router.post("/payments/credits/crypto/create", response_model=CreatePaymentResponse)
async def create_crypto_credit_payment(
    body: CreateCreditPaymentRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CreatePaymentResponse:
    return await _create_credit_payment(PaymentProvider.crypto, body.package_code, user, session)


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
