from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.enums import ModelCategory, RequestStatus


class AIRequest(Base, TimestampMixin):
    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    model_code: Mapped[str] = mapped_column(String(64))
    model_category: Mapped[ModelCategory] = mapped_column()

    prompt: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)

    status: Mapped[RequestStatus] = mapped_column(default=RequestStatus.processing)
    error_message: Mapped[str | None] = mapped_column(Text)
