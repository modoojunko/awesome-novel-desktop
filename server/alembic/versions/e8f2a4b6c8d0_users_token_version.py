"""users 加 token_version 列（s-security-hardening R5：会话撤销）。

存量行默认 0；签发令牌携带 ver，鉴权按 payload.get("ver", 0) 比对——
无版本声明的存量令牌不被误伤，升级零登出。

Revision ID: e8f2a4b6c8d0
Revises: d7e9f1a3b5c7
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e8f2a4b6c8d0"
down_revision: str | None = "d7e9f1a3b5c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
