from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType, PaymentProvider, PaymentStatus
from app.db.models import Payment, User
from app.services.credit_service import grant_credits
from app.services.settings_service import get_setting


@dataclass
class ActivationResult:
    credits_granted: int = 0
    # Надбавка за первую покупку (0, если не первая или бонус выключен) --
    # вебхук добавляет её в уведомление об оплате.
    bonus_credits: int = 0


async def _first_purchase_bonus(session: AsyncSession, payment: Payment, credits: int) -> int:
    """Бонус-кредиты первой покупки: min(credits * percent/100, cap).

    «Первая» определяется по total_credits_purchased ДО начисления пакета --
    поле растёт только на tx_type=purchase (welcome/referral его не трогают).
    Сам бонус идёт типом first_purchase_bonus, не purchase: иначе он второй раз
    поднял бы total_credits_purchased и исказил статистику покупок."""
    user = await session.get(User, payment.user_id)
    if user is None or user.total_credits_purchased > 0:
        return 0
    percent = await get_setting(session, "first_purchase_bonus_percent", cast=int, default=0)
    if percent <= 0:
        return 0
    cap = await get_setting(session, "first_purchase_bonus_cap", cast=int, default=1500)
    return min(credits * percent // 100, cap)


async def activate_paid_payment(
    session: AsyncSession,
    *,
    payment_id: int | None = None,
    provider: PaymentProvider | None = None,
    provider_payment_id: str | None = None,
    charge_id: str | None = None,
) -> ActivationResult | None:
    """Единая идемпотентная активация оплаты пакета кредитов
    (Stars/ЮKassa/crypto/manual).

    Один и тот же платёж не может активироваться дважды: платёж выбирается с
    блокировкой строки (FOR UPDATE), и если он уже succeeded -- возвращается
    None без побочных эффектов. Связь платёж→начисление живёт в
    credit_transactions.metadata_json["payment_id"] (дизайн фазы 1).
    """
    query = select(Payment).with_for_update()
    if payment_id is not None:
        query = query.where(Payment.id == payment_id)
    elif provider is not None and provider_payment_id is not None:
        query = query.where(
            Payment.provider == provider, Payment.provider_payment_id == provider_payment_id
        )
    else:
        raise ValueError("provide payment_id or (provider, provider_payment_id)")

    payment = (await session.execute(query)).scalar_one_or_none()
    if payment is None or payment.status == PaymentStatus.succeeded:
        return None

    payment.status = PaymentStatus.succeeded
    payment.paid_at = datetime.now(timezone.utc)
    if charge_id:
        payment.provider_payment_id = charge_id

    credits = int((payment.payload or {}).get("credits", 0))
    bonus = 0
    if credits > 0:
        # Бонус считаем ДО начисления пакета: grant_credits(purchase) поднимет
        # total_credits_purchased, и покупка перестала бы выглядеть первой.
        bonus = await _first_purchase_bonus(session, payment, credits)
        await grant_credits(
            session,
            payment.user_id,
            credits,
            reason=f"credit package {payment.credit_package_code}",
            metadata={"payment_id": payment.id},
        )
        if bonus > 0:
            await grant_credits(
                session,
                payment.user_id,
                bonus,
                reason="first purchase bonus",
                tx_type=CreditTxType.first_purchase_bonus,
                metadata={"payment_id": payment.id},
            )

    await session.commit()
    return ActivationResult(credits_granted=credits, bonus_credits=bonus)
