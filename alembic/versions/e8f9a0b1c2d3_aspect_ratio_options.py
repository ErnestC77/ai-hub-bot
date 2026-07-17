"""Формат кадра: enum-значение aspect_ratio + опции для всех фото/видео-моделей.

Ось aspect_ratio -- для 7 моделей с независимой ручкой провайдера (wan, kling,
veo, flux, обе nano-banana; у ovi аспект живёт в resolution-парах). У qwen_image
и seedream аспект -- ТО ЖЕ поле image_size, что и размер, поэтому там это
расширение существующей оси quality, а не отдельная ось (две оси, пишущие один
ключ, молча затирали бы друг друга при мерже provider_params).

Все множители 1.0: формат кадра на цену не влияет (видео тарифицируется
секундами и разрешением, фото-модели -- плоско или по мегапикселям, а все
пресеты <= дефолтного square_hd). Enum-значения выверены по OpenAPI-схемам
fal 2026-07-17.

Идемпотентна: вставляет только отсутствующие (model, kind, code); сид делает
то же самое -- кто первый прибежал, тот и вставил, второй пропустит.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-17 16:00:00.000000
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ar(model_code, code, label, params, default=False, so=10):
    return dict(model_code=model_code, kind="aspect_ratio", code=code, label=label,
                params=json.dumps(params), mult="1.0", is_default=default, sort_order=so)


def _q(model_code, code, label, preset, so):
    return dict(model_code=model_code, kind="quality", code=code, label=label,
                params=json.dumps({"image_size": preset}), mult="1.0",
                is_default=False, sort_order=so)


_OPTIONS = [
    # wan / kling: 16:9, 9:16, 1:1 (дефолт fal -- 16:9)
    _ar("wan_video", "16_9", "16:9", {"aspect_ratio": "16:9"}, default=True, so=10),
    _ar("wan_video", "9_16", "9:16", {"aspect_ratio": "9:16"}, so=20),
    _ar("wan_video", "1_1", "1:1", {"aspect_ratio": "1:1"}, so=30),
    _ar("kling_video", "16_9", "16:9", {"aspect_ratio": "16:9"}, default=True, so=10),
    _ar("kling_video", "9_16", "9:16", {"aspect_ratio": "9:16"}, so=20),
    _ar("kling_video", "1_1", "1:1", {"aspect_ratio": "1:1"}, so=30),
    # veo: квадрата в схеме fal нет
    _ar("veo_video", "16_9", "16:9", {"aspect_ratio": "16:9"}, default=True, so=10),
    _ar("veo_video", "9_16", "9:16", {"aspect_ratio": "9:16"}, so=20),
    # ovi: аспект фиксированными resolution-парами; дефолт fal = 992x512
    _ar("ovi_video", "wide", "Горизонтальный", {"resolution": "992x512"}, default=True, so=10),
    _ar("ovi_video", "tall", "Вертикальный", {"resolution": "512x992"}, so=20),
    _ar("ovi_video", "square", "Квадрат", {"resolution": "720x720"}, so=30),
    # flux / nano-banana / nano-banana-pro: дефолт fal -- 1:1
    _ar("flux_kontext_pro", "1_1", "1:1", {"aspect_ratio": "1:1"}, default=True, so=10),
    _ar("flux_kontext_pro", "16_9", "16:9", {"aspect_ratio": "16:9"}, so=20),
    _ar("flux_kontext_pro", "9_16", "9:16", {"aspect_ratio": "9:16"}, so=30),
    _ar("flux_kontext_pro", "4_3", "4:3", {"aspect_ratio": "4:3"}, so=40),
    _ar("flux_kontext_pro", "3_4", "3:4", {"aspect_ratio": "3:4"}, so=50),
    _ar("nano_banana", "1_1", "1:1", {"aspect_ratio": "1:1"}, default=True, so=10),
    _ar("nano_banana", "16_9", "16:9", {"aspect_ratio": "16:9"}, so=20),
    _ar("nano_banana", "9_16", "9:16", {"aspect_ratio": "9:16"}, so=30),
    _ar("nano_banana", "4_3", "4:3", {"aspect_ratio": "4:3"}, so=40),
    _ar("nano_banana", "3_4", "3:4", {"aspect_ratio": "3:4"}, so=50),
    _ar("nano_banana_pro", "1_1", "1:1", {"aspect_ratio": "1:1"}, default=True, so=10),
    _ar("nano_banana_pro", "16_9", "16:9", {"aspect_ratio": "16:9"}, so=20),
    _ar("nano_banana_pro", "9_16", "9:16", {"aspect_ratio": "9:16"}, so=30),
    _ar("nano_banana_pro", "4_3", "4:3", {"aspect_ratio": "4:3"}, so=40),
    _ar("nano_banana_pro", "3_4", "3:4", {"aspect_ratio": "3:4"}, so=50),
    # qwen_image / seedream: форматы внутри оси quality (между 1k=10 и 2k=20)
    _q("qwen_image", "16_9", "16:9", "landscape_16_9", so=12),
    _q("qwen_image", "9_16", "9:16", "portrait_16_9", so=14),
    _q("qwen_image", "4_3", "4:3", "landscape_4_3", so=16),
    _q("qwen_image", "3_4", "3:4", "portrait_4_3", so=18),
    _q("seedream", "16_9", "16:9", "landscape_16_9", so=12),
    _q("seedream", "9_16", "9:16", "portrait_16_9", so=14),
    _q("seedream", "4_3", "4:3", "landscape_4_3", so=16),
    _q("seedream", "3_4", "3:4", "portrait_4_3", so=18),
]


def upgrade() -> None:
    # Нативный Postgres enum: ADD VALUE только вне транзакции (паттерн
    # credittxtype из c7d8e9f0a1b2/c6d7e8f9a0b1).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE modeloptionkind ADD VALUE IF NOT EXISTS 'aspect_ratio'")

    for o in _OPTIONS:
        op.execute(
            sa.text(
                "INSERT INTO model_options "
                "(model_id, kind, code, label, provider_params, credits_multiplier, "
                " is_default, sort_order, is_active) "
                # CAST(:kind AS modeloptionkind) обязателен: bind-параметр приезжает
                # varchar'ом, неявного приведения к enum для параметров нет
                # (грабля bb51258925d4, проверено на живом Postgres).
                "SELECT m.id, CAST(:kind AS modeloptionkind), :code, :label, "
                "       CAST(:params AS JSONB), CAST(:mult AS NUMERIC), "
                "       :is_default, :sort_order, true "
                "FROM ai_models m WHERE m.code = :model_code "
                "AND NOT EXISTS (SELECT 1 FROM model_options o "
                "                WHERE o.model_id = m.id "
                "                AND o.kind = CAST(:kind AS modeloptionkind) "
                "                AND o.code = :code)"
            ).bindparams(**o)
        )


def downgrade() -> None:
    op.execute("DELETE FROM model_options WHERE kind = 'aspect_ratio'")
    # Форматные пресеты оси quality у qwen/seedream (коды с подчёркиванием --
    # 1k/2k/4k не трогаем).
    op.execute(
        "DELETE FROM model_options o USING ai_models m "
        "WHERE o.model_id = m.id AND m.code IN ('qwen_image', 'seedream') "
        "AND o.kind = 'quality' AND o.code IN ('16_9', '9_16', '4_3', '3_4')"
    )
    # Значение из enum Postgres удалять не умеет -- aspect_ratio остаётся (безвредно).
