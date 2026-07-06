from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.enums import ModelCategory, ModelProvider


class ModelConfig(Base, TimestampMixin):
    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_code: Mapped[str] = mapped_column(String(64), unique=True)
    provider: Mapped[ModelProvider] = mapped_column()
    display_name: Mapped[str] = mapped_column(String(64))
    category: Mapped[ModelCategory] = mapped_column()

    cost_input_per_1m: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    cost_output_per_1m: Mapped[float] = mapped_column(Numeric(10, 4), default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=8000)
