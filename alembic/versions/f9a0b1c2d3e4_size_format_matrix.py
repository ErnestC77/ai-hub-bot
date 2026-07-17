"""qwen/seedream: ось размера -> матрица «размер x формат» (коды <size>__<fmt>).

Одна строка «1K | 16:9 | ... | 2K» смешивала размер и формат: выбрать «2K и
16:9» было невозможно. У этих моделей оба параметра живут в ОДНОМ поле
провайдера (image_size), поэтому лечится не второй осью (две оси в один ключ
затирали бы друг друга), а полной матрицей комбинаций в той же оси: фронт
рисует два ряда (Размер / Формат кадра) и склеивает выбор в один код.

Цена -- по размеру, формат бесплатный: у qwen все 2K-комбо x4.0 (как прежний
2K; не-квадратные дешевле нам по мегапикселям -- маржа выше, цена та же),
у seedream всё x1.0 (замерено: разрешение бесплатно, плоский тариф).

Идемпотентна; _REPLACED убирает прежние одиночные коды (страж
test_option_migration_matches_seed_constants сверяет цепочку миграций с сидом).

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-07-17 19:00:00.000000
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Прежние одиночные коды оси quality у qwen/seedream, заменённые матрицей.
_REPLACED = {
    ("qwen_image", "quality"): ["1k", "2k", "16_9", "9_16", "4_3", "3_4"],
    ("seedream", "quality"): ["1k", "2k", "4k", "16_9", "9_16", "4_3", "3_4"],
}

_FMT_LABEL = {"1_1": "1:1", "16_9": "16:9", "9_16": "9:16", "4_3": "4:3", "3_4": "3:4"}


def _row(model_code, size, fmt, params, mult, default=False, so=10):
    return dict(
        model_code=model_code, kind="quality", code=f"{size}__{fmt}",
        label=f"{size.upper()} · {_FMT_LABEL[fmt]}", params=json.dumps(params),
        mult=str(mult), is_default=default, sort_order=so,
    )


def _wh(w, h):
    return {"image_size": {"width": w, "height": h}}


_OPTIONS = [
    # --- qwen_image: 1K пресетами fal, 2K пикселями (длинная сторона 2048) ---
    _row("qwen_image", "1k", "1_1", {"image_size": "square_hd"}, 1.0, default=True, so=10),
    _row("qwen_image", "1k", "16_9", {"image_size": "landscape_16_9"}, 1.0, so=12),
    _row("qwen_image", "1k", "9_16", {"image_size": "portrait_16_9"}, 1.0, so=14),
    _row("qwen_image", "1k", "4_3", {"image_size": "landscape_4_3"}, 1.0, so=16),
    _row("qwen_image", "1k", "3_4", {"image_size": "portrait_4_3"}, 1.0, so=18),
    _row("qwen_image", "2k", "1_1", _wh(2048, 2048), 4.0, so=20),
    _row("qwen_image", "2k", "16_9", _wh(2048, 1152), 4.0, so=22),
    _row("qwen_image", "2k", "9_16", _wh(1152, 2048), 4.0, so=24),
    _row("qwen_image", "2k", "4_3", _wh(2048, 1536), 4.0, so=26),
    _row("qwen_image", "2k", "3_4", _wh(1536, 2048), 4.0, so=28),
    # --- seedream: разрешение бесплатно (замерено) -- вся матрица x1.0 ---
    _row("seedream", "1k", "1_1", {"image_size": "square_hd"}, 1.0, default=True, so=10),
    _row("seedream", "1k", "16_9", {"image_size": "landscape_16_9"}, 1.0, so=12),
    _row("seedream", "1k", "9_16", {"image_size": "portrait_16_9"}, 1.0, so=14),
    _row("seedream", "1k", "4_3", {"image_size": "landscape_4_3"}, 1.0, so=16),
    _row("seedream", "1k", "3_4", {"image_size": "portrait_4_3"}, 1.0, so=18),
    _row("seedream", "2k", "1_1", _wh(2048, 2048), 1.0, so=20),
    _row("seedream", "2k", "16_9", _wh(2048, 1152), 1.0, so=22),
    _row("seedream", "2k", "9_16", _wh(1152, 2048), 1.0, so=24),
    _row("seedream", "2k", "4_3", _wh(2048, 1536), 1.0, so=26),
    _row("seedream", "2k", "3_4", _wh(1536, 2048), 1.0, so=28),
    _row("seedream", "4k", "1_1", _wh(4096, 4096), 1.0, so=30),
    _row("seedream", "4k", "16_9", _wh(4096, 2304), 1.0, so=32),
    _row("seedream", "4k", "9_16", _wh(2304, 4096), 1.0, so=34),
    _row("seedream", "4k", "4_3", _wh(4096, 3072), 1.0, so=36),
    _row("seedream", "4k", "3_4", _wh(3072, 4096), 1.0, so=38),
]


def upgrade() -> None:
    for (model_code, kind), codes in _REPLACED.items():
        op.execute(
            sa.text(
                "DELETE FROM model_options o USING ai_models m "
                "WHERE o.model_id = m.id AND m.code = :model_code "
                "AND o.kind = CAST(:kind AS modeloptionkind) "
                "AND o.code = ANY(CAST(:codes AS text[]))"
            ).bindparams(model_code=model_code, kind=kind, codes=codes)
        )
    for o in _OPTIONS:
        op.execute(
            sa.text(
                "INSERT INTO model_options "
                "(model_id, kind, code, label, provider_params, credits_multiplier, "
                " is_default, sort_order, is_active) "
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
    # Матрицу убираем; одиночные коды вернёт сид при следующем старте (или
    # повторный прогон e8f9a0b1c2d3/bb51258925d4 -- они идемпотентны).
    op.execute(
        "DELETE FROM model_options o USING ai_models m "
        "WHERE o.model_id = m.id AND m.code IN ('qwen_image', 'seedream') "
        "AND o.kind = 'quality' AND o.code LIKE '%\\_\\_%' ESCAPE '\\'"
    )
