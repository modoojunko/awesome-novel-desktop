"""device_grants 加 challenge 列（s-security-hardening：配对挑战-应答）。

challenge = C端 本机配对密钥的 SHA-256（64 位小写 hex），授权时落库；
换取令牌走 /api/pair/exchange 恒定时间比对。可空：存量行=未升级（硬切后不返 token）。

Revision ID: d7e9f1a3b5c7
Revises: a002_payments_tables
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d7e9f1a3b5c7"
down_revision: str | None = "a002_payments_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device_grants", sa.Column("challenge", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("device_grants", "challenge")
