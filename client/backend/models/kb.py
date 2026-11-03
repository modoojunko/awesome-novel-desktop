"""写作知识库 · 知识两域（账号级域＋书级域；表清单见各域注释——表数以域枚举为准，不锁计数）。

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
    LargeBinary,
    String,
    Text,
    func,
    text,
)
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


class KbEntryBlob(Base):
    """条目头像/图片字节 — (entry_id, variant) 复合主键；variant=full|thumb。

    角色库数据源切换（c-kb-character-migration 刀2c ①）：库卡头像字节的新家。
    不用 CharacterLibraryBlob 承接新键是实证裁定：那张表 library_id 有指向
    character_library 的真 FK（PRAGMA foreign_keys=ON 下 entry id 键插入必
    FOREIGN KEY constraint failed），且 C端无 alembic、活库无 schema 手术通道。
    旧字节仍住 CharacterLibraryBlob（迁移卡经 src_key 回联读，零迁移），
    头像键统一（③）搬迁后退役。照 KbEntryTag 先例不挂 FK（kb 家族松约束）。
    """

    __tablename__ = "kb_entry_blobs"

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    variant: Mapped[str] = mapped_column(String(10), primary_key=True)  # full | thumb
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


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
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    # 写法块（c-kb-write-block）四列预留：selector=rule|llm|rule_fallback；
    # brief_json=LLM 选择输入/输出摘要（P1 审计）；domain_fingerprint=启用库 id 集
    # 指纹（换库即重选——复用守卫）；server_default 保列交集搬运（老库加列口径）
    selector: Mapped[str] = mapped_column(String(20), nullable=False, default="rule", server_default="rule")
    brief_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    domain_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
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
    # 条目文本快照（重试字节一致：条目编辑后同 run 重建仍逐字节同块）
    text_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class KbOrganizeOutput(Base):
    """整理运行明细计数（c-kb-organize）——runs 只有关系三计数，本表装其余各类。

    spec 措辞「运行记录（含关联明细表）」；kind 例：trigger/scan/pending_relations/
    suggestion_merge/suggestion_reclass/suggestion_subconcept/quality/truncated。
    """

    __tablename__ = "kb_organize_outputs"

    # uuid 主键：备份导入端通用循环按 row["id"] 识别行（无 id 行会被跳过）
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class KbOrganizeFinding(Base):
    """整理建议/待确认项（c-kb-organize）——合并/纠偏/子概念/质量四类，跨 run 持久。

    status: proposed（待作家处置）/ adopted（采纳）/ ignored（忽略——同 signature
    不再提出）。payload_json 为建议快照（目标概念/保留条目/说明/证据）。
    """

    __tablename__ = "kb_organize_findings"
    __table_args__ = (
        Index("ix_kb_org_findings_user_kind", "user_id", "kind", "status"),
        Index("uq_kb_org_findings_sig", "user_id", "kind", "signature",
              unique=True, sqlite_where=text("status = 'proposed'")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    genre: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # merge|reclass|subconcept|quality
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    subject2_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="proposed")
    signature: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class KbBookEntry(Base):
    """书级知识副本（c-kb-book-scope）——开书选题材时从账号级条目复制而来，
    复制即脱离：源条目编辑/删除不影响副本，副本编辑/删除不回写源。

    src 溯源：src_kind="book_copy"、src_ref=novel_id、src_key=源条目 id
    （增量导入/补平的幂等键；部分唯一索引防并发双击重复复制）。
    标签物化照 kb_entry_tags 同构落 kb_book_entry_tags（选择器书级取数域）。"""

    __tablename__ = "kb_book_entries"
    __table_args__ = (
        Index(
            "uq_kb_book_entries_src",
            "novel_id", "src_key",
            unique=True,
            sqlite_where=text("src_ref <> ''"),
        ),
        Index("ix_kb_book_entries_novel", "novel_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
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
    src_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="book_copy")
    src_ref: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    src_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    src_novel_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class KbOrganizeFeedback(Base):
    """整理负反馈（c-kb-organize）——「这条不对」的特征签名，下次整理降权。

    与 kb_prefs（条目有用率）语义隔离：本表只服务整理器特征打分。
    """

    __tablename__ = "kb_organize_feedback"
    __table_args__ = (
        Index("uq_kb_org_feedback_sig", "user_id", "kind", "signature", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # relation|merge
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class KbEntryMerge(Base):
    """条目合并指向（c-kb-organize）——被并条目（status=merged）→保留条目。

    独立表而非 kb_relations：六类白名单纯度保住、5× 上限计数免过滤。
    详情追溯（include_merged）读它。
    """

    __tablename__ = "kb_entry_merges"
    __table_args__ = (
        Index("uq_kb_entry_merges_merged", "merged_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    surviving_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    merged_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class KbBaselineEntry(Base):
    """官方基线条目——只读 lower 层（c-kb-baseline）。

    overlay 双层：同步＝整层事务替换（清旧插新＋记 pack_version），客户端任何路径
    SHALL NOT 对单条修改；用户改/藏＝upper 层 kb_baseline_overlays 写时复制。
    主键＝uuid5(NS, src_key) 确定性代理——跨包/跨设备/跨备份稳定。
    设备级、非账号级：不进备份（重同步重建）、不进账号级八表计数。
    """

    __tablename__ = "kb_baseline_entries"

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    src_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    pack_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    genre: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    concept: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(12), nullable=False, default="base")
    slot: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    when_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KbBaselineOverlay(Base):
    """用户对基线条目的覆盖（upper 层写时复制）——hide whiteout / edit 私有副本。"""

    __tablename__ = "kb_baseline_overlays"
    __table_args__ = (
        Index("uq_kb_baseline_overlay", "user_id", "src_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    src_key: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)  # hide | edit
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    base_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KbBaselineTag(Base):
    """基线条目物化过滤维度（照 kb_entry_tags 可重建先例——同步时随层物化）。"""

    __tablename__ = "kb_baseline_tags"
    __table_args__ = (
        Index("ix_kb_baseline_tags_dim_value", "dim", "value"),
        Index("ix_kb_baseline_tags_entry", "entry_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dim: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)


class KbBookEntryTag(Base):
    """书级副本的物化标签（照 kb_entry_tags 同构；选择器书级取数域）——
    可随时 DELETE+重建（自愈），novel_id 冗余列使单表索引成立。"""

    __tablename__ = "kb_book_entry_tags"
    __table_args__ = (
        Index("ix_kb_book_entry_tags_novel_dim", "novel_id", "dim", "value"),
        Index("ix_kb_book_entry_tags_entry", "entry_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    dim: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
