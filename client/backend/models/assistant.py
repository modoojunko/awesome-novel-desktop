"""Assistant 表模型（c-writing-agent 批A；c-agent-chat-memory 增书记忆两表）。

六张表全部走 create_all 路径（本地库每版本一个文件、启动期 Base.metadata.create_all，
代内 DDL 已退役）——零迁移代码。

- assistant_sessions   每书每页签一个会话线程（UNIQUE user_id+novel_id+thread_key），携带授权档位 grants 与
                       compact 状态（openwriter conversations.py 的 sessions.grants/compaction
                       双列模式，conversations.py:111）
- assistant_messages   消息与步级事件（seq 会话内序号；card_kind 非空＝产物卡；
                       payload_json 结构化载荷；status=streaming|done|error|adopted）
- writer_profile       作家画像（作家级跨书一份；sections_json 分区：命名口味/雷点/节奏/文风）
- writer_profile_events 画像行为事件源（采纳/拒绝/修改/对话收集），定期总结的数据源
- book_agent_memory    书级 agent 记忆（AI 自身写作规矩按书一份；随书应用层级联删）
- book_decisions       书级项目决策（方向性结论按时间留痕；随书应用层级联删）
"""

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # 会话线程键（c-writing-agent：每页签一个会话——章纲/正文等章内页签、
    # 设定面板、预览各自独立对话；空串＝书级兜底线程。boss 拍板 2026-11-15）
    thread_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 最近所在页面（跨页面续聊定位；「——切换到卷纲——」分隔标记依据）
    page_cursor: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 授权梯度 grants：{"tier": "confirm_each"|"allow_book"|"allow_all"}（c-writing-agent 设计）
    grants_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # compact 状态（openwriter sessions.compaction 同款防御性解析；CompactionState.as_dict）
    compaction_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("user_id", "novel_id", "thread_key", name="uq_assistant_session_thread"),
    )


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

    None＝无覆盖（走 C 端 identity.py 内置默认）；有值＝四字段
    结构化人格（name/persona/voice_rules/fence_rules，fail-loud 校验后落库）。
    """

    __tablename__ = "assistant_personas"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class BookAgentMemory(Base):
    """书级 agent 记忆（c-agent-chat-memory：四层记忆 scope 的「按书」新增层）。

    AI 助手自身对一本书积累的写作规矩与特化知识（叙事视角/禁忌/结尾手法等
    项目级约定）——等价 agent.md 按书一份。助手经记忆工具自主增改删；注入
    L1 系统提示词（身份→人格→书记忆→围栏→协议→域纪律）。生命周期随书：
    删书时应用层级联清理（novels/router.py delete → memory.delete_book_memory，
    image_assets 先例同款；表无 DB 级 FK——本模块惯例 novel_id 裸列＋索引）。
    """

    __tablename__ = "book_agent_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class BookDecision(Base):
    """书级项目决策（c-agent-chat-memory：协作方向性结论按书按时间留痕）。

    作家否决的方向/拍板的调子/关键修改理由——助手经 remember_decision 追加，
    按时间倒序注入（超容量从最旧截断）。生命周期同 book_agent_memory（随书
    删；应用层级联）。
    """

    __tablename__ = "book_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    novel_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
