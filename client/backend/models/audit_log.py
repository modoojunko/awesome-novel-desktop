"""Audit log for project AI model changes."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class ProjectModelAuditLog(Base):
    __tablename__ = "project_model_audit_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        "novel_id",
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String(50), default="ai_model")
    old_api_config_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    new_api_config_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    old_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    change_type: Mapped[str] = mapped_column(
        String(20), default="switch"
    )  # initial/switch/clear/restore
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
