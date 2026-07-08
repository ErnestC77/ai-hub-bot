from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import CreditTxType


class CreditTransaction(Base):
    """Неизменяемый аудит-лог кредитов. amount -- ПОДПИСАННОЕ значение:
    reserve/spend -- отрицательные; purchase/refund/release -- положительные.
    Строки создаются только внутри app/services/credit_service.py."""

    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    type: Mapped[CreditTxType] = mapped_column()
    amount: Mapped[int] = mapped_column(Integer)
    balance_before: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)

    provider: Mapped[str | None] = mapped_column(String(32))  # "openrouter" / "fal" / None
    model_code: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("ai_requests.id"))
    description: Mapped[str | None] = mapped_column(String(256))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
