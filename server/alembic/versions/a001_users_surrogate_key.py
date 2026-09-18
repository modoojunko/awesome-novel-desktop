"""users surrogate key: username PK -> id BIGINT PK

一次性到位（2026-08-30 用户裁定）。表重建法（schema-only）。
消费场景 = fresh sqlite 库（本地 dev/测试 startup 的 alembic 先行）；
存量数据回填在生产 PG 由 MCP 手工等价 SQL 完成（runbook 1.3），不走 alembic。

Revision ID: a001_users_surrogate
Revises: c3a51e09d7e2
"""
import sqlalchemy as sa

from alembic import op

# SQLite 仅对 INTEGER PRIMARY KEY 自增；PG 用 BIGINT（BigIntPK 跨库类型，同 ORM types.py）
BIGPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

revision = 'a001_users_surrogate'
down_revision = 'c3a51e09d7e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. users：重建（id PK + username UNIQUE）──
    op.create_table('users_new',
        sa.Column('id', BIGPK, autoincrement=True, primary_key=True),
        sa.Column('username', sa.String(128), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('security_question', sa.Text(), server_default='', nullable=True),
        sa.Column('security_answer_hash', sa.String(256), server_default='', nullable=True),
        sa.Column('status', sa.String(32), server_default='active', nullable=True),
        sa.Column('theme', sa.String(32), server_default='', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=True))
    op.create_index('ix_users_new_status', 'users_new', ['status'])

    # ── 2. codes：bound_username -> user_id ──
    op.create_table('codes_new',
        sa.Column('code_id', sa.String(32), primary_key=True),
        sa.Column('tier', sa.String(32), nullable=False, index=True),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(32), server_default='unused', nullable=True, index=True),
        sa.Column('user_id', BIGPK, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=True),
        sa.Column('created_by', sa.String(64), server_default='', nullable=True))

    # ── 3. device_grants：username -> user_id ──
    op.create_table('device_grants_new',
        sa.Column('pc_hash', sa.String(128), primary_key=True),
        sa.Column('user_id', BIGPK, sa.ForeignKey('users.id'),
                  nullable=False, index=True),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('enrolled', sa.Integer(), server_default='0', nullable=True),
        sa.Column('fingerprint', sa.String(256), server_default='', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=True))

    # ── 4. device_registry：旧 user_id(String) -> user_id BIGINT ──
    op.create_table('device_registry_new',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', BIGPK, sa.ForeignKey('users.id'),
                  nullable=False, index=True),
        sa.Column('fingerprint', sa.String(256), server_default='', nullable=True),
        sa.Column('hostname', sa.String(256), server_default='', nullable=True),
        sa.Column('os', sa.String(128), server_default='', nullable=True),
        sa.Column('os_arch', sa.String(32), server_default='', nullable=True),
        sa.Column('last_active_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=True),
        sa.Column('bound_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=True),
        sa.UniqueConstraint('user_id', 'fingerprint', name='uq_user_fingerprint'))

    # ── 数据回填 ──
    # 本迁移的消费场景只有「fresh sqlite 库」（本地 dev/测试，startup 先 alembic 后
    # create_all）——fresh 库无存量数据，回填为空操作；存量数据回填（username→id）
    # 在生产 PG 由 MCP 手工等价 SQL 完成（s-pay-foundation runbook 1.3），不走 alembic。
    # 存量 sqlite 库如需保留数据升级，请参照生产 runbook 的四条 INSERT...SELECT 手工执行。

    # ── 删旧表+改名 ──
    op.drop_table('users')
    op.rename_table('users_new', 'users')
    op.drop_table('codes')
    op.rename_table('codes_new', 'codes')
    op.drop_table('device_grants')
    op.rename_table('device_grants_new', 'device_grants')
    op.drop_table('device_registry')
    op.rename_table('device_registry_new', 'device_registry')


def downgrade() -> None:
    pass
