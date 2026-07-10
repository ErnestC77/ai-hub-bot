from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import Payment
from app.services.credit_service import grant_credits


@dataclass
class ActivationResult:
    credits_granted: int = 0


async def activate_paid_payment(
    session: AsyncSession,
    *,
    payment_id: int | None = None,
    provider: PaymentProvider | None = None,
    provider_payment_id: str | None = None,
    charge_id: str | None = None,
) -> ActivationResult | None:
    """Единая идемпотентная активация оплаты пакета кредитов
    (Stars/ЮKassa/crypto/manual).

    Один и тот же платёж не может активироваться дважды: платёж выбирается с
    блокировкой строки (FOR UPDATE), и если он уже succeeded -- возвращается
    None без побочных эффектов. Связь платёж→начисление живёт в
    credit_transactions.metadata_json["payment_id"] (дизайн фазы 1).
    """
    query = select(Payment).with_for_update()
    if payment_id is not None:
        query = query.where(Payment.id == payment_id)
    elif provider is not None and provider_payment_id is not None:
        query = query.where(
            Payment.provider == provider, Payment.provider_payment_id == provider_payment_id
        )
    else:
        raise ValueError("provide payment_id or (provider, provider_payment_id)")

    payment = (await session.execute(query)).scalar_one_or_none()
    if payment is None or payment.status == PaymentStatus.succeeded:
        return None

    payment.status = PaymentStatus.succeeded
    payment.paid_at = datetime.now(timezone.utc)
    if charge_id:
        payment.provider_payment_id = charge_id

    credits = int((payment.payload or {}).get("credits", 0))
    if credits > 0:
        await grant_credits(
            session,
            payment.user_id,
            credits,
            reason=f"credit package {payment.credit_package_code}",
            metadata={"payment_id": payment.id},
        )

    await session.commit()
    return ActivationResult(credits_granted=credits)
