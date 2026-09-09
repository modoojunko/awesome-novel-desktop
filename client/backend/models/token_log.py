"""TokenLog tracks token usage per AI call with fields for
user/project/api_config/operation/model/tokens."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class TokenLog(Base):
    __tablename__ = "token_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        "novel_id", String(36), ForeignKey("novels.id"), nullable=True
    )
    api_config_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("api_configs.id", ondelete="SET NULL"), nullable=True
    )
    chapter_id: Mapped[str] = mapped_column(String(100), nullable=True)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(50), default="haiku")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# Composite indexes for usage aggregation queries
Index("idx_token_log_project_time", TokenLog.project_id, TokenLog.created_at.desc())
Index("idx_token_log_config_time", TokenLog.api_config_id, TokenLog.created_at.desc())
Index("idx_token_log_user_time", TokenLog.user_id, TokenLog.created_at.desc())
