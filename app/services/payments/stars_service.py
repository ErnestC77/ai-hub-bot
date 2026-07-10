import uuid

from aiogram.types import LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User
from app.services.payments.gateway import PaymentCreateResult, PaymentGateway


class TelegramStarsPaymentService(PaymentGateway):
    provider = PaymentProvider.telegram_stars

    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult:
        payment = Payment(
            user_id=user.id,
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
            title=package.title,
            description=f"{package.credits} кредитов для AI-запросов",
            payload=str(payment.id),
            currency="XTR",
            prices=[LabeledPrice(label=package.title, amount=package.price_stars)],
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
