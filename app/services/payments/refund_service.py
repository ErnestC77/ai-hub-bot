from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentStatus
from app.db.models import Payment
from app.services.credit_service import revoke_purchase_credits
from app.services.payments.gateway import GATEWAYS


async def refund(session: AsyncSession, payment: Payment) -> bool:
    """Возврат оплаты пакета: внешний возврат + ОТЗЫВ начисленных кредитов.

    Вернуть можно только УСПЕШНЫЙ платёж (нельзя «вернуть» pending/failed/
    created/refunded -- иначе можно отозвать кредиты, которые не начислялись,
    или отозвать дважды). Кредиты отзываются ДО вызова гейтвея: gateway.
    refund_payment коммитит status=refunded вместе с этим отзывом одной
    транзакцией, а при ошибке внешнего провайдера всё откатывается.
    """
    if payment.status != PaymentStatus.succeeded:
        return False

    gateway = GATEWAYS.get(payment.provider)
    if gateway is None:
        return False

    credits = int((payment.payload or {}).get("credits", 0))
    if credits > 0:
        await revoke_purchase_credits(
            session,
            payment.user_id,
            credits,
            reason=f"refund package {payment.credit_package_code}",
            metadata={"payment_id": payment.id},
        )

    try:
        ok = await gateway.refund_payment(session, payment)
    except NotImplementedError:
        # crypto: возврат только вручную, пока нет процессора -> 400, не 500.
        await session.rollback()
        return False

    if not ok:
        await session.rollback()  # отменяем отзыв кредитов: возврат не состоялся
        return False
    return True
