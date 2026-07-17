"""indexes on ai_requests for webhook lookup + reconcile

provider_response_id -- ключ поиска в горячем пути вебхука
(media_generation_service.handle_fal_webhook); (status, created_at) -- фильтр
reconcile-джобы refund_stale_reserved_requests. Таблица растёт линейно с каждым
запросом, без индексов -- seq scan.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-17
"""

from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_requests_provider_response_id "
        "ON ai_requests (provider_response_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_requests_status_created_at "
        "ON ai_requests (status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ai_requests_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_ai_requests_provider_response_id")
