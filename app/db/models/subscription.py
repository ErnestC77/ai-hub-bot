from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.enums import SubscriptionStatus


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"))

    status: Mapped[SubscriptionStatus] = mapped_column(default=SubscriptionStatus.active)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    source_payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    auto_renewal_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
