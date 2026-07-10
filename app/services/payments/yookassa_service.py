import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from yookassa import Configuration
from yookassa import Payment as YooPaymentAPI
from yookassa import Refund as YooRefundAPI

from app.config import settings
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User
from app.services.payments.gateway import PaymentCreateResult, PaymentGateway

Configuration.configure(settings.yookassa_shop_id, settings.yookassa_secret_key)

_STATUS_MAP = {
    "pending": PaymentStatus.pending,
    "waiting_for_capture": PaymentStatus.pending,
    "succeeded": PaymentStatus.succeeded,
    "canceled": PaymentStatus.canceled,
}


class YooKassaPaymentService(PaymentGateway):
    provider = PaymentProvider.yookassa

    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult:
        idempotence_key = str(uuid.uuid4())
        payment = Payment(
            user_id=user.id,
            credit_package_code=package.code,
            provider=self.provider,
            amount=package.price_rub,
            currency="RUB",
            status=PaymentStatus.created,
            idempotence_key=idempotence_key,
            payload={"credits": package.credits},
        )
        session.add(payment)
        await session.commit()

        # yookassa SDK синхронный (requests) — уводим блокирующий HTTP-вызов в поток,
        # чтобы не стопорить event loop остальных пользователей.
        response = await asyncio.to_thread(
            YooPaymentAPI.create,
            {
                "amount": {"value": f"{package.price_rub:.2f}", "currency": "RUB"},
                "capture": True,
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{settings.payment_return_url}?payment_id={payment.id}",
                },
                "description": f"{package.title} ({package.credits} кредитов)",
                "metadata": {
                    "internal_payment_id": str(payment.id),
                    "telegram_id": str(user.telegram_id),
                    "credit_package_code": package.code,
                },
                "receipt": {
                    "customer": {"email": "support@ai-hub-bot.ru"},
                    "items": [
                        {
                            "description": package.title,
                            "quantity": "1.00",
                            "amount": {"value": f"{package.price_rub:.2f}", "currency": "RUB"},
                            "vat_code": 1,
                            "payment_subject": "service",
                            "payment_mode": "full_payment",
                        }
                    ],
                },
            },
            idempotence_key,
        )

        payment.provider_payment_id = response.id
        payment.payment_url = response.confirmation.confirmation_url
        payment.status = _STATUS_MAP.get(response.status, PaymentStatus.pending)
        await session.commit()

        return PaymentCreateResult(
            payment=payment, kind="external_url", confirmation_url=response.confirmation.confirmation_url
        )

    async def check_payment_status(self, session: AsyncSession, payment: Payment) -> PaymentStatus:
        if not payment.provider_payment_id:
            return payment.status
        response = await asyncio.to_thread(YooPaymentAPI.find_one, payment.provider_payment_id)
        return _STATUS_MAP.get(response.status, payment.status)

    async def refund_payment(self, session: AsyncSession, payment: Payment) -> bool:
        if not payment.provider_payment_id:
            return False

        await asyncio.to_thread(
            YooRefundAPI.create,
            {
                "amount": {"value": f"{payment.amount:.2f}", "currency": payment.currency},
                "payment_id": payment.provider_payment_id,
            },
        )
        payment.status = PaymentStatus.refunded
        await session.commit()
        return True
