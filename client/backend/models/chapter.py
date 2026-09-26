import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Chapter(Base):
    """章族主表 — 章元数据 + 章纲标量字段（数据全量入库，章纲子表另立）。

    volume_id FK ondelete CASCADE + ORM relationship cascade 双保险
    （db.py 已 PRAGMA foreign_keys=ON，级联真生效）。
    长度纪律（四档为主）：标签/枚举 50；一句话 150；标题 200；短段落 300。
    SQLite 不强制 VARCHAR 长度，由服务层真校验（组装/拆装时截断或拒收）。
    """

    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("novel_id", "ref", name="uq_chapters_project_ref"),
        Index("ix_chapters_project_volume_status", "novel_id", "volume_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        "novel_id", String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    volume_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    ref: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="outline")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_prose: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outline_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unfilled"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 本章文风影子（chapter-style-shadow，拍板③记章节档案）：JSON 文本列。
    # 形状 {"rows": {dim: {"value": str, "reason": str}}}——只存本章覆盖的行，
    # 未覆盖行沿用全书文风基线（style-quant）。写章提示词组装时按行覆盖注入。
    style_shadow: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 旧稿支线（revert-ghost）：回退点章 ref（vol-1-ch-5）。非空＝本章已脱离主线，
    # 只读保留在支线分组；主线查询一律 ghost_of IS NULL。
    ghost_of: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 基于旧设定（chapter-rewrite）：上游章被重写后由重写事务置位；本章自身
    # 保存/归档成功即清除（单写入口统一处理，不做时间戳派生）
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # ── 章纲标量字段（章纲设定指南；全部可空，建章后逐步填充）──────────
    # outline.summary — 一句话概要（谁做了什么+冲突+结束时什么变了）
    summary: Mapped[str | None] = mapped_column(String(300))
    # c-og-slim-v2 退役：outline.location / outline.time(story_time) / outline.narrative_pov /
    # memo.current_task —— 页面无控件或提示词不读，列随模型摘除（旧库经迁入走列交集）。
    # 字数目标（默认 2500）
    word_target: Mapped[int | None] = mapped_column(Integer)
    # 情绪设计·主情绪
    primary_mood: Mapped[str | None] = mapped_column(String(50))
    # c-og-slim-v2 退役：mood_progression / intensity_peak / intensity_level / emotional_hook /
    # expectation_state / expectation_strategy / expectation_detail / perspective_guidance。
    # 章末落点 — 结尾停在哪个紧张度上，须给下一章更高起点（提示词前情消费）
    ladder_exit: Mapped[str | None] = mapped_column(String(300))

    # ── 拆章五段（c-chapter-plan-ai；JSON 键路径＝章档案顶层，与 ladder_exit 同层）──
    # 碰到的挑战 — 剧情推进时撞上的那道墙（拆章第一步写入）
    challenge: Mapped[str | None] = mapped_column(String(150))
    # 阶段 — 本章在卷剧情里的位置（六档闭集：开局铺垫/冲突初现/矛盾升级/重要转折/高潮爆发/卷末收束）
    plot_stage: Mapped[str | None] = mapped_column(String(20))
    # 章内剧情条目（c-plot-split）：「这一章怎么演」的场景描述条目（string[] 直存
    # JSON 文本列，无子表/排序列）。读侧损坏按 []（assemble_chapter）；写侧
    # presence-gate（缺键保持现值、显式 [] 清空）；预算单源 chapters/schemas。
    plot_items: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")

    # Relationships
    project = relationship("Novel", back_populates="chapters")
    # selectin：组装章 JSON 需要 volume_no，异步会话里禁止隐性 lazy IO
    volume = relationship("Volume", back_populates="chapters", lazy="selectin")
    characters = relationship(
        "ChapterCharacter",
        cascade="all, delete-orphan",
        order_by="ChapterCharacter.sort_order",
        lazy="selectin",
    )
    micro_payoffs = relationship(
        "ChapterMicroPayoff",
        cascade="all, delete-orphan",
        order_by="ChapterMicroPayoff.sort_order",
        lazy="selectin",
    )
    payoff_items = relationship(
        "ChapterPayoffItem",
        cascade="all, delete-orphan",
        order_by="ChapterPayoffItem.sort_order",
        lazy="selectin",
    )
    required_changes = relationship(
        "ChapterRequiredChange",
        cascade="all, delete-orphan",
        order_by="ChapterRequiredChange.sort_order",
        lazy="selectin",
    )
    prohibitions = relationship(
        "ChapterProhibition",
        cascade="all, delete-orphan",
        order_by="ChapterProhibition.sort_order",
        lazy="selectin",
    )
    content = relationship(
        "ChapterContent",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )


class _ChapterChildMixin:
    """章纲子表公共列：FK CASCADE + 有序唯一。"""

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    chapter_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ChapterCharacter(_ChapterChildMixin, Base):
    """outline.characters — 本章出场角色。

    character_id 指向角色身份（改名/合并后引用不断）；character_name 保留原文——
    既是未命中时的快照，也是"读不回卡时"的展示兜底。API 契约 outline.characters
    仍是名字数组：写入时按名解析 id（chapters/store.apply_chapter_data），
    读取时按 id 回填现名。
    """

    __tablename__ = "chapter_characters"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chch_chapter_sort"),
    )
    # 本章该角色的状态变化一句话（archive-reconcile：归档收尾 AI 提取或手填，
    # 重归档/重试覆盖；「截至本章」投影按章引用展示）。替代 legacy
    # character-setting/*.yaml 的 state_history 追加路径。
    state_change: Mapped[str] = mapped_column(Text, nullable=False, default="")
    character_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    character_name: Mapped[str] = mapped_column(String(50), nullable=False)


class ChapterMicroPayoff(_ChapterChildMixin, Base):
    """memo 读者获得（爽点）— 每章 ≥1 只警告不拦（D1 口径），提示词叙事目标消费。"""

    __tablename__ = "chapter_micro_payoffs"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chmp_chapter_sort"),
    )
    # info/relationship/emotion/clue/ability/resource/recognition
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class ChapterPayoffItem(_ChapterChildMixin, Base):
    """memo.payoff_plan 两列表：must_resolve / must_hold（partial_advance 随 c-og-slim-v2 退役）。"""

    __tablename__ = "chapter_payoff_items"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chpi_chapter_sort"),
    )
    # must_resolve / must_hold
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(String(300), nullable=False)


class ChapterRequiredChange(_ChapterChildMixin, Base):
    """memo.required_changes — 本章必须完成的改变（从什么变成什么）。"""

    __tablename__ = "chapter_required_changes"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chrc_chapter_sort"),
    )
    # 信息 / 关系 / 物理 / 权力
    change_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    content: Mapped[str] = mapped_column(String(300), nullable=False)


class ChapterProhibition(_ChapterChildMixin, Base):
    """memo.prohibitions — 可验证的"不要做X"。"""

    __tablename__ = "chapter_prohibitions"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chpr_chapter_sort"),
    )
    content: Mapped[str] = mapped_column(String(300), nullable=False)


class ChapterContent(Base):
    """正文 — 全库 TEXT 五处之一。一章一行（UNIQUE FK）。"""

    __tablename__ = "chapter_contents"
    __table_args__ = (
        UniqueConstraint("chapter_id", name="uq_chco_chapter"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    chapter_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 正文全文 — 全库 TEXT 五处之一（prose/segment 提示词/快照/归档/生成提示词）
    prose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ChapterVersion(Base):
    """版本快照 — 全库 TEXT 五处之一。一章多行（≤50/章，服务层裁剪）。

    version 为 13 位毫秒时间戳（BIGINT，例外档），字典序即时间序；
    snapshot 为冻结的章 JSON（prose/outline/status）。
    """

    __tablename__ = "chapter_versions"
    __table_args__ = (
        UniqueConstraint("chapter_id", "version", name="uq_chve_chapter_version"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    chapter_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(150))
    snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
