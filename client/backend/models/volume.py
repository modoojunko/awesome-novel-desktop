import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Volume(Base):
    """卷族主表 — 卷元数据 + 卷纲标量字段（数据全量入库，卷纲子表另立）。

    长度纪律（四档为主）：标签/枚举 50；一句话 150；标题 200；短段落 300。
    SQLite 不强制 VARCHAR 长度，由 volumes/schemas.py 的 Pydantic max_length 真校验。
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

    # ── 卷纲标量字段（卷纲设定指南 §一~§五；全部可空，建卷后逐步填充）────
    # 卷方向来源：template / character_voice / manual
    direction_method: Mapped[str | None] = mapped_column(String(50))
    # 结构模板：三幕式 / 起承転結 / 悬疑递进 / 人物弧线
    template_name: Mapped[str | None] = mapped_column(String(50))
    # 核心冲突一句话："谁 + 想做什么 + 被什么阻碍"
    core_conflict: Mapped[str | None] = mapped_column(String(150))
    # 情绪弧线："压抑→更压抑→提升→打脸→装逼"
    emotional_arc: Mapped[str | None] = mapped_column(String(150))
    # 弧线模式：先压后爽 / 层层逼近 / 张力开合 / 蓄势爆发 / 螺旋递进
    arc_mode: Mapped[str | None] = mapped_column(String(50))
    # 主导驱动力：悬疑 / 威胁 / 目标 / 关系 / 信息差
    primary_drive: Mapped[str | None] = mapped_column(String(50))
    # 卷级信息差起点/终点（谁知道什么 ↦ 谁不知道）
    info_gap_start: Mapped[str | None] = mapped_column(String(300))
    info_gap_end: Mapped[str | None] = mapped_column(String(300))
    # 预估章节数
    chapter_target: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    project = relationship("Novel", back_populates="volumes")
    chapters = relationship(
        "Chapter",
        cascade="all, delete-orphan",
        back_populates="volume",
    )
    stages = relationship(
        "VolumeStage",
        cascade="all, delete-orphan",
        order_by="VolumeStage.sort_order",
        lazy="selectin",
    )
    conflict_ladders = relationship(
        "VolumeConflictLadder",
        cascade="all, delete-orphan",
        order_by="VolumeConflictLadder.sort_order",
        lazy="selectin",
    )
    chapter_plans = relationship(
        "VolumeChapterPlan",
        cascade="all, delete-orphan",
        order_by="VolumeChapterPlan.sort_order",
        lazy="selectin",
    )
    character_voices = relationship(
        "VolumeCharacterVoice",
        cascade="all, delete-orphan",
        order_by="VolumeCharacterVoice.sort_order",
        lazy="selectin",
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


class VolumeStage(_VolumeChildMixin, Base):
    """阶段分配（卷纲 §一）：每阶段名 + 一句话功能 + 分配章节数。"""

    __tablename__ = "volume_stages"
    __table_args__ = (
        UniqueConstraint("volume_id", "sort_order", name="uq_volume_stages_order"),
    )

    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)
    stage_function: Mapped[str] = mapped_column(String(300), nullable=False)
    chapter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class VolumeConflictLadder(_VolumeChildMixin, Base):
    """冲突阶梯 + 转折点（卷纲 §四）：2-4 层逐级升级的障碍。"""

    __tablename__ = "volume_conflict_ladders"
    __table_args__ = (
        UniqueConstraint("volume_id", "sort_order", name="uq_volume_ladders_order"),
    )

    layer_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # 章节区间，格式固定 "1-1~1-2"（标识符例外档）
    chapters_range: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    obstacle: Mapped[str] = mapped_column(String(300), nullable=False)
    # 转折类型：信息 / 关系 / 状态 / 事件
    turning_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    turning_point: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class VolumeChapterPlan(_VolumeChildMixin, Base):
    """chapters_summary（卷纲 §七）——卷纲最核心产出，每章一行。"""

    __tablename__ = "volume_chapter_plans"
    __table_args__ = (
        UniqueConstraint("volume_id", "sort_order", name="uq_volume_plans_order"),
    )

    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # 三要素一句话：谁做了什么 + 冲突 + 结束时什么变了
    summary: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # 情绪锚点："压抑↑——主角发现有人在阻挠"
    emotional_anchor: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    # 信息差："反派知道是陷阱 ↦ 主角不知道"
    info_gap: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # 弧线位置："第3章/共10章——压抑阶段后段"
    arc_position: Mapped[str] = mapped_column(String(150), nullable=False, default="")


class VolumeCharacterVoice(_VolumeChildMixin, Base):
    """卷 N+1 角色发声（卷纲 §一.2）：活跃角色的四项卷间状态。"""

    __tablename__ = "volume_character_voices"
    __table_args__ = (
        UniqueConstraint("volume_id", "sort_order", name="uq_volume_voices_order"),
    )

    character_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 卷末落位：在哪儿、和谁、知道什么
    situation: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # 未完成的事：执念/目标/恐惧
    unfinished: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # 卷间思考
    interlude_thought: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # 现在想做的事
    next_action: Mapped[str] = mapped_column(String(300), nullable=False, default="")
