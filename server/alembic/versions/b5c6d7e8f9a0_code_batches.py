"""code_batches 表 + codes.batch_id（s-code-issue：发码批次单/预算制）

Revision ID: b5c6d7e8f9a0
Revises: a003_schema_alignment
Create Date: 2026-10-01 16:30:00.000000

幂等：表/列已存在时跳过（inspection 判重，SQLite / PG 通用，同 c4d5e6f7a8b9 套路）。
生产（pg_http）无迁移链，带外 DDL 操作单见 docs/ops/s-code-issue-out-of-band-ddl.md。
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b5c6d7e8f9a0'
down_revision: str | None = 'a003_schema_alignment'
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = 'code_batches'
_COL = 'batch_id'
# sqlite 自增主键须 INTEGER 类型（rowid 别名），PG 用 BigInteger——同 a002 套路
_BIGPK = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def _has_table(insp) -> bool:
    return _TABLE in insp.get_table_names()


def _has_column(insp) -> bool:
    return _COL in [c["name"] for c in insp.get_columns('codes')]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not _has_table(insp):
        op.create_table(
            _TABLE,
            sa.Column('id', _BIGPK, autoincrement=True, primary_key=True),
            sa.Column('batch_id', sa.String(32), nullable=False, unique=True, index=True),
            sa.Column('tier', sa.String(32), nullable=False),
            sa.Column('duration_days', sa.Integer(), nullable=False),
            sa.Column('count', sa.Integer(), nullable=False),
            sa.Column('channel', sa.String(64), nullable=False, server_default=''),
            sa.Column('note', sa.String(255), nullable=False, server_default=''),
            sa.Column('created_by', sa.String(64), nullable=False, server_default=''),
            sa.Column('budget_consumed', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
    if not _has_column(insp):
        op.add_column('codes', sa.Column(_COL, sa.String(32), nullable=True))
        op.create_index('ix_codes_batch_id', 'codes', [_COL])


def _has_index(insp) -> bool:
    return any(ix["name"] == "ix_codes_batch_id" for ix in insp.get_indexes('codes'))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _has_column(insp):
        # 判重兜底：带外 DDL 人工偏差（只加列漏建索引）时跳过，不炸回滚
        if _has_index(insp):
            op.drop_index('ix_codes_batch_id', table_name='codes')
        op.drop_column('codes', _COL)
    if _has_table(insp):
        op.drop_table(_TABLE)
