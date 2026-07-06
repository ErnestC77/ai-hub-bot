import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.enums import PaymentProvider, PaymentStatus, SubscriptionStatus
from app.db.models import Payment, Subscription, Tariff, User
from app.db.session import get_session
from app.services.notification_service import (
    notify_payment_success,
    notify_subscription_expired,
    notify_subscription_expiring,
)
from app.services.payments import GATEWAYS
from app.services.payments.activation import activate_paid_payment
from app.services.payments.setup import register_all_gateways

logger = logging.getLogger(__name__)

register_all_gateways()


async def expire_subscriptions() -> None:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        subs = (
            await session.execute(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatus.active,
                    Subscription.expires_at <= now,
                )
            )
        ).scalars().all()

        for sub in subs:
            sub.status = SubscriptionStatus.expired
            user = await session.get(User, sub.user_id)
            tariff = await session.get(Tariff, sub.tariff_id)
            if user and tariff:
                await notify_subscription_expired(user.telegram_id, tariff.name)

        if subs:
            await session.commit()


async def warn_expiring_subscriptions() -> None:
    """Одно напоминание за ~23-24ч до конца подписки.

    Без отдельного поля "напоминание отправлено" (schema фиксирована ТЗ) —
    узкое скользящее окно, равное интервалу запуска джобы, гарантирует, что
    подписка попадёт в него ровно один раз (если воркер не был подолгу выключен).
    """
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(hours=23)
    window_end = now + timedelta(hours=24)

    async with get_session() as session:
        subs = (
            await session.execute(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatus.active,
                    Subscription.expires_at >= window_start,
                    Subscription.expires_at < window_end,
                )
            )
        ).scalars().all()

        for sub in subs:
            user = await session.get(User, sub.user_id)
            tariff = await session.get(Tariff, sub.tariff_id)
            if user and tariff:
                await notify_subscription_expiring(user.telegram_id, tariff.name, sub.expires_at)


async def poll_pending_yookassa_payments() -> None:
    """Страховка на случай потерянного webhook (раздел 7 bot_ai.md)."""
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        pending = (
            await session.execute(
                select(Payment).where(
                    Payment.provider == PaymentProvider.yookassa,
                    Payment.status == PaymentStatus.pending,
                    Payment.created_at < now - timedelta(minutes=3),
                    Payment.created_at > now - timedelta(hours=24),
                )
            )
        ).scalars().all()

        gateway = GATEWAYS[PaymentProvider.yookassa]
        for payment in pending:
            try:
                real_status = await gateway.check_payment_status(session, payment)
            except Exception:
                logger.exception("poll: failed to check yookassa payment %s", payment.id)
                continue

            if real_status == PaymentStatus.succeeded:
                subscription = await activate_paid_payment(session, payment_id=payment.id)
                if subscription:
                    user = await session.get(User, subscription.user_id)
                    tariff = await session.get(Tariff, subscription.tariff_id)
                    if user and tariff:
                        await notify_payment_success(user.telegram_id, tariff.name, subscription.expires_at)
            elif real_status == PaymentStatus.canceled:
                payment.status = PaymentStatus.canceled
                await session.commit()


async def cancel_stale_created_payments() -> None:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        stale = (
            await session.execute(
                select(Payment).where(
                    Payment.status == PaymentStatus.created,
                    Payment.created_at < now - timedelta(hours=24),
                )
            )
        ).scalars().all()

        for payment in stale:
            payment.status = PaymentStatus.canceled

        if stale:
            await session.commit()


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(expire_subscriptions, "interval", minutes=5, id="expire_subscriptions")
    scheduler.add_job(warn_expiring_subscriptions, "interval", hours=1, id="warn_expiring_subscriptions")
    scheduler.add_job(poll_pending_yookassa_payments, "interval", minutes=2, id="poll_pending_yookassa")
    scheduler.add_job(cancel_stale_created_payments, "interval", hours=24, id="cancel_stale_created_payments")
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("worker started")
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
