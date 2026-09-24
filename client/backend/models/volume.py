import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Volume(Base):
    """卷族主表 — 卷元数据 + 卷纲字段（storyline 卷视图换代字段集）。

    长度纪律（四档为主）：标签/枚举 50；一句话 150；标题 200；短段落 300。
    SQLite 不强制 VARCHAR 长度，由 volumes/schemas.py 的 Pydantic max_length 真校验。
    plants/reveals 存多行文本（一行一条）；接口契约是 list[str]（schemas 归一化），
    存储列只承载 join 后的行文本，装配端复用 schemas 的同一归一函数。
    """

    __tablename__ = "volumes"
    __table_args__ = (
        UniqueConstraint("novel_id", "volume_no", name="uq_volumes_project_volume_no"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        "novel_id", String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    volume_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    chapter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # ── 卷纲字段（storyline 卷视图：卷基础信息 + 本卷剧情 + 伏笔与信息披露）──
    # 结构模板：三幕式 / 起承転結 / 悬疑递进 / 人物弧线
    template_name: Mapped[str | None] = mapped_column(String(50))
    # 核心矛盾（必填，界面校验；≤150）
    core_conflict: Mapped[str | None] = mapped_column(String(150))
    # 整体目标：本卷结束时想达成的局面（≤300）
    goal: Mapped[str | None] = mapped_column(String(300))
    # 预期结局：收尾状态；多结局在此列分支（≤300）
    ending: Mapped[str | None] = mapped_column(String(300))
    # 本卷埋下伏笔，一行一条（后续卷回收）
    plants: Mapped[str | None] = mapped_column(Text)
    # 本卷揭露信息，一行一条
    reveals: Mapped[str | None] = mapped_column(Text)
    # 预估章节数（章数目标；留空为不设）
    chapter_target: Mapped[int | None] = mapped_column(Integer)
    # 展开依据：本卷是照哪句话铺出来的（作者写的那一句或选中的那套走法；可空）
    plan_line: Mapped[str | None] = mapped_column(String(150))
    # 本卷的坎（c-volume-antagonist）：类型闭集（人物/难题/环境/自我/势力）＋一句话
    antagonist_type: Mapped[str | None] = mapped_column(String(20))
    antagonist_line: Mapped[str | None] = mapped_column(String(150))

    # Relationships
    project = relationship("Novel", back_populates="volumes")
    chapters = relationship(
        "Chapter",
        cascade="all, delete-orphan",
        back_populates="volume",
    )


class _VolumeChildMixin:
    """卷纲子表公共列：volume_id + sort_order（卷内 0 起连续）。"""

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    volume_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("volumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


