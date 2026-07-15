"""fix fal catalog: реальные эндпоинты + цены по формуле.

apply_seed идемпотентен по code и НЕ обновляет существующие строки, поэтому
правка констант в seed.py чинит только чистую БД. Здесь -- UPDATE для тех,
у кого каталог уже засеян.

Основания (спек docs/superpowers/specs/2026-07-15-generation-quality-design.md):
- wan/v2.2 и kling-video/v2 не существуют (воркер: "Path /v2.2 not found");
- seedream/v3 и veo3 депрецированы fal, 2K/4K только у преемников;
- flux-pro/kontext -- это i2i (image_url обязателен), t2i -- отдельный маршрут;
- цены измерены живыми генерациями: kling 5с=$1.40, veo=$0.40/с, wan 480p=$0.04/с.

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-07-15 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (code, новый provider_model_id, новый min_credits, новый recommended_credits)
# None в цене = не менять.
_FIXES = [
    ("seedream", "fal-ai/bytedance/seedream/v4/text-to-image", None, None),
    ("flux_kontext_pro", "fal-ai/flux-pro/kontext/text-to-image", None, None),
    ("wan_video", "fal-ai/wan/v2.2-a14b/text-to-video", 466, 932),
    ("kling_video", "fal-ai/kling-video/v2/master/text-to-video", 3220, 3220),
    ("veo_video", "fal-ai/veo3.1", 1840, 7360),
]

# Прежние значения -- для downgrade.
_ROLLBACK = [
    ("seedream", "fal-ai/bytedance/seedream/v3", None, None),
    ("flux_kontext_pro", "fal-ai/flux-pro/kontext", None, None),
    ("wan_video", "fal-ai/wan/v2.2", 600, 600),
    ("kling_video", "fal-ai/kling-video/v2", 850, 850),
    ("veo_video", "fal-ai/veo3", 4800, 4800),
]


def _apply(rows) -> None:
    for code, model_id, min_credits, recommended in rows:
        sets = {"provider_model_id": model_id}
        if min_credits is not None:
            sets["min_credits"] = min_credits
        if recommended is not None:
            sets["recommended_credits"] = recommended
        assignments = ", ".join(f"{k} = :{k}" for k in sets)
        op.execute(
            sa.text(f"UPDATE ai_models SET {assignments} WHERE code = :code").bindparams(
                **sets, code=code
            )
        )


def upgrade() -> None:
    _apply(_FIXES)


def downgrade() -> None:
    _apply(_ROLLBACK)
