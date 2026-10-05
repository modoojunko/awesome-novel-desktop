"""tiers 加 device_limit / duration_days 列（tier-plan-four-tiers B2.1）

档位目录数据驱动（tier-catalog）：设备限额与试用时长从 TIER_POLICY 代码表
升为 tiers 表列，销售侧改库即生效。回填 server_default：现存行 device_limit=1、
duration_days=0（消费方迁移见 domain/licensing/tier_policy.py——DB 不可用兜底）。
生产应用走 MCP 带外 DDL（pg_gate 复核），本迁移承载「迁移链=唯一 schema 事实源」。
"""
import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tiers", sa.Column("device_limit", sa.Integer(), nullable=False,
                                     server_default="1"))
    op.add_column("tiers", sa.Column("duration_days", sa.Integer(), nullable=False,
                                     server_default="0"))


def downgrade() -> None:
    op.drop_column("tiers", "duration_days")
    op.drop_column("tiers", "device_limit")
