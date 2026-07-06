from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentProvider, PaymentStatus, SubscriptionStatus
from app.db.models import Payment, Subscription, Tariff, UsageLimit
from app.services.subscription_service import get_active_subscription


async def activate_paid_payment(
    session: AsyncSession,
    *,
    payment_id: int | None = None,
    provider: PaymentProvider | None = None,
    provider_payment_id: str | None = None,
    charge_id: str | None = None,
) -> Subscription | None:
    """Единая идемпотентная активация подписки для Stars/ЮKassa/manual.

    Один и тот же платёж не может активировать подписку дважды: платёж
    выбирается с блокировкой строки (FOR UPDATE), и если он уже succeeded —
    возвращается None без побочных эффектов. Продление подписки считается от
    текущего expires_at активной подписки, а не от now() — чтобы продление
    "заранее" не сжигало уже оплаченный остаток периода.
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
    return subscription
