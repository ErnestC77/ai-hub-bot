import uuid

from aiogram.types import LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import Payment, Tariff, User
from app.services.credit_packages import CreditPackage
from app.services.payments.gateway import PaymentCreateResult, PaymentGateway


class TelegramStarsPaymentService(PaymentGateway):
    provider = PaymentProvider.telegram_stars

    async def create_payment(self, session: AsyncSession, user: User, tariff: Tariff) -> PaymentCreateResult:
        payment = Payment(
            user_id=user.id,
            tariff_id=tariff.id,
            provider=self.provider,
            amount=tariff.price_stars,
            currency="XTR",
            status=PaymentStatus.created,
            idempotence_key=str(uuid.uuid4()),
        )
        session.add(payment)
        await session.commit()

        invoice_link = await bot.create_invoice_link(
            title=f"Подписка {tariff.name}",
            description=f"Подписка «{tariff.name}» на {tariff.period_days} дней",
            payload=str(payment.id),
            currency="XTR",
            prices=[LabeledPrice(label=tariff.name, amount=tariff.price_stars)],
        )
        payment.payment_url = invoice_link
        await session.commit()

        return PaymentCreateResult(payment=payment, kind="telegram_invoice", invoice_link=invoice_link)

    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult:
        payment = Payment(
            user_id=user.id,
            tariff_id=None,
            credit_package_code=package.code,
            provider=self.provider,
            amount=package.price_stars,
            currency="XTR",
            status=PaymentStatus.created,
            idempotence_key=str(uuid.uuid4()),
            payload={"credits": package.credits},
        )
        session.add(payment)
        await session.commit()

        invoice_link = await bot.create_invoice_link(
            title=package.name,
            description=f"{package.credits} кредитов для AI-запросов",
            payload=str(payment.id),
            currency="XTR",
            prices=[LabeledPrice(label=package.name, amount=package.price_stars)],
        )
        payment.payment_url = invoice_link
        await session.commit()

        return PaymentCreateResult(payment=payment, kind="telegram_invoice", invoice_link=invoice_link)

    async def check_payment_status(self, session: AsyncSession, payment: Payment) -> PaymentStatus:
        # У Bot API нет pull-запроса статуса Stars-платежа — источник истины
        # это successful_payment/PreCheckoutQuery, обрабатываемые в bot/handlers/payments.py.
        return payment.status

    async def refund_payment(self, session: AsyncSession, payment: Payment) -> bool:
        if not payment.provider_payment_id:
            return False

        user = await session.get(User, payment.user_id)
        if user is None:
            return False

        ok = await bot.refund_star_payment(
            user_id=user.telegram_id, telegram_payment_charge_id=payment.provider_payment_id
        )
        if ok:
            payment.status = PaymentStatus.refunded
            await session.commit()
        return ok
