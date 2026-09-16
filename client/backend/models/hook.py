"""伏笔表 — 伏笔设定 v2（foreshadow-settings-v2，tasks 1.2）。

KV 三数组（settings/hooks.yaml active/resolved/abandoned）退役，伏笔升级真表：
id 主键＋每书单调 seq（编号 #H-#### 不复用）＋章节引用 FK 到 chapters.id
（删章 SET NULL 不删行——CASCADE 错杀伏笔、RESTRICT 打断删章流，均被否）。

词表/白名单/长度纪律的唯一事实源在 settings/hooks_model.py（本文件只落列型）。
mentioned_in_chapter_id 是归档留痕列，不是状态——状态枚举只有三值，由
settings/hooks_model.HOOK_STATUSES 白名单约束（服务层校验）。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class NovelHook(Base):
    """伏笔条目 — 稳定 id 身份；description 仅内容，引用方都用 id。"""

    __tablename__ = "novel_hooks"
    __table_args__ = (
        UniqueConstraint("novel_id", "seq", name="uq_hook_novel_seq"),
        Index("ix_hook_novel_status", "novel_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 每书单调递增的显示序号（#H-0001 由它派生）；不复用——由 novels.hook_seq_high
    # 计数器保证（沿 character_seq_high 先例：MAX+1 会在删掉最大号后复用编号）
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # 钩子内容（一句话；readiness 门禁判 trim 非空、任意状态）
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # 9 值 slug 白名单（mystery/threat/promise/clue/relationship/power/emotion/choice/desire）
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="mystery")
    # Integer 1/2/3（高/中/低）；混形归一在服务层 hooks_model.normalize_priority
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    # active | resolved | abandoned（单列；状态切换只改此列，归档不碰）
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # 章节引用存 chapter id（FK SET NULL）：删章/删卷后置 NULL，前端显「章节已删」
    introduced_chapter_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    planned_chapter_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolved_chapter_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 归档留痕（write-archive-meta-sync）：归档本章引入的活跃伏笔时单条 UPDATE；
    # 不参与注入与门禁判定，本期只迁不增（归档 UI 归写作期 change）
    mentioned_chapter_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 收束记录·怎么收的（软引导留痕，不硬拦保存与确认；≤300 字）
    payoff_note: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class HookOp(Base):
    """破坏性操作前像 — 删除伏笔的一步撤销依据（沿 CharacterOp 先例）。

    撤销按原 id 原样恢复（id 与 seq 不变），故删除行的前像必须留底。
    单槽撤销：新书删除操作诞生时，本书更早的 op 一并过期（token 有效期
    到「下次操作」）；过期不删行，让「过期 409」与「无此 token 404」可区分。
    """

    __tablename__ = "hook_ops"
    __table_args__ = (
        UniqueConstraint("undo_token", name="uq_hook_op_token"),
        Index("ix_hook_op_novel", "novel_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
    )
    # delete（本期唯一破坏性操作；预留 kind 供后续扩展）
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # JSON 前像：被删伏笔全量；撤销按它同事务重放（原 id 原样恢复）
    before: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 被删伏笔的 id（restore 路由按 hid 定位 op）
    hook_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    undo_token: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
