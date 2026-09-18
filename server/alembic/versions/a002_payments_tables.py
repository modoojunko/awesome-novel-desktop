"""payments tables: tiers/skus/orders/trade_events/reconciliation_reports/invoices + codes columns

Change 1 支付地基（s-pay-foundation task 1.2）。
纯 DDL——本地 SQLite 测试用；生产走 MCP applyMigration。

Revision ID: a002_payments_tables
Revises: a001_users_surrogate
"""
import sqlalchemy as sa

from alembic import op

# SQLite 仅对 INTEGER PRIMARY KEY 自增；PG 用 BIGINT（BigIntPK 跨库类型，同 ORM types.py）
BIGPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

revision = 'a002_payments_tables'
down_revision = 'a001_users_surrogate'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tiers（档位配置：PRO/MAX）──
    op.create_table('tiers',
        sa.Column('id', BIGPK, autoincrement=True, primary_key=True),
        sa.Column('key', sa.String(32), nullable=False, unique=True),
        sa.Column('display_name', sa.String(64), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('selling_points', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(16), nullable=False, server_default='live'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.CheckConstraint("status IN ('live','planned','retired')", name='ck_tiers_status'))
    op.create_index('idx_tiers_rank', 'tiers', ['rank'])

    # ── skus（SKU 配置：tier × period）──
    op.create_table('skus',
        sa.Column('id', BIGPK, autoincrement=True, primary_key=True),
        sa.Column('sku_key', sa.String(64), nullable=False, unique=True),
        sa.Column('tier_id', BIGPK, sa.ForeignKey('tiers.id'), nullable=False),
        sa.Column('period', sa.String(16), nullable=False),
        sa.Column('period_days', sa.Integer(), nullable=False),
        sa.Column('base_price_fen', sa.Integer(), nullable=False),
        sa.Column('discount_permille', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('device_limit', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('on_sale', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.CheckConstraint('period_days > 0', name='ck_skus_days'),
        sa.CheckConstraint('base_price_fen > 0', name='ck_skus_price'),
        sa.CheckConstraint('discount_permille BETWEEN 1 AND 1000', name='ck_skus_discount'),
        sa.CheckConstraint("period IN ('monthly','quarterly','yearly')", name='ck_skus_period'),
        sa.UniqueConstraint('tier_id', 'period', name='uq_skus_tier_period'))

    # ── orders（根对象：含退款列族 + sku_snapshot）──
    op.create_table('orders',
        sa.Column('id', BIGPK, autoincrement=True, primary_key=True),
        sa.Column('order_no', sa.String(32), nullable=False, unique=True),
        sa.Column('user_id', BIGPK, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('sku_id', BIGPK, nullable=False),
        sa.Column('sku_snapshot', sa.JSON(), nullable=False),
        sa.Column('amount_fen', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False, server_default='pending'),
        sa.Column('prepay_status', sa.String(12), nullable=False, server_default='none'),
        sa.Column('code_url', sa.Text(), nullable=True),
        sa.Column('attach_sent', sa.Text(), nullable=True),
        sa.Column('transaction_id', sa.String(64), nullable=True),
        sa.Column('payer_openid', sa.String(128), nullable=True),
        sa.Column('channel', sa.String(12), nullable=False, server_default='wxpay'),
        sa.Column('agreement_version', sa.String(16), nullable=False),
        sa.Column('agreed_at', sa.DateTime(), nullable=False),
        # 退款环节列族（合并进 orders，无独立表）
        sa.Column('refund_status', sa.String(16), nullable=True),
        sa.Column('refund_amount_fen', sa.Integer(), nullable=True),
        sa.Column('refund_reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('refund_operator', sa.String(64), nullable=True),
        sa.Column('refund_wx_id', sa.String(64), nullable=True),
        sa.Column('refund_not_enough', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('refund_requested_at', sa.DateTime(), nullable=True),
        sa.Column('refund_accepted_at', sa.DateTime(), nullable=True),
        # 时间戳
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('fulfilled_at', sa.DateTime(), nullable=True),
        sa.Column('refunded_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('cooldown_ends_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.CheckConstraint('amount_fen > 0', name='ck_orders_amount'),
        sa.CheckConstraint("status IN ('pending','paid','fulfilled','refund_pending','refund_processing','refunded','closed','exception')", name='ck_orders_status'),
        sa.CheckConstraint("prepay_status IN ('none','created','failed')", name='ck_orders_prepay'),
        sa.CheckConstraint("refund_status IN (NULL,'none','cooldown','processing','succeeded','canceled','abnormal')", name='ck_orders_refund_status'),
        sa.CheckConstraint("channel IN ('wxpay','alipay')", name='ck_orders_channel'))

    op.create_index('idx_orders_user_created', 'orders', ['user_id', 'created_at'])
    op.create_index('idx_orders_scan_pending', 'orders', ['created_at'],
                    sqlite_where=sa.text("status = 'pending'"),
                    postgresql_where=sa.text("status = 'pending'"))
    op.create_index('idx_orders_scan_paid', 'orders', ['paid_at'],
                    sqlite_where=sa.text("status = 'paid'"),
                    postgresql_where=sa.text("status = 'paid'"))
    op.create_index('idx_orders_cooldown', 'orders', ['cooldown_ends_at'],
                    sqlite_where=sa.text("status = 'refund_pending'"),
                    postgresql_where=sa.text("status = 'refund_pending'"))
    op.create_index('idx_orders_refund_half', 'orders', ['refund_accepted_at'],
                    sqlite_where=sa.text("refund_status = 'succeeded' AND status != 'refunded'"),
                    postgresql_where=sa.text("refund_status = 'succeeded' AND status != 'refunded'"))
    op.create_index('uq_orders_transaction', 'orders', ['transaction_id'],
                    unique=True,
                    sqlite_where=sa.text('transaction_id IS NOT NULL'),
                    postgresql_where=sa.text('transaction_id IS NOT NULL'))

    # ── trade_events（append-only 审计流水）──
    op.create_table('trade_events',
        sa.Column('event_id', BIGPK, autoincrement=True, primary_key=True),
        sa.Column('event_key', sa.String(255), nullable=False, unique=True),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('order_no', sa.String(32), nullable=True),
        sa.Column('refund_no', sa.String(32), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('operator', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True))
    op.create_index('idx_trade_events_order', 'trade_events', ['order_no', 'created_at'])
    op.create_index('idx_trade_events_type', 'trade_events', ['event_type', 'created_at'])

    # ── reconciliation_reports（日对账）──
    op.create_table('reconciliation_reports',
        sa.Column('bill_date', sa.Date(), primary_key=True),
        sa.Column('internal_count', sa.Integer(), nullable=False),
        sa.Column('wx_count', sa.Integer(), nullable=False),
        sa.Column('internal_total_fen', sa.Integer(), nullable=False),
        sa.Column('wx_total_fen', sa.Integer(), nullable=False),
        sa.Column('refund_count', sa.Integer(), nullable=False),
        sa.Column('refund_total_fen', sa.Integer(), nullable=False),
        sa.Column('mismatch_detail', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True))
    op.create_index('idx_recon_status', 'reconciliation_reports', ['status'])

    # ── invoices（发票台账；功能暂缓，表随建）──
    op.create_table('invoices',
        sa.Column('invoice_id', BIGPK, autoincrement=True, primary_key=True),
        sa.Column('order_id', BIGPK, nullable=False),
        sa.Column('refund_id', BIGPK, nullable=True),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('title', sa.JSON(), nullable=False),
        sa.Column('amount_fen', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False, server_default='requested'),
        sa.Column('invoice_no', sa.String(64), nullable=True, unique=True),
        sa.Column('red_invoice_no', sa.String(64), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.CheckConstraint("kind IN ('blue','red')", name='ck_invoices_kind'),
        sa.CheckConstraint("status IN ('requested','issued','pending_red_flush','red_flushed','superseded')", name='ck_invoices_status'))

    # ── codes 加列（权益台账扩展）──
    op.add_column('codes', sa.Column('source', sa.String(12), nullable=False, server_default='admin'))
    op.add_column('codes', sa.Column('order_id', BIGPK, nullable=True))
    op.add_column('codes', sa.Column('grant_start', sa.DateTime(), nullable=True))
    op.add_column('codes', sa.Column('status_detail', sa.String(24), nullable=True,
                  server_default='unused'))
    op.create_index('idx_codes_order', 'codes', ['order_id'])
    op.create_index('idx_codes_user_status', 'codes', ['user_id', 'status'])


def downgrade() -> None:
    op.drop_table('invoices')
    op.drop_table('reconciliation_reports')
    op.drop_table('trade_events')
    op.drop_column('orders', 'refund_status')
    op.drop_table('orders')
    op.drop_table('skus')
    op.drop_table('tiers')
