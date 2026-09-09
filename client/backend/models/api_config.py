"""ApiConfig model — user's API key configurations."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class ApiConfig(Base):
    __tablename__ = "api_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    vendor: Mapped[str] = mapped_column(String(50), nullable=False)
    vendor_display_name: Mapped[str] = mapped_column(String(100), default="")
    vendor_override: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 接口格式（wire format），与 vendor 正交：同厂商可有两种报文契约
    api_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="openai", server_default="openai"
    )
    api_key: Mapped[str] = mapped_column(String(512), default="")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    models: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    models_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_test_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_api_configs_user_name"),
    )

    # Relationships
    user = relationship("User", back_populates="api_configs")
    novels = relationship("Novel", back_populates="ai_config")
