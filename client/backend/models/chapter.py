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
    # outline.location — 场景
    location: Mapped[str | None] = mapped_column(String(200))
    # outline.time — 故事时间（"下午两点"）
    story_time: Mapped[str | None] = mapped_column(String(150))
    # outline.narrative_pov — 叙事视角
    narrative_pov: Mapped[str | None] = mapped_column(String(50))
    # memo.current_task — 本章任务（c-og-fields-slim 退役：只留不读写，列留存因 SQLite 无迁移链）
    current_task: Mapped[str | None] = mapped_column(String(300))
    # 字数目标（默认 2500）
    word_target: Mapped[int | None] = mapped_column(Integer)
    # 情绪设计·主情绪
    primary_mood: Mapped[str | None] = mapped_column(String(50))
    # 章内微弧线（至少三步："平静→不安→紧张"）
    mood_progression: Mapped[str | None] = mapped_column(String(300))
    # 强度峰值（具体到场景）
    intensity_peak: Mapped[str | None] = mapped_column(String(300))
    # 强度等级 1-10
    intensity_level: Mapped[int | None] = mapped_column(Integer)
    # 章末情绪钩子
    emotional_hook: Mapped[str | None] = mapped_column(String(150))
    # memo.reader_expectation.state — 读者预期状态
    expectation_state: Mapped[str | None] = mapped_column(String(150))
    # memo.reader_expectation.strategy — 兑现策略
    expectation_strategy: Mapped[str | None] = mapped_column(String(50))
    # memo.reader_expectation.detail — 一句话说明
    expectation_detail: Mapped[str | None] = mapped_column(String(300))
    # outline.perspective_guidance — 视角转换产物（prompt/router 持久化）
    perspective_guidance: Mapped[str | None] = mapped_column(String(300))
    # 章末落点 — 结尾停在哪个紧张度上，须给下一章更高起点（提示词前情消费）
    ladder_exit: Mapped[str | None] = mapped_column(String(300))

    # ── 拆章五段（c-chapter-plan-ai；JSON 键路径＝章档案顶层，与 ladder_exit 同层）──
    # 碰到的挑战 — 剧情推进时撞上的那道墙（拆章第一步写入）
    challenge: Mapped[str | None] = mapped_column(String(150))
    # 本章行动 — 谁做了什么，一行一条（≤4 行×60；标量清单外定制，照 ladder_exit 先例）
    chapter_acts: Mapped[str | None] = mapped_column(Text)
    # 阶段 — 本章在卷剧情里的位置（六档闭集：开局铺垫/冲突初现/矛盾升级/重要转折/高潮爆发/卷末收束）
    plot_stage: Mapped[str | None] = mapped_column(String(20))

    # Relationships
    project = relationship("Novel", back_populates="chapters")
    # selectin：组装章 JSON 需要 volume_no，异步会话里禁止隐性 lazy IO
    volume = relationship("Volume", back_populates="chapters", lazy="selectin")
    key_points = relationship(
        "ChapterKeyPoint",
        cascade="all, delete-orphan",
        order_by="ChapterKeyPoint.sort_order",
        lazy="selectin",
    )
    characters = relationship(
        "ChapterCharacter",
        cascade="all, delete-orphan",
        order_by="ChapterCharacter.sort_order",
        lazy="selectin",
    )
    scene_cards = relationship(
        "ChapterSceneCard",
        cascade="all, delete-orphan",
        order_by="ChapterSceneCard.sort_order",
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
    downtime_functions = relationship(
        "ChapterDowntimeFunction",
        cascade="all, delete-orphan",
        order_by="ChapterDowntimeFunction.sort_order",
        lazy="selectin",
    )
    key_choices = relationship(
        "ChapterKeyChoice",
        cascade="all, delete-orphan",
        order_by="ChapterKeyChoice.sort_order",
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
    knowledge_states = relationship(
        "ChapterKnowledgeState",
        cascade="all, delete-orphan",
        order_by="ChapterKnowledgeState.sort_order",
        lazy="selectin",
    )
    segments = relationship(
        "ChapterSegment",
        cascade="all, delete-orphan",
        order_by="ChapterSegment.sort_order",
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


class ChapterKeyPoint(_ChapterChildMixin, Base):
    """outline.key_points — [功能标签]笔记体锚点（前端契约：string[]）。"""

    __tablename__ = "chapter_key_points"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chkp_chapter_sort"),
    )
    # [推进剧情·对话] / [造悬念] / [过渡] 等；无标签时空串
    func_tag: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    content: Mapped[str] = mapped_column(String(300), nullable=False)


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


class ChapterSceneCard(_ChapterChildMixin, Base):
    """章纲场景卡三要素（一章 2-5 卡，spec §场景卡）。

    weight/focus 为提示词格子：权重定笔墨分配（high ≥70% 笔墨 / low ≤100 字转场），
    焦点三选一（核心冲突/人物情绪/信息差）。
    """

    __tablename__ = "chapter_scene_cards"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chsc_chapter_sort"),
    )
    scene_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    goal: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    obstacle: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    hook: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # high / mid / low（可空=未标注）
    weight: Mapped[str | None] = mapped_column(String(10))
    # 核心冲突 / 人物情绪 / 信息差（可空=未标注）
    focus: Mapped[str | None] = mapped_column(String(50))


class ChapterMicroPayoff(_ChapterChildMixin, Base):
    """memo 读者获得（爽点）— 每章 ≥1 只警告不拦（D1 口径），提示词叙事目标消费。"""

    __tablename__ = "chapter_micro_payoffs"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chmp_chapter_sort"),
    )
    # info/relationship/emotion/clue/ability/resource/recognition
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # 前段 / 中段 / 后段
    location: Mapped[str] = mapped_column(String(20), nullable=False, default="")


class ChapterPayoffItem(_ChapterChildMixin, Base):
    """memo.payoff_plan 三列表：must_resolve / must_hold / partial_advance。"""

    __tablename__ = "chapter_payoff_items"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chpi_chapter_sort"),
    )
    # must_resolve / must_hold / partial_advance
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(String(300), nullable=False)


class ChapterDowntimeFunction(_ChapterChildMixin, Base):
    """memo.downtime_functions — 日常场景的隐性功能。"""

    __tablename__ = "chapter_downtime_functions"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chdf_chapter_sort"),
    )
    scene: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    func: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class ChapterKeyChoice(_ChapterChildMixin, Base):
    """memo.key_choices — 选择+为什么+人设验证。"""

    __tablename__ = "chapter_key_choices"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chkc_chapter_sort"),
    )
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


class ChapterKnowledgeState(_ChapterChildMixin, Base):
    """角色信息状态+信息差关系/变化（规范字段，模板缺、由 AI 链路逐步填充）。"""

    __tablename__ = "chapter_knowledge_states"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chks_chapter_sort"),
    )
    character_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    knows: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    unknowns: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    gap_relation: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    gap_change: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class ChapterSegment(_ChapterChildMixin, Base):
    """章纲分段元数据（前端可编辑：summary/target_words；AI 生成附加上报键）。

    分段提示词全文（assemble 产物）属生成物，入 chapter_prompts（PR④）。
    """

    __tablename__ = "chapter_segments"
    __table_args__ = (
        UniqueConstraint("chapter_id", "sort_order", name="uq_chsg_chapter_sort"),
    )
    # 这段写什么（人类编辑主字段）
    summary: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    target_words: Mapped[int | None] = mapped_column(Integer)
    # AI 生成时的增强键（分段提示词链路已退役，保留存量数据；人工分段通常为空）
    what_to_write: Mapped[str | None] = mapped_column(String(300))
    goal: Mapped[str | None] = mapped_column(String(300))
    emotional_tone: Mapped[str | None] = mapped_column(String(50))
    # 逗号分隔的角色名列表（原 JSON list 的紧凑存储）
    characters: Mapped[str | None] = mapped_column(String(200))
    function: Mapped[str | None] = mapped_column(String(150))
    word_target: Mapped[int | None] = mapped_column(Integer)
    seg_number: Mapped[int | None] = mapped_column(Integer)


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
