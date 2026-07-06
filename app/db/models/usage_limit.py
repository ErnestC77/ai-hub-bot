from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageLimit(Base):
    __tablename__ = "usage_limits"
    __table_args__ = (
        UniqueConstraint("user_id", "subscription_id", "period_start", name="ux_usage_limits_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"))

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    fast_used: Mapped[int] = mapped_column(Integer, default=0)
    medium_used: Mapped[int] = mapped_column(Integer, default=0)
    premium_used: Mapped[int] = mapped_column(Integer, default=0)
    images_used: Mapped[int] = mapped_column(Integer, default=0)
    daily_used: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
