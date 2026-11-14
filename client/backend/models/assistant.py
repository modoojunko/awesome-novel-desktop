"""Assistant 表模型（c-writing-agent 批A）。

四张表全部走 create_all 路径（本地库每版本一个文件、启动期 Base.metadata.create_all，
代内 DDL 已退役）——零迁移代码。

- assistant_sessions   每书一个会话（UNIQUE user_id+novel_id），携带授权档位 grants 与
                       compact 状态（openwriter conversations.py 的 sessions.grants/compaction
                       双列模式，conversations.py:111）
- assistant_messages   消息与步级事件（seq 会话内序号；card_kind 非空＝产物卡；
                       payload_json 结构化载荷；status=streaming|done|error|adopted）
- writer_profile       作家画像（作家级跨书一份；sections_json 分区：命名口味/雷点/节奏/文风）
- writer_profile_events 画像行为事件源（采纳/拒绝/修改/对话收集），定期总结的数据源
"""

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # 最近所在页面（跨页面续聊定位；「——切换到卷纲——」分隔标记依据）
    page_cursor: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 授权梯度 grants：{"tier": "confirm_each"|"allow_book"|"allow_all"}（c-writing-agent 设计）
    grants_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # compact 状态（openwriter sessions.compaction 同款防御性解析；CompactionState.as_dict）
    compaction_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    __table_args__ = (UniqueConstraint("user_id", "novel_id", name="uq_assistant_session_book"),)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(nullable=False)
    # user | assistant | event | tool
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # 消息产生时所在页面（「——切换到卷纲——」分隔标记依据）
    page: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 气泡纯文本（叙述/回复/工具结果摘要）
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 结构化载荷：intent / 产物卡 / 思考轨迹 / 工具调用记录
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # struct | text | report | pick | gate；空＝普通消息
    card_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    # streaming | done | error | adopted
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="done")
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    tokens_in: Mapped[int] = mapped_column(nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class WriterProfile(Base):
    __tablename__ = "writer_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 分区 JSON：{"naming":…, "pet_peeves":…, "pacing":…, "style":…, "freeform":…}
    sections_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 「暂停画像学习」开关（true＝后台总结停更；已有内容保留可手动编辑）
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class WriterProfileEvent(Base):
    __tablename__ = "writer_profile_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    # adopted | rejected | revised | chat_collect | summary | …（行为事件源）
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")

class AssistantPersona(Base):
    """助手人格的用户覆盖（c-writing-agent：顶栏控制中心可查看/编辑/恢复默认）。

    None＝无覆盖（走提示词包 assistant_identity / 内置兜底）；有值＝四字段
    结构化人格（name/persona/voice_rules/fence_rules，fail-loud 校验后落库）。
    """

    __tablename__ = "assistant_personas"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
