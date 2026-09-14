"""角色族表 — 角色设定 v2（character-settings-v2）。

数据全量入库（拍板：角色进真表，id 主键，关系型设计；上线后淘汰 character: 前缀 KV）。

长度纪律（同卷族四档）：标签/枚举 50；一句话 150；标题/名称 200；短段落/说明 300。
dossier / cog / legacy 用 JSON 文本列——schema 指纹按"表+列+类型"计算
（legacy_archive.compute_schema_fingerprint），拆列意味着以后每加一格都触发一次
全量留档；JSON 列把加格降为纯代码变更（design.md D1）。

关系为**单向**视角：一条记录归属于 owner（"这个角色怎么看别人"），对方卡上写的
是他自己的视角——同一对端一条由 UNIQUE(owner_id, other_id) 保证。
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Character(Base):
    """角色卡 — 稳定 id 身份；name 仅展示与解析（可改名，引用不受影响）。"""

    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint("novel_id", "seq", name="uq_char_novel_seq"),
        UniqueConstraint("novel_id", "name", name="uq_char_novel_name"),
        # 每本书至多一位主角（部分唯一索引；SQLite 3.8+ 支持，已实测）
        Index(
            "uq_char_protagonist",
            "novel_id",
            unique=True,
            sqlite_where=text("role = '主角'"),
        ),
        Index("ix_char_novel_role", "novel_id", "role"),
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
    # 每书单调递增的显示序号（#C-0001 由它派生）；不复用——由 novels.character_seq_high 计数器保证
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    # JSON array[string]；解析时与 name 一并参与"名字→id"匹配
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 主角 | 配角 | 反派 | 路人（白名单校验在服务层 character_model）
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="配角")
    # 一句话人设（写章必带的全卡摘要；唯一"AI 可覆盖"格）
    persona: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # JSON object：gender/age/race/faction/look/speech/background/plot（8 键，键名冻结）
    dossier: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # JSON object：认知六层 30 格（w1..e5，键名冻结；新增格位=纯代码变更）
    cog: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # JSON object：老字段原文留存（possessions/experiences/relationships/state_history/
    # personality…）——只存不读、不上界面、不进 AI；响应组装必须显式白名单，禁 model_dump 直出
    legacy: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 卡级乐观锁（单格 PATCH 条件 UPDATE；merge/delete/关系 upsert 也要 bump）
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CharacterRelation(Base):
    """单向人物关系 — owner 对 other 的看法；一条记录一个视角。"""

    __tablename__ = "character_relations"
    __table_args__ = (
        UniqueConstraint("owner_id", "other_id", name="uq_char_rel_pair"),
        Index("ix_char_rel_novel", "novel_id"),
        Index("ix_char_rel_other", "other_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    # 冗余 novel_id：按书聚合列表 + 级联删除（与 chapters.volume_id 同款）
    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    other_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 亲缘/师承/立场/恩怨四组词表（白名单校验在服务层 character_model）
    rel_type: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    stance: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    note: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # 记录时的章节 ref（vol-1-ch-11）；是时间戳性质的历史标记，不是活链接
    ch_ref: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CharacterGate(Base):
    """角色确认存档 — 两档门禁与第三态（内容有变）的唯一事实源。

    与 settings-status.yaml 分离：那份文件是纯 bool dict（gates.py 按 bool() 读），
    塞对象会恒真。readiness 保持纯内容谓词，绝不读写本表。
    """

    __tablename__ = "character_gate"

    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    protagonist_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 确认时的门禁相关性摘要（sha256[:16]）：非路人卡的六项按 id 排序拼接后哈希。
    # 与 protagonist_id 一起构成 stale 判据（换主角时 gate_digest 可能仍 ok，
    # 只有 protagonist_id 能捕捉"主角换人"）。
    fingerprint: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CharacterOp(Base):
    """破坏性操作前像 — 删除/合并/删关系的一步撤销依据。

    合并的"按对端去重"会删掉关系行，其前像不在任何表的当前状态里 ⇒ 撤销必须留底。
    过期不删行：保留审计痕迹，且让"过期 409"与"无此 token 404"可区分。
    """

    __tablename__ = "character_ops"
    __table_args__ = (
        UniqueConstraint("undo_token", name="uq_char_op_token"),
        Index("ix_char_op_novel", "novel_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
    )
    # delete | merge | relation_delete
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # JSON 前像：被删卡全量 + 相关关系行 + 门禁行；撤销按它同事务重放
    before: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    undo_token: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
