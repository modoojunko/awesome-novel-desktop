"""schema 对齐：tiers.entitlement / users.agreement_version / device_outdated_marks

s-db-migrate-pipeline 的可升级性测试实勘：这三处只存在于 ORM 元数据（生产由 MCP
手工 DDL 预建、dev 靠 create_all 兜底），迁移链从未承载——fresh sqlite `upgrade head`
后与元数据对不上。本迁移补齐，使「迁移链=唯一 schema 事实源」成立。

Revision ID: a003_schema_alignment
Revises: c4d5e6f7a8b9（线性化后的链尾，见 a1b2c3d4e5f6 的 down_revision 注记）
"""
import sqlalchemy as sa
from sqlalchemy import func

from alembic import op

revision = "a003_schema_alignment"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tiers",
        sa.Column("entitlement", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "users",
        sa.Column("agreement_version", sa.String(length=32), server_default="", nullable=True),
    )
    op.create_table(
        "device_outdated_marks",
        sa.Column("pc_hash", sa.String(length=128), primary_key=True),
        sa.Column(
            "rejected_at",
            sa.DateTime(),
            nullable=False,
            server_default=func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("device_outdated_marks")
    op.drop_column("users", "agreement_version")
    op.drop_column("tiers", "entitlement")
