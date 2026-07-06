from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Banner(Base, TimestampMixin):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str | None] = mapped_column(String(200), default=None)
    badge_text: Mapped[str | None] = mapped_column(String(50), default=None)
    cta_text: Mapped[str] = mapped_column(String(50), default="Открыть")
    image_url: Mapped[str] = mapped_column(String(500))

    # "prompt" -- открыть чат с prefill-промптом (action_value = сам промпт);
    # "link" -- открыть внешнюю ссылку (action_value = URL)
    action_type: Mapped[str] = mapped_column(String(20), default="prompt")
    action_value: Mapped[str] = mapped_column(String(500))

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
