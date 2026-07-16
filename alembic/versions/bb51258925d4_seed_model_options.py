"""seed model_options -- множители выведены из замеров живого fal 2026-07-15.

`apply_seed` вставляет только отсутствующие строки, но на уже существующей БД
он не гоняется автоматически -- эта миграция засеивает model_options для уже
существующих моделей. Значения строк дословно скопированы из MODEL_OPTIONS
(app/db/seed.py) -- не набраны заново, чтобы сид и миграция не разъехались
(см. tests/db/test_seed_catalog.py::test_option_migration_matches_seed_constants).

Revision ID: bb51258925d4
Revises: e5f6a9b0c1d2
Create Date: 2026-07-16 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bb51258925d4'
down_revision: Union[str, None] = 'e5f6a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Те же данные, что MODEL_OPTIONS в app/db/seed.py, но kind -- строкой,
# params -- через json.dumps (сырой SQL не знает про Python-enum/dict).
_OPTIONS = [
    # --- Wan: две независимые оси качества (resolution + video_quality) ---
    dict(model_code="wan_video", kind="quality", code="480p", label="480p",
         params=json.dumps({"resolution": "480p", "video_quality": "high"}),
         mult="0.5", is_default=False, sort_order=10),
    dict(model_code="wan_video", kind="quality", code="580p", label="580p",
         params=json.dumps({"resolution": "580p", "video_quality": "high"}),
         mult="0.75", is_default=False, sort_order=20),
    dict(model_code="wan_video", kind="quality", code="720p", label="720p",
         # video_quality оставлен на дефолте fal "high" -- эффект этого параметра
         # на цену НЕ замерялся (замер варьировал только resolution), поэтому
         # менять его на "maximum" нельзя без отдельного замера.
         params=json.dumps({"resolution": "720p", "video_quality": "high"}),
         mult="1.0", is_default=True, sort_order=30),
    dict(model_code="wan_video", kind="duration", code="5s", label="5 сек",
         params=json.dumps({"num_frames": 81, "frames_per_second": 16}),
         mult="1.0", is_default=True, sort_order=10),
    dict(model_code="wan_video", kind="duration", code="10s", label="10 сек",
         params=json.dumps({"num_frames": 161, "frames_per_second": 16}),
         mult="1.988", is_default=False, sort_order=20),
    # --- Kling: duration СТРОКОЙ, размером управлять нельзя ---
    dict(model_code="kling_video", kind="duration", code="5s", label="5 сек",
         params=json.dumps({"duration": "5"}),
         mult="1.0", is_default=True, sort_order=10),
    dict(model_code="kling_video", kind="duration", code="10s", label="10 сек",
         params=json.dumps({"duration": "10"}),
         mult="2.0", is_default=False, sort_order=20),
    # --- Veo: duration строкой с суффиксом; звук удваивает цену ---
    dict(model_code="veo_video", kind="duration", code="4s", label="4 сек",
         params=json.dumps({"duration": "4s"}),
         mult="0.5", is_default=False, sort_order=10),
    dict(model_code="veo_video", kind="duration", code="6s", label="6 сек",
         params=json.dumps({"duration": "6s"}),
         mult="0.75", is_default=False, sort_order=20),
    dict(model_code="veo_video", kind="duration", code="8s", label="8 сек",
         params=json.dumps({"duration": "8s"}),
         mult="1.0", is_default=True, sort_order=30),
    dict(model_code="veo_video", kind="audio", code="on", label="Со звуком",
         params=json.dumps({"generate_audio": True}),
         mult="1.0", is_default=True, sort_order=10),
    dict(model_code="veo_video", kind="audio", code="off", label="Без звука",
         params=json.dumps({"generate_audio": False}),
         mult="0.5", is_default=False, sort_order=20),
    dict(model_code="veo_video", kind="quality", code="720p", label="720p",
         params=json.dumps({"resolution": "720p"}),
         mult="1.0", is_default=True, sort_order=10),
    dict(model_code="veo_video", kind="quality", code="1080p", label="1080p",
         params=json.dumps({"resolution": "1080p"}),
         mult="1.0", is_default=False, sort_order=20),
    dict(model_code="veo_video", kind="quality", code="4k", label="4K",
         params=json.dumps({"resolution": "4k"}),
         mult="2.0", is_default=False, sort_order=30),
    # --- qwen_image: image_size пресетом или объектом ---
    dict(model_code="qwen_image", kind="quality", code="1k", label="1K",
         params=json.dumps({"image_size": "square_hd"}),
         mult="1.0", is_default=True, sort_order=10),
    dict(model_code="qwen_image", kind="quality", code="2k", label="2K",
         params=json.dumps({"image_size": {"width": 2048, "height": 2048}}),
         mult="4.0", is_default=False, sort_order=20),
    # --- seedream v4: разрешение бесплатно ---
    dict(model_code="seedream", kind="quality", code="1k", label="1K",
         params=json.dumps({"image_size": "square_hd"}),
         mult="1.0", is_default=True, sort_order=10),
    dict(model_code="seedream", kind="quality", code="2k", label="2K",
         params=json.dumps({"image_size": "auto_2K"}),
         mult="1.0", is_default=False, sort_order=20),
    dict(model_code="seedream", kind="quality", code="4k", label="4K",
         params=json.dumps({"image_size": "auto_4K"}),
         mult="1.0", is_default=False, sort_order=30),
    # --- nano_banana_pro: селектор 1K/2K/4K из дизайн-макета ---
    dict(model_code="nano_banana_pro", kind="quality", code="1k", label="1K",
         params=json.dumps({"resolution": "1K"}),
         mult="1.0", is_default=True, sort_order=10),
    dict(model_code="nano_banana_pro", kind="quality", code="2k", label="2K",
         params=json.dumps({"resolution": "2K"}),
         mult="1.0", is_default=False, sort_order=20),
    dict(model_code="nano_banana_pro", kind="quality", code="4k", label="4K",
         params=json.dumps({"resolution": "4K"}),
         mult="2.0", is_default=False, sort_order=30),
    # НЕ заведены намеренно (см. app/db/seed.py -- комментарий у MODEL_OPTIONS):
    #  - ovi: цена плоская, но влияние resolution не мерили; длительность не
    #    управляется вовсе;
    #  - flux_kontext_pro, nano_banana (обычная), kling quality: у провайдера
    #    нет ручки размера, только aspect_ratio.
]


def upgrade() -> None:
    for o in _OPTIONS:
        op.execute(
            sa.text(
                "INSERT INTO model_options "
                "(model_id, kind, code, label, provider_params, credits_multiplier, "
                " is_default, sort_order, is_active) "
                "SELECT id, :kind, :code, :label, CAST(:params AS JSONB), :mult, "
                "       :is_default, :sort_order, true "
                "FROM ai_models WHERE code = :model_code"
            ).bindparams(**o)
        )


def downgrade() -> None:
    op.execute("DELETE FROM model_options")
