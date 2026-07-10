from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from app.db.enums import PaymentStatus
from app.db.models import Payment
from app.db.session import get_session
from app.services.payments.activation import activate_paid_payment

router = Router(name="payments")


@router.pre_checkout_query()
async def handle_pre_checkout(query: PreCheckoutQuery) -> None:
    async with get_session() as session:
        payment = None
        try:
            payment = await session.get(Payment, int(query.invoice_payload))
        except ValueError:
            payment = None

        if payment is None or payment.status != PaymentStatus.created:
            await query.answer(ok=False, error_message="Платёж не найден или уже обработан.")
            return

        await query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    sp = message.successful_payment
    try:
        payment_id = int(sp.invoice_payload)
    except ValueError:
        return

    async with get_session() as session:
        result = await activate_paid_payment(
            session, payment_id=payment_id, charge_id=sp.telegram_payment_charge_id
        )

    if result is None:
        await message.answer("Оплата получена, но уже была обработана ранее.")
    elif result.credits_granted:
        await message.answer(f"✅ Оплата прошла! Начислено {result.credits_granted} кредитов.")
