from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType, PaymentProvider, PaymentStatus, SubscriptionStatus
from app.db.models import Payment, Subscription, Tariff, UsageLimit
from app.services.credit_service import grant_credits
from app.services.subscription_service import get_active_subscription


@dataclass
class ActivationResult:
    subscription: Subscription | None = None
    credits_granted: int | None = None


async def activate_paid_payment(
    session: AsyncSession,
    *,
    payment_id: int | None = None,
    provider: PaymentProvider | None = None,
    provider_payment_id: str | None = None,
    charge_id: str | None = None,
) -> ActivationResult | None:
    """Единая идемпотентная активация оплаты для Stars/ЮKassa/manual --
    подписка (payment.tariff_id) или пакет кредитов (payment.credit_package_code).

    Один и тот же платёж не может активироваться дважды: платёж выбирается с
    блокировкой строки (FOR UPDATE), и если он уже succeeded — возвращается
    None без побочных эффектов. Продление подписки считается от текущего
    expires_at активной подписки, а не от now() — чтобы продление "заранее"
    не сжигало уже оплаченный остаток периода.
    """
    query = select(Payment).with_for_update()
    if payment_id is not None:
        query = query.where(Payment.id == payment_id)
    elif provider is not None and provider_payment_id is not None:
        query = query.where(Payment.provider == provider, Payment.provider_payment_id == provider_payment_id)
    else:
        raise ValueError("provide payment_id or (provider, provider_payment_id)")

    payment = (await session.execute(query)).scalar_one_or_none()
    if payment is None or payment.status == PaymentStatus.succeeded:
        return None

    now = datetime.now(timezone.utc)
    payment.status = PaymentStatus.succeeded
    payment.paid_at = now
    if charge_id:
        payment.provider_payment_id = charge_id

    if payment.credit_package_code is not None:
        credits = int((payment.payload or {}).get("credits", 0))
        await grant_credits(
            session,
            payment.user_id,
            credits,
            reason=f"credit package {payment.credit_package_code}",
            payment_id=payment.id,
            tx_type=CreditTxType.deposit,
        )
        await session.commit()
        return ActivationResult(credits_granted=credits)

    tariff = await session.get(Tariff, payment.tariff_id)

    current = await get_active_subscription(session, payment.user_id)
    base = max(now, current.expires_at) if current else now
    expires_at = base + timedelta(days=tariff.period_days)

    subscription = Subscription(
        user_id=payment.user_id,
        tariff_id=payment.tariff_id,
        status=SubscriptionStatus.active,
        started_at=now,
        expires_at=expires_at,
        source_payment_id=payment.id,
    )
    session.add(subscription)
    await session.flush()

    session.add(
        UsageLimit(
            user_id=payment.user_id,
            subscription_id=subscription.id,
            period_start=now,
            period_end=expires_at,
        )
    )

    await session.commit()
    return ActivationResult(subscription=subscription)
