"""写作知识库 · 11 张表（账号级 8 + 书内 3）。

账号级（不挂 novel_id、不随书级联）：
  kb_concepts        概念树（六概念 + 子概念叶子；种子只读，P1 可加）
  kb_entries         条目（一知识一行；payload_json 按概念强校验）
  kb_entry_tags      物化过滤索引（concept/genre/scope/scene/emotion/chapter_pos/slot/tag）
  kb_relations       概念/条目关系（AI 整理写入；只读展示）
  kb_organize_runs   AI 整理流水（一次一题材）
  kb_libraries       库定义（题材×概念格子；默认库自动生成）
  kb_library_items   库成员 join（默认库=全部条目；手动圈选 P1）
  kb_prefs           反馈权重（user_id+entry_id 账号级；有用/没用）

书内（挂 novel_id、随书级联、进单书备份）：
  kb_book_bindings   书启用了哪个库（含快照）
  kb_match_runs      每章选择运行（章+brief_hash 唯一）
  kb_match_items     逐条目清单（clause/entry/decision/score/reason/used/helpful）
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _uuid() -> str:
    import uuid
    return str(uuid.uuid4())


# ─── 账号级 ───────────────────────────────────────────────

class KbConcept(Base):
    """概念树——六概念（level 1）+ 子概念叶子（level 2）。种子只读，P1 可加子概念。"""

    __tablename__ = "kb_concepts"
    __table_args__ = (
        Index("ix_kb_concepts_user_parent", "user_id", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    parent_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array[str]
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class KbEntry(Base):
    """条目——一知识一行；payload_json 按概念强校验；来源幂等键防重。"""

    __tablename__ = "kb_entries"
    __table_args__ = (
        Index("ix_kb_entries_user_genre_concept", "user_id", "genre", "concept", "concept_id", "status"),
        # 幂等键：手录（src_ref=''）不参与
        Index(
            "uq_kb_entries_src",
            "user_id", "src_ref", "src_key",
            unique=True,
            sqlite_where=text("src_ref <> ''"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    genre: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    concept: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    concept_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    example: Mapped[str] = mapped_column(Text, nullable=False, default="")
    negative_example: Mapped[str] = mapped_column(Text, nullable=False, default="")
    when_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    src_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    src_ref: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    src_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    src_novel_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class KbEntryTag(Base):
    """物化过滤索引——payload/when_json 的可索引投影；可随时 DELETE+重建（自愈）。"""

    __tablename__ = "kb_entry_tags"
    __table_args__ = (
        Index("ix_kb_entry_tags_user_dim_value", "user_id", "dim", "value"),
        Index("ix_kb_entry_tags_entry", "entry_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    dim: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)


class KbRelation(Base):
    """概念/条目关系——AI 整理写入；作家只读展示+反馈。"""

    __tablename__ = "kb_relations"
    __table_args__ = (
        Index("ix_kb_relations_user", "user_id", "status"),
        Index("ix_kb_relations_from_to", "from_id", "to_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    from_id: Mapped[str] = mapped_column(String(80), nullable=False)
    to_id: Mapped[str] = mapped_column(String(80), nullable=False)
    rel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    strength: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="ai")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class KbOrganizeRun(Base):
    """AI 整理流水——一次一题材。"""

    __tablename__ = "kb_organize_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    genre: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="running")
    model: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    api_config_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    entries_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relations_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relations_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relations_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")


class KbLibrary(Base):
    """库定义——题材×概念格子；默认库 auto_all 由首条目触发。"""

    __tablename__ = "kb_libraries"
    __table_args__ = (
        # 默认库唯一：同账号同题材同概念只一个自动库
        Index(
            "uq_kb_lib_auto",
            "user_id", "genre", "concept",
            unique=True,
            sqlite_where=text("rule_kind = 'auto'"),
        ),
        Index("ix_kb_libraries_user_genre", "user_id", "genre"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    genre: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    concept: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    purpose: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    contract: Mapped[str] = mapped_column(String(12), nullable=False, default="snapshot")
    rule_kind: Mapped[str] = mapped_column(String(12), nullable=False, default="auto")
    rule_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class KbLibraryItem(Base):
    """库成员 join——默认库=全部条目；手动圈选 P1。"""

    __tablename__ = "kb_library_items"
    __table_args__ = (
        Index("uq_kb_lib_item", "library_id", "entry_id", unique=True),
        Index("ix_kb_lib_items_lib", "library_id", "sort"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class KbPref(Base):
    """反馈权重——账号级全局（有用率跨书共享）。"""

    __tablename__ = "kb_prefs"
    __table_args__ = (
        Index("uq_kb_pref", "user_id", "entry_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    adopt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drop_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ─── 书内（挂 novel_id、随书级联、进单书备份） ──────────────


class KbBookBinding(Base):
    """书启用了哪个库（含快照）。"""

    __tablename__ = "kb_book_bindings"
    __table_args__ = (
        Index("uq_kb_binding", "novel_id", "library_id", unique=True),
        Index("ix_kb_bindings_novel", "novel_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    library_id: Mapped[str] = mapped_column(String(36), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class KbMatchRun(Base):
    """每章选择运行——章+brief_hash 唯一；重试复用。"""

    __tablename__ = "kb_match_runs"
    __table_args__ = (
        Index("uq_kb_match_run", "novel_id", "chapter_ref", "brief_hash", unique=True),
        Index("ix_kb_match_runs_novel", "novel_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    chapter_ref: Mapped[str] = mapped_column(String(40), nullable=False)
    brief_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scene: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    emotion: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    chapter_pos: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class KbMatchItem(Base):
    """逐条目清单——clause/entry/decision/score/reason/used/helpful。"""

    __tablename__ = "kb_match_items"
    __table_args__ = (
        Index("ix_kb_match_items_run", "run_id"),
        Index("ix_kb_match_items_entry", "entry_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    clause: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision: Mapped[str] = mapped_column(String(12), nullable=False, default="included")
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    helpful: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
