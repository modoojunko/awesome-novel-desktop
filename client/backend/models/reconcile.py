"""归档收尾提案（archive-reconcile）。

每行＝某章某类收尾（AI 收尾或重试）的一次产出：待确认的差异描述与建议值。
**不复存对象数据**：采纳经目标对象自身服务写回（关系/伏笔/lore/出场引用行），
本表只记「待确认的差异」与处置状态；属运行态待办，不进入备份导出包。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ChapterReconcile(Base):
    """归档收尾提案行——某章某类收尾的一次产出。

    进度（进行中/待确认/失败数）由行聚合派生，不另存任务实体。
    同章同键未决行覆盖（防堆积）；已决（accepted/rejected）行保留留痕。
    """

    __tablename__ = "chapter_reconcile"
    __table_args__ = (
        # 同章同类同业务键至多一条未决行（业务键在 payload 内，应用层维护；
        # partial unique 需要 SQLite 表达式索引，为可迁移性改为应用层约束）
        Index("ix_chrec_chapter", "chapter_id"),
        Index("ix_chrec_novel", "novel_id"),
        Index("ix_chrec_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
    )
    chapter_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 收尾类别：set_changes（设定变化）/ relations（角色关系）/
    # hooks（伏笔登记）/ lore（世界要素）/ char_states（角色状态变化）
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    # pending → accepted / rejected / failed（failed 可重试生成新 pending）
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # 待确认的差异：建议值＋证据句（JSON：业务键、建议条目、证据、摘要等）。
    # 不复存对象数据——采纳经目标对象自身服务写回。
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
