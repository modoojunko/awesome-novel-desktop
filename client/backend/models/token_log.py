"""TokenLog tracks token usage per AI call with fields for
user/project/api_config/operation/model/tokens."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
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
    # ── 写链遥测（c-shortfall-refill）：仅正文生成/续写两路填，其余操作恒 NULL ──
    # 截断分桶：finish_reason="length"＝撞输出预算截断，"stop"＝模型自愿收笔，
    # ""＝供应商未回传（unknown 桶，不与截断混计）
    target_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    below_limit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    finish_reason: Mapped[str] = mapped_column(String(20), default="")
    # 档内命中：建议区间 [plot_hint_low, plot_hint_high] vs 实发剧情条数（现算于
    # plot_count_band 同源；无条数章 NULL＝不参与命中率聚合）
    plot_hint_low: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plot_hint_high: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tier_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# Composite indexes for usage aggregation queries
Index("idx_token_log_project_time", TokenLog.project_id, TokenLog.created_at.desc())
Index("idx_token_log_config_time", TokenLog.api_config_id, TokenLog.created_at.desc())
Index("idx_token_log_user_time", TokenLog.user_id, TokenLog.created_at.desc())
