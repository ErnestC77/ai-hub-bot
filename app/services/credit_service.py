"""Движок кредитов. ЕДИНСТВЕННОЕ место, где можно менять users.credits_balance.

Правила (из спеки фазы 1):
- каждая операция лочит строку users через SELECT ... FOR UPDATE;
- credit_transactions -- неизменяемый аудит-лог со снимками balance_before/after;
- функции делают flush(), но НЕ commit() -- транзакцией владеет вызывающий код
  (фазы 2-3 создают AIRequest и резервируют кредиты в одной транзакции).
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CreditTxType, RequestStatus
from app.db.models import AIRequest, CreditTransaction, User


class InsufficientBalanceError(Exception):
    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required
        super().__init__(f"credits balance {balance} < required {required}")


async def _lock_user(session: AsyncSession, user_id: int) -> User:
    # На SQLite (юнит-тесты) FOR UPDATE игнорируется диалектом; на Postgres --
    # честная блокировка строки до конца транзакции вызывающего кода.
    return (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one()


async def reserve_credits(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    request_id: int | None,
    provider: str,
    model_code: str,
) -> CreditTransaction:
    """Удерживает amount кредитов до запроса. При нехватке баланса кидает
    InsufficientBalanceError и НИЧЕГО не пишет."""
    if amount <= 0:
        raise ValueError(f"reserve amount must be positive, got {amount}")

    user = await _lock_user(session, user_id)
    if user.credits_balance < amount:
        raise InsufficientBalanceError(balance=user.credits_balance, required=amount)

    balance_before = user.credits_balance
    user.credits_balance = balance_before - amount
    tx = CreditTransaction(
        user_id=user_id,
        type=CreditTxType.reserve,
        amount=-amount,
        balance_before=balance_before,
        balance_after=user.credits_balance,
        provider=provider,
        model_code=model_code,
        request_id=request_id,
    )
    session.add(tx)
    await session.flush()
    return tx


async def settle_request(
    session: AsyncSession, request: AIRequest, actual_credits: int
) -> CreditTransaction | None:
    """Шаги 6-9 reserve-flow из ТЗ: пересчёт по фактическому расходу после ответа
    провайдера. Возвращает корректирующую транзакцию (release/spend) или None,
    если корректировка не нужна / доплата невозможна."""
    if actual_credits < 0:
        raise ValueError(f"actual_credits must be >= 0, got {actual_credits}")
    if request.status != RequestStatus.reserved:
        raise ValueError(f"cannot settle request {request.id} with status {request.status}")

    user = await _lock_user(session, request.user_id)
    reserved = request.reserved_credits
    tx: CreditTransaction | None = None
    charged = reserved

    if actual_credits < reserved:
        # Вернуть разницу на баланс.
        diff = reserved - actual_credits
        balance_before = user.credits_balance
        user.credits_balance = balance_before + diff
        tx = CreditTransaction(
            user_id=user.id,
            type=CreditTxType.release,
            amount=diff,
            balance_before=balance_before,
            balance_after=user.credits_balance,
            provider=request.provider,
            model_code=request.model_code,
            request_id=request.id,
        )
        session.add(tx)
        charged = actual_credits
    elif actual_credits > reserved:
        diff = actual_credits - reserved
        if user.credits_balance >= diff:
            balance_before = user.credits_balance
            user.credits_balance = balance_before - diff
            tx = CreditTransaction(
                user_id=user.id,
                type=CreditTxType.spend,
                amount=-diff,
                balance_before=balance_before,
                balance_after=user.credits_balance,
                provider=request.provider,
                model_code=request.model_code,
                request_id=request.id,
            )
            session.add(tx)
            charged = actual_credits
        else:
            # Баланса на доплату нет: списываем 0 доплаты, оставляем charged=reserved
            # и помечаем запрос флагом -- это НЕ ошибка.
            request.insufficient_balance_after_usage = True

    request.charged_credits = charged
    request.status = RequestStatus.completed
    request.completed_at = datetime.now(timezone.utc)
    user.total_credits_spent += charged
    await session.flush()
    return tx


async def refund_request(
    session: AsyncSession, request: AIRequest, *, reason: str
) -> CreditTransaction:
    """Полный возврат при ошибке провайдера: reserved_credits, либо
    charged_credits, если запрос уже был рассчитан (settle)."""
    if request.status not in (RequestStatus.reserved, RequestStatus.completed):
        raise ValueError(f"cannot refund request {request.id} with status {request.status}")

    user = await _lock_user(session, request.user_id)
    already_settled = request.status == RequestStatus.completed
    refund_amount = request.charged_credits if already_settled else request.reserved_credits

    balance_before = user.credits_balance
    user.credits_balance = balance_before + refund_amount
    if already_settled:
        user.total_credits_spent = max(user.total_credits_spent - refund_amount, 0)

    tx = CreditTransaction(
        user_id=user.id,
        type=CreditTxType.refund,
        amount=refund_amount,
        balance_before=balance_before,
        balance_after=user.credits_balance,
        provider=request.provider,
        model_code=request.model_code,
        request_id=request.id,
        description=reason,
    )
    session.add(tx)
    request.status = RequestStatus.refunded
    request.charged_credits = 0  # итоговое списание по запросу -- ноль
    await session.flush()
    return tx


async def grant_credits(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    reason: str,
    tx_type: CreditTxType = CreditTxType.purchase,
    metadata: dict | None = None,
) -> CreditTransaction:
    """Начисление кредитов: покупка пакета (фаза 4) или админ-корректировка (фаза 5).
    metadata -- контекст начисления (например {"payment_id": ...} из activation.py),
    сохраняется в credit_transactions.metadata_json."""
    if amount <= 0:
        raise ValueError(f"grant amount must be positive, got {amount}")

    user = await _lock_user(session, user_id)
    balance_before = user.credits_balance
    user.credits_balance = balance_before + amount
    if tx_type == CreditTxType.purchase:
        user.total_credits_purchased += amount

    tx = CreditTransaction(
        user_id=user_id,
        type=tx_type,
        amount=amount,
        balance_before=balance_before,
        balance_after=user.credits_balance,
        description=reason,
        metadata_json=metadata,
    )
    session.add(tx)
    await session.flush()
    return tx
