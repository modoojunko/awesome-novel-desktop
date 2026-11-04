"""知识 v2 模型（c-kb-knowledge-v2）——知识 / 实例 / 关系 / 别名 / 版本快照。

一条知识＝一个知识单元（c-kb-knowledge-v2 spec）：
  kb_knowledge            知识主体（id/知识名/分类/知识定义/状态/版本/时间/归档）
  kb_knowledge_instances  实例（1 条知识 N 个实例，各有 id；实例不是定义）
  kb_knowledge_relations  知识↔知识关系（两端都用知识 id；六类白名单；禁自环）
  kb_knowledge_aliases    别名（可检索）
  kb_knowledge_revisions  版本快照（保存 +1，保留最近 N 版）

删除＝归档（archived_at 写时间，不硬删）；类别沿用六类封闭注册表；
关系六类白名单与 D6 概念相容矩阵在应用层校验。
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


class KbKnowledge(Base):
    """知识——一个知识单元；删除＝归档（archived_at），不硬删。"""

    __tablename__ = "kb_knowledge"
    __table_args__ = (
        CheckConstraint(
            "category IN ('文风','文笔','世界设定','角色设定','手法','情节')",
            name="ck_kb_knowledge_category",
        ),
        CheckConstraint(
            "status IN ('draft','formed','needs_work')",
            name="ck_kb_knowledge_status",
        ),
        Index(
            "ix_kb_knowledge_list",
            "user_id", "archived_at", "category", "genre", "updated_at",
        ),
        Index("ix_kb_knowledge_updated", "user_id", "updated_at"),
        # 拆书幂等键（手录 src_ref='' 不参与）
        Index(
            "uq_kb_knowledge_src",
            "user_id", "src_ref", "src_key",
            unique=True,
            sqlite_where=text("src_ref <> ''"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    genre: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    when_text: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    when_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    src_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    src_ref: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    src_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    src_novel_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KbKnowledgeMigrationBackup(Base):
    """迁移前快照（c-kb-knowledge-v2 一次性）——回放可重建旧表行；迁移完成后保留。"""

    __tablename__ = "kb_knowledge_migration_backup"
    __table_args__ = (
        Index("ix_kb_migration_backup_kind", "kind", "row_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # kb_entries / kb_relations
    row_key: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class KbKnowledgeInstance(Base):
    """实例——1 条知识 N 个实例；实例有自己的 id；删除知识级联删实例。"""

    __tablename__ = "kb_knowledge_instances"
    __table_args__ = (
        Index("ix_kb_instances_knowledge", "knowledge_id", "sort"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    knowledge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kb_knowledge.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="拆书")
    source_novel: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    source_chapter: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KbKnowledgeRelation(Base):
    """知识↔知识关系——两端都用知识 id；六类白名单；active 唯一；禁自环。"""

    __tablename__ = "kb_knowledge_relations"
    __table_args__ = (
        CheckConstraint("from_id <> to_id", name="ck_kb_knowledge_rel_no_self"),
        CheckConstraint(
            "rel_type IN ('refines','contradicts','depends_on',"
            "'instance_of','derived_from','applies_to')",
            name="ck_kb_knowledge_rel_type",
        ),
        CheckConstraint(
            "status IN ('active','pending','archived')",
            name="ck_kb_knowledge_rel_status",
        ),
        Index(
            "uq_kb_knowledge_rel_active",
            "from_id", "to_id", "rel_type",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_kb_knowledge_rel_from", "from_id", "status"),
        Index("ix_kb_knowledge_rel_to", "to_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    from_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kb_knowledge.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kb_knowledge.id", ondelete="CASCADE"),
        nullable=False,
    )
    rel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KbKnowledgeAlias(Base):
    """别名——可检索投影；(knowledge_id, alias) 唯一。"""

    __tablename__ = "kb_knowledge_aliases"
    __table_args__ = (
        PrimaryKeyConstraint("knowledge_id", "alias"),
        Index("ix_kb_knowledge_alias", "alias"),
    )

    knowledge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kb_knowledge.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(80), nullable=False)


class KbKnowledgeRevision(Base):
    """版本快照——保存时 version+1 并落一份快照；保留策略在应用层（最近 20 版）。"""

    __tablename__ = "kb_knowledge_revisions"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "version", name="uq_kb_revision_version"),
        Index("ix_kb_revisions_knowledge", "knowledge_id", "version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    knowledge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kb_knowledge.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
