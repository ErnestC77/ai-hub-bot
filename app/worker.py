import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import Payment, User
from app.db.session import get_session
from app.services.media_generation_service import refund_stale_reserved_requests
from app.services.notification_service import notify_credits_purchase
from app.services.payments import GATEWAYS
from app.services.payments.activation import activate_paid_payment
from app.services.payments.setup import register_all_gateways

logger = logging.getLogger(__name__)

register_all_gateways()


async def poll_pending_yookassa_payments() -> None:
    """Страховка на случай потерянного webhook ЮKassa: опрашиваем зависшие
    pending-платежи и активируем оплаченные (только пакеты кредитов, фаза 4)."""
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
                result = await activate_paid_payment(session, payment_id=payment.id)
                if result and result.credits_granted:
                    user = await session.get(User, payment.user_id)
                    if user:
                        await notify_credits_purchase(user.telegram_id, result.credits_granted)
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


async def reconcile_stale_media_reserves() -> None:
    """Возврат кредитов за image/video-запросы, по которым вебхук fal.ai так и
    не пришёл (фаза 3 оставила refund_stale_reserved_requests готовой к
    подключению сюда; сама функция коммитит транзакцию)."""
    async with get_session() as session:
        refunded = await refund_stale_reserved_requests(session)
    if refunded:
        logger.info("reconcile: refunded %d stale media reserves", refunded)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll_pending_yookassa_payments, "interval", minutes=2, id="poll_pending_yookassa")
    scheduler.add_job(cancel_stale_created_payments, "interval", hours=24, id="cancel_stale_created_payments")
    scheduler.add_job(reconcile_stale_media_reserves, "interval", minutes=5, id="reconcile_stale_media_reserves")
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
