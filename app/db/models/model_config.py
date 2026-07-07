from sqlalchemy import Boolean, Integer, JSON, Numeric, String
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

    # Цена одного запроса в кредитах -- списывается из баланса пользователя,
    # когда лимит тарифа по этой категории исчерпан (кредиты поверх тарифов).
    credit_cost: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # Какой ключ провайдера использовать (app.services.keys.enums.KeyPurpose) --
    # разные модели одного provider могут требовать разные ключи (text/image/premium/...).
    key_purpose: Mapped[str] = mapped_column(String(50), default="text", server_default="text")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=8000)

    # PiAPI unified task API identifiers. None for non-PiAPI rows (e.g. dall-e-3).
    piapi_model: Mapped[str | None] = mapped_column(String(64))
    piapi_task_type: Mapped[str | None] = mapped_column(String(64))
    # Fixed request fields PiAPI needs beyond "prompt" (resolution, duration, etc).
    piapi_extra_input: Mapped[dict | None] = mapped_column(JSON)
    # Video only -- informational + drives the frontend poll timeout.
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
