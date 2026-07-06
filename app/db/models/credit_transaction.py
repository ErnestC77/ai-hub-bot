from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import CreditTxType


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    type: Mapped[CreditTxType] = mapped_column()
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    reason: Mapped[str | None] = mapped_column(String(256))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
