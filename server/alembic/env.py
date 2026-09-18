"""Alembic 迁移环境配置。

从 app.models 自动加载所有 ORM 模型，使用 app.config 中的 DB 路径。
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# 将 server/ 目录加入 Python 路径，使 app 包可导入
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 加载 ORM 模型元数据
from app.models import Base

target_metadata = Base.metadata

from app.config import settings


def run_migrations_offline() -> None:
    """离线模式：使用 settings.DATABASE_URL 配置 URL（SQLite / PostgreSQL 均可）。"""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：使用 app.models.base 中的 engine。"""
    from app.models.base import engine
    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
