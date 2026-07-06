from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType
from app.db.models import CreditTransaction, User

# CreditTransaction.amount хранится как ПОДПИСАННОЕ значение: положительное --
# начисление (deposit/bonus/refund), отрицательное -- списание (spend).
# Баланс — это просто сумма всех записей, без отдельной логики по type.


async def get_balance(session: AsyncSession, user: User) -> int:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.user_id == user.id
            )
        )
    ).scalar_one()
    return int(total)


async def grant_credits(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    reason: str,
    payment_id: int | None = None,
    tx_type: CreditTxType = CreditTxType.deposit,
) -> None:
    session.add(
        CreditTransaction(user_id=user_id, type=tx_type, amount=amount, reason=reason, payment_id=payment_id)
    )
    await session.commit()


async def spend_credits(session: AsyncSession, user: User, amount: int, *, reason: str) -> bool:
    """Возвращает False, если баланса не хватает -- ничего не списывает."""
    balance = await get_balance(session, user)
    if balance < amount:
        return False

    session.add(CreditTransaction(user_id=user.id, type=CreditTxType.spend, amount=-amount, reason=reason))
    await session.commit()
    return True
