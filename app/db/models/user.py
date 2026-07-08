from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(8))
    default_model_code: Mapped[str | None] = mapped_column(String(64))

    # Хранимый баланс -- единственный источник истины для balance >= amount.
    # Обновляется ТОЛЬКО функциями app/services/credit_service.py под SELECT ... FOR UPDATE.
    credits_balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_credits_purchased: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_credits_spent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
