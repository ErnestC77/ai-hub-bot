from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier


class AiModel(Base, TimestampMixin):
    """Каталог AI-моделей (замена ModelConfig). Все цены/кредиты редактируются
    через будущую админку (фаза 5) -- бизнес-логика не привязана к конкретной модели."""

    __tablename__ = "ai_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[ModelProvider] = mapped_column()
    category: Mapped[ModelCategory] = mapped_column()
    code: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    provider_model_id: Mapped[str] = mapped_column(String(128))
    tier: Mapped[ModelTier] = mapped_column()

    input_price_usd_per_1m_tokens: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    output_price_usd_per_1m_tokens: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    fixed_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    cost_unit: Mapped[CostUnit] = mapped_column()

    min_credits: Mapped[int] = mapped_column(Integer, default=0)
    recommended_credits: Mapped[int] = mapped_column(Integer, default=0)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=8000)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
