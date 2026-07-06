from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Tariff(Base, TimestampMixin):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)

    price_rub: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    price_stars: Mapped[int] = mapped_column(Integer, default=0)
    period_days: Mapped[int] = mapped_column(Integer, default=30)

    fast_limit: Mapped[int] = mapped_column(Integer, default=0)
    medium_limit: Mapped[int] = mapped_column(Integer, default=0)
    premium_limit: Mapped[int] = mapped_column(Integer, default=0)
    image_limit: Mapped[int] = mapped_column(Integer, default=0)
    daily_limit: Mapped[int] = mapped_column(Integer, default=0)

    max_input_tokens: Mapped[int] = mapped_column(Integer, default=4000)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=2000)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
