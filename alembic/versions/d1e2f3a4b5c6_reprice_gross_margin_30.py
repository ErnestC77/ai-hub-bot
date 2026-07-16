"""reprice media + margin to gross margin 30%

Валовая маржа 2.5 -> 1.428571 (= 1/(1-0.30)). Текст пересчитывается на лету из
settings.margin_multiplier; медиа-цены -- фиксированные recommended_credits/
min_credits, поэтому обновляются здесь (сид меняет только чистые установки).
Медиа-фактор 2300 -> 1314 (= 80 x 1.15 x 1.428571 / 0.10); значения = ceil(old x 1314/2300).
VIDEO_MIN_CREDITS (500 -> 290) -- код-константа, миграции не требует.

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-07-16
"""

from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None

# code -> (new_min, new_rec, old_min, old_rec)
_MEDIA = {
    "qwen_image": (29, 29, 50, 50),
    "seedream": (43, 43, 75, 75),
    "flux_kontext_pro": (58, 58, 100, 100),
    "nano_banana": (58, 58, 100, 100),
    "nano_banana_pro": (198, 198, 345, 345),
    "ovi_video": (286, 286, 500, 500),
    "wan_video": (267, 533, 466, 932),
    "kling_video": (1840, 1840, 3220, 3220),
    "veo_video": (1052, 4206, 1840, 7360),
}


def _apply(min_idx: int, rec_idx: int, margin: str) -> None:
    op.execute(
        f"UPDATE settings SET value = '{margin}' WHERE key = 'margin_multiplier'"
    )
    for code, vals in _MEDIA.items():
        op.execute(
            "UPDATE ai_models "
            f"SET min_credits = {vals[min_idx]}, recommended_credits = {vals[rec_idx]} "
            f"WHERE code = '{code}'"
        )


def upgrade() -> None:
    _apply(0, 1, "1.428571")


def downgrade() -> None:
    _apply(2, 3, "2.5")
