import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import CreditPackage, Payment, User
from app.services.payments.gateway import PaymentCreateResult, PaymentGateway

# Заглушка (фаза 4): интеграции с реальным крипто-процессором нет.
# Подтверждение оплаты -- ручное: админ начисляет кредиты через grant_credits
# напрямую (или через admin-команду фазы 5), автоматического webhook нет.
CRYPTO_PAYMENT_INSTRUCTION = (
    "Оплата криптовалютой подтверждается вручную: напишите в поддержку "
    "и укажите номер платежа."
)


class CryptoPaymentGateway(PaymentGateway):
    provider = PaymentProvider.crypto

    async def create_credit_payment(
        self, session: AsyncSession, user: User, package: CreditPackage
    ) -> PaymentCreateResult:
        payment = Payment(
            user_id=user.id,
            credit_package_code=package.code,
            provider=self.provider,
            amount=package.price_rub,  # номинал в рублях; реальный курс -- дело процессора (вне фазы 4)
            currency="RUB",
            status=PaymentStatus.created,
            idempotence_key=str(uuid.uuid4()),
            payload={"credits": package.credits},
            payment_url=CRYPTO_PAYMENT_INSTRUCTION,
        )
        session.add(payment)
        await session.commit()

        return PaymentCreateResult(
            payment=payment, kind="external_url", confirmation_url=CRYPTO_PAYMENT_INSTRUCTION
        )

    async def check_payment_status(self, session: AsyncSession, payment: Payment) -> PaymentStatus:
        # Внешнего API нет -- источник истины это текущий статус в БД
        # (меняется активацией/админом, не этим методом).
        return payment.status

    async def refund_payment(self, session: AsyncSession, payment: Payment) -> bool:
        # Возвраты возможны только вручную, пока не подключён реальный
        # крипто-процессор (вне рамок фазы 4; admin-инструменты -- фаза 5).
        raise NotImplementedError(
            "crypto refunds are manual until a real processor is integrated"
        )
