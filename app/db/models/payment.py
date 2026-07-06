from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.enums import PaymentProvider, PaymentStatus


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="ux_payments_provider_payment_id"),
        UniqueConstraint("idempotence_key", name="ux_payments_idempotence_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Ровно одно из двух: подписка на тариф (tariff_id) или разовая покупка
    # пакета кредитов (credit_package_code) -- см. activate_paid_payment().
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"))
    credit_package_code: Mapped[str | None] = mapped_column(String(32))

    provider: Mapped[PaymentProvider] = mapped_column()
    provider_payment_id: Mapped[str | None] = mapped_column(String(128))

    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[PaymentStatus] = mapped_column(default=PaymentStatus.created)

    payment_url: Mapped[str | None] = mapped_column(String(512))
    idempotence_key: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSON)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
