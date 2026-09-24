"""users 注销四字段：账号自助注销（account-deletion，design D1）

Revision ID: a1b2c3d4e5f6
Revises: c3a51e09d7e2
Create Date: 2026-08-30 00:40:00.000000

幂等：列已存在时跳过（SQLite / PG 通用，靠 inspection 而非方言 DDL）。
存量行经 server_default 回填 deletion_status='正常'，无 NULL 歧义。
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
# 线性化（s-db-migrate-pipeline）：原挂 c3a51e09d7e2 时与 a001_users_surrogate 形成
# 双头，且 alembic merge 按 revision 字符串排序会先跑本加列支、后跑 a001 重建支——
# 重建的显式列清单会把注销四列吃掉。改挂重建支尾（e8f2a4b6c8d0）锁定「先重建后加列」。
down_revision: str | None = 'e8f2a4b6c8d0'
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = 'users'
_COLS = {
    'deletion_status': sa.Column('deletion_status', sa.String(length=32), server_default='正常', nullable=True),
    'deletion_requested_at': sa.Column('deletion_requested_at', sa.DateTime(), nullable=True),
    'deletion_deadline': sa.Column('deletion_deadline', sa.DateTime(), nullable=True),
    'deletion_waive_assets': sa.Column('deletion_waive_assets', sa.Boolean(), server_default=sa.text('0'), nullable=True),
}


def _existing(insp) -> set[str]:
    return {c["name"] for c in insp.get_columns(_TABLE)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing = _existing(insp)
    for name, col in _COLS.items():
        if name not in existing:
            op.add_column(_TABLE, col)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing = _existing(insp)
    for name in reversed(list(_COLS)):
        if name in existing:
            op.drop_column(_TABLE, name)
