from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import ModelCategory, RequestStatus


class AIRequest(Base):
    """Биллинговая запись AI-запроса. Полные prompt/answer не хранятся --
    только prompt_preview (обрезка до 200 символов)."""

    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    provider: Mapped[str] = mapped_column(String(32))  # "openrouter" / "fal"
    model_code: Mapped[str] = mapped_column(String(64))
    category: Mapped[ModelCategory] = mapped_column()
    status: Mapped[RequestStatus] = mapped_column(default=RequestStatus.pending)

    prompt_preview: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    estimated_credits: Mapped[int] = mapped_column(Integer, default=0)
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0)
    charged_credits: Mapped[int] = mapped_column(Integer, default=0)
    provider_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)

    provider_response_id: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    # actual > reserved и баланса на доплату не хватило -- см. credit_service.settle_request.
    insufficient_balance_after_usage: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
