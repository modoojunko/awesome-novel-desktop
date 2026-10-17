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

# 拆解状态机（任务级）：queued → running → completed | failed | cancelled；
# need_reupload：排队任务源文件缺失（启动 sweep 检测），重传后回 queued 原位次。
STATUSES = ("queued", "running", "completed", "failed", "cancelled", "need_reupload")

# 拆解维度（key, 中文名, 产物文件名）——顺序即管线执行序与目录树展示序。
DIMENSIONS = (
    ("intro", "简介", "简介.md"),
    ("genre", "题材", "题材.md"),
    ("world", "世界设定", "世界设定.md"),
    ("characters", "角色设定", "角色设定.md"),
    ("relations", "人物关系与势力", "人物关系与势力.md"),
    ("mainplot", "主线剧情", "主线剧情.md"),
    ("structure", "章卷结构", "章卷结构.md"),
    ("style", "写作文风", "写作文风.md"),
    ("techniques", "写作技法", "写作技法.md"),
    ("foreshadow", "伏笔", "伏笔.md"),
)
DIMENSION_KEYS = tuple(k for k, _, _ in DIMENSIONS)
# 其中写入书内设定页的 7 项（关系/章卷结构/写作技法随任务侧资料，不进设定页）
SETTING_DIMENSION_KEYS = ("intro", "genre", "world", "characters", "mainplot", "style", "foreshadow")


class DeconstructJob(Base):
    """拆书任务（c-deconstruct-book）——产物事实源（products_json），随应用数据备份。

    独立于 job_runner 全局单飞槽（备份/成稿下载共用该槽，31 分钟拆解不得锁死它们）：
    专属队列 FIFO（queue_seq），全局同一时刻最多一个 running（串行 worker）。
    dims_json：{"cards": {"state", "done", "entries": {章号: 十维拆卡 JSON}},
                "dims": {key: {state, seg_done, seg_total, error}}}（v2 逐章拆卡＋分级归并）.
    products_json：{dim: {"file": 文件名, "data": 模型JSON终稿, "md": 代码渲染全文}}
    （建书消费 data、导出消费 md，不反解；应用内不预览不编辑）。
    """

    __tablename__ = "deconstruct_jobs"
    __table_args__ = (
        Index("ix_deconstruct_jobs_status_seq", "status", "queue_seq"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # queued / running / completed / failed / cancelled / need_reupload
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    queue_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    encoding: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    book_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    total_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chapter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    volume_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parse_warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    api_config_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    ai_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # 创建时勾选的维度子集（JSON 数组，默认全选；管线/续拆/出口计数以此为基础）
    selected_dims_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    dims_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    products_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    book_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # 建书幂等键：重复确认返回同一本书
    # 「已取结果」标记（评审 P3）：任一出口（建书/导出）消费后 badge 不再计数。
    # db-per-version 下发版库全新建表；dev 旧形状库（本列之前建的表）直接 DROP 本表重建。
    exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 换模型续拆历史（c-deconstruct-resilience）：[{api_config_id, ai_model, at}]，append-only
    model_history_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeconstructUnit(Base):
    """拆书单元账（c-deconstruct-resilience D4）——断点续拆与调用账的事实源。

    粒度：card=章；l1=维度内一批碎片；reduce=一次组合并；reduce_state=维度归并
    树的轮间检查点（partials 全量，unit_key 恒 "partials"——续拆从轮边界继续，
    轮内重做有界）；presence=章；place=全书一次。
    unit_key：card=章号，其余=输入内容 sha256 前缀——输入变化（卡片重拆/碎片变化）
    旧单元自然失效，不存在 stale 复用。
    调用账由本表聚合（service.task_stats），不另建统计表；不含原文，只有计数与产物。
    """

    __tablename__ = "deconstruct_units"
    __table_args__ = (
        UniqueConstraint("task_id", "stage", "dim", "unit_key", name="uq_dec_unit"),
        Index("ix_dec_unit_task_stage", "task_id", "stage", "dim"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("deconstruct_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    # card | l1 | reduce | reduce_state | presence | place
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    dim: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    unit_key: Mapped[str] = mapped_column(String(80), nullable=False)
    # running | done | failed | skipped
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="done")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    error_msg: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 成功产物（卡片 JSON / 批次归并 JSON / reduce 检查点 partials 数组）；
    # 失败行为空——账本不存错误原文之外的载荷
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
