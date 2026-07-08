"""phase1 credit system v2: users balance columns + rename, data-migrate balances,
drop tariffs/subscriptions/usage_limits/model_configs, recreate credit_transactions
and ai_requests, create ai_models/credit_packages/settings, swap enum types.

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1f2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(*values: str, name: str) -> postgresql.ENUM:
    # create_type=False: типы создаются явно ниже, чтобы один тип (modelcategory)
    # можно было использовать в двух таблицах без повторного CREATE TYPE.
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    # --- 1. users: новые колонки + rename active_model -> default_model_code ---
    op.add_column('users', sa.Column('credits_balance', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('total_credits_purchased', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('total_credits_spent', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('users', 'active_model', new_column_name='default_model_code')

    # --- 2. data migration: перенести балансы из старого леджера ДО его дропа ---
    # (проект не запущен в платном режиме, но шаг делается безусловно -- на dev/staging
    # могут быть тестовые данные). Старый amount -- Numeric(10,2), баланс -- int.
    op.execute(
        """
        UPDATE users SET credits_balance = COALESCE(
            (SELECT CAST(SUM(ct.amount) AS INTEGER)
             FROM credit_transactions ct
             WHERE ct.user_id = users.id),
            0
        )
        """
    )

    # --- 3. payments.tariff_id: тарифы удаляются, FK снимается (колонка остаётся до фазы 4) ---
    op.drop_constraint('payments_tariff_id_fkey', 'payments', type_='foreignkey')

    # --- 4. drop старых таблиц (в порядке FK-зависимостей) ---
    op.drop_table('usage_limits')
    op.drop_table('subscriptions')
    op.drop_table('credit_transactions')
    op.drop_table('ai_requests')
    op.drop_table('tariffs')
    op.drop_table('model_configs')

    # --- 5. drop старых enum-типов (имена переиспользуются новыми наборами значений) ---
    for type_name in ('subscriptionstatus', 'modelcategory', 'modelprovider', 'credittxtype', 'requeststatus'):
        op.execute(f'DROP TYPE IF EXISTS {type_name}')

    # --- 6. новые enum-типы ---
    op.execute("CREATE TYPE modelprovider AS ENUM ('openrouter', 'fal')")
    op.execute("CREATE TYPE modelcategory AS ENUM ('text', 'image', 'video')")
    op.execute("CREATE TYPE modeltier AS ENUM ('economy', 'standard', 'premium', 'pro', 'ultra')")
    op.execute("CREATE TYPE costunit AS ENUM ('tokens', 'image', 'megapixel', 'second', 'video')")
    op.execute(
        "CREATE TYPE credittxtype AS ENUM "
        "('purchase', 'spend', 'refund', 'reserve', 'release', 'admin_adjustment')"
    )
    op.execute(
        "CREATE TYPE requeststatus AS ENUM "
        "('pending', 'reserved', 'processing', 'completed', 'failed', 'refunded')"
    )

    # --- 7. новые таблицы ---
    op.create_table(
        'ai_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', _enum('openrouter', 'fal', name='modelprovider'), nullable=False),
        sa.Column('category', _enum('text', 'image', 'video', name='modelcategory'), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=False),
        sa.Column('provider_model_id', sa.String(length=128), nullable=False),
        sa.Column('tier', _enum('economy', 'standard', 'premium', 'pro', 'ultra', name='modeltier'), nullable=False),
        sa.Column('input_price_usd_per_1m_tokens', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0'),
        sa.Column('output_price_usd_per_1m_tokens', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0'),
        sa.Column('fixed_cost_usd', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0'),
        sa.Column('cost_unit', _enum('tokens', 'image', 'megapixel', 'second', 'video', name='costunit'), nullable=False),
        sa.Column('min_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recommended_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_context_tokens', sa.Integer(), nullable=False, server_default='8000'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_visible', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'credit_packages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=64), nullable=False),
        sa.Column('credits', sa.Integer(), nullable=False),
        sa.Column('price_rub', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.String(length=128), nullable=False),
        sa.Column('type', sa.String(length=8), nullable=False),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    # ai_requests -- ДО credit_transactions (на него ссылается request_id).
    op.create_table(
        'ai_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model_code', sa.String(length=64), nullable=False),
        sa.Column('category', _enum('text', 'image', 'video', name='modelcategory'), nullable=False),
        sa.Column(
            'status',
            _enum('pending', 'reserved', 'processing', 'completed', 'failed', 'refunded', name='requeststatus'),
            nullable=False,
        ),
        sa.Column('prompt_preview', sa.String(length=200), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reserved_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('charged_credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('provider_cost_usd', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0'),
        sa.Column('provider_response_id', sa.String(length=128), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('insufficient_balance_after_usage', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_requests_user_id'), 'ai_requests', ['user_id'], unique=False)
    op.create_table(
        'credit_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column(
            'type',
            _enum('purchase', 'spend', 'refund', 'reserve', 'release', 'admin_adjustment', name='credittxtype'),
            nullable=False,
        ),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('balance_before', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('model_code', sa.String(length=64), nullable=True),
        sa.Column('request_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['request_id'], ['ai_requests.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_credit_transactions_user_id'), 'credit_transactions', ['user_id'], unique=False)


def downgrade() -> None:
    # Cutover-миграция уничтожает данные старых таблиц (tariffs/subscriptions/
    # usage_limits/model_configs и старый леджер) -- честного отката не существует.
    raise NotImplementedError(
        "phase1_credit_system_v2 is a destructive cutover migration and cannot be downgraded; "
        "restore from a DB backup instead"
    )
