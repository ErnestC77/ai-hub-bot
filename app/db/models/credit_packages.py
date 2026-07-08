from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CreditPackage(Base, TimestampMixin):
    """Пакеты кредитов (замена dataclass-списка app/services/credit_packages.py).
    Использование в оплате -- фаза 4; здесь только таблица + сиды."""

    __tablename__ = "credit_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(64))
    credits: Mapped[int] = mapped_column(Integer)
    price_rub: Mapped[float] = mapped_column(Numeric(10, 2))
    description: Mapped[str | None] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
