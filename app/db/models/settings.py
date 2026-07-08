from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Setting(Base):
    """Бизнес-настройки (курс, маржа, цена кредита), редактируемые через будущую
    админку (фаза 5). НЕ путать с app.config.Settings -- те читают .env (API-ключи)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(8))  # int / float / str / bool
    description: Mapped[str | None] = mapped_column(String(256))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
