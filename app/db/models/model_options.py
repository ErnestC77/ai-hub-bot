from sqlalchemy import Boolean, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import ModelOptionKind


class ModelOption(Base):
    """Опция модели: набор допустимых значений диктует сам провайдер, а не мы.

    Контракты fal несводимы между собой (проверено по схемам 2026-07-15):
    Wan берёт resolution=480p/580p/720p И отдельно video_quality; Kling --
    duration строкой "5"/"10"; Veo -- "4s"/"6s"/"8s" плюс generate_audio;
    Ovi -- сырые пиксели. Поэтому provider_params -- JSON, а не колонки:
    одна пользовательская опция может выставлять несколько полей провайдера
    (у Wan «720p» задаёт и resolution, и video_quality).
    """

    __tablename__ = "model_options"
    __table_args__ = (UniqueConstraint("model_id", "kind", "code", name="uq_model_option_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("ai_models.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ModelOptionKind] = mapped_column()
    code: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(64))
    # JSONB на Postgres, JSON на sqlite (тесты). Внутрь никогда не запрашиваем --
    # читаем целиком и мержим в тело запроса к провайдеру.
    provider_params: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    # Во сколько раз опция дороже дефолтной комбинации модели.
    # Выводится из замеров провайдера, не назначается (см. Global Constraints).
    credits_multiplier: Mapped[float] = mapped_column(Numeric(6, 3), default=1.0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
