import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentProvider, PaymentStatus, SubscriptionStatus
from app.db.models import Payment, Subscription, Tariff, User
from app.services.payments.activation import activate_paid_payment


async def grant_manual_subscription(session: AsyncSession, user: User, tariff: Tariff) -> Subscription | None:
    """Ручная выдача подписки админом — идёт через тот же идемпотентный путь,
    что и оплаченные подписки (activate_paid_payment), просто с provider=manual.
    """
    payment = Payment(
        user_id=user.id,
        tariff_id=tariff.id,
        provider=PaymentProvider.manual,
        amount=0,
        currency="RUB",
        status=PaymentStatus.created,
        idempotence_key=str(uuid.uuid4()),
    )
    session.add(payment)
    await session.commit()

    result = await activate_paid_payment(session, payment_id=payment.id)
    return result.subscription if result else None


async def cancel_subscription(session: AsyncSession, subscription: Subscription) -> None:
    subscription.status = SubscriptionStatus.canceled
    await session.commit()
