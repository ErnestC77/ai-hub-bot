from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.services.payments.gateway import GATEWAYS


async def refund(session: AsyncSession, payment: Payment) -> bool:
    gateway = GATEWAYS.get(payment.provider)
    if gateway is None:
        return False
    return await gateway.refund_payment(session, payment)
