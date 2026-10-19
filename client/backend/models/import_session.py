import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class ImportSession(Base):
    """A 路第 1 步解析会话：冻结 manifest + 源文件路径，供落库/建任务复用。

    源文件落在 DATA_ROOT/import-sessions/<id>.txt；manifest 只存区间与事实，
    正文不重复进 JSON。过期时间由 persist 入口校验（过期即要求重新解析）。
    """

    __tablename__ = "import_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    encoding: Mapped[str] = mapped_column(String(32), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
