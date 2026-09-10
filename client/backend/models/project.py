import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Novel(Base):
    __tablename__ = "novels"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    root_path: Mapped[str] = mapped_column(String(500), nullable=False)
    current_phase: Mapped[str] = mapped_column(String(20), default="init")
    status: Mapped[str] = mapped_column(String(20), default="active")
    total_volumes: Mapped[int] = mapped_column(Integer, default=0)
    total_chapters: Mapped[int] = mapped_column(Integer, default=0)
    total_archives: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(10), default="ai")
    backfill_status: Mapped[str] = mapped_column(String(20), default="none")
    ai_config_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("api_configs.id", ondelete="SET NULL"), nullable=True
    )
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "slug"),)

    # Relationships
    ai_config = relationship("ApiConfig", back_populates="novels")
    volumes = relationship(
        "Volume", cascade="all, delete-orphan", back_populates="project"
    )
    chapters = relationship(
        "Chapter", cascade="all, delete-orphan", back_populates="project"
    )
